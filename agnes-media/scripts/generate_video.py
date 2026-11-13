#!/usr/bin/env python3
"""Generate video segments from scenes.json via Agnes Video (retry forever, resumable).

Modes auto-selected per scene:
  - text       (default)              : prompt only
  - keyframe   if `first_frame`/`last_frame` given (image URL, publicly reachable)
  - reference  if `images`/`audios`/`videos` given (arrays of URLs)

Usage:
  python3 generate_video.py [--root DIR] [--scenes scenes.json] [--out segments]

Expects scenes.json: [{"id","seconds","prompt", ..., optional media fields}, ...]
Writes {out}/{id}.mp4 and {out}/{id}.video_id; creates {root}/ALL_DONE when all present.
"""
import argparse, json, os, sys, time, urllib.request, urllib.error

BASE = "https://apihub.agnes-ai.com/v1"
MODEL = "agnes-video-2.5-flash"
AUTH = "/data/home/.local/share/opencode/auth.json"


def load_key():
    with open(AUTH) as f:
        return json.load(f)["agnes"]["key"]


KEY = None


def log(root, msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    os.makedirs(os.path.join(root, "logs"), exist_ok=True)
    with open(os.path.join(root, "logs", "gen.log"), "a") as f:
        f.write(line + "\n")


def req(method, url, payload=None, timeout=60):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.getcode(), json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        return e.code, {"error": body}
    except Exception as e:
        return 0, {"error": str(e)}


def download(url, path):
    tmp = path + ".part"
    with urllib.request.urlopen(url, timeout=300) as resp, open(tmp, "wb") as f:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    os.replace(tmp, path)


def build_payload(scene):
    """Pick mode + media fields from the scene dict. text is the default."""
    payload = {
        "model": scene.get("model", MODEL),
        "prompt": scene["prompt"],
        "seconds": str(scene.get("seconds", "12")),
        "size": scene.get("size", "720P"),
        "aspect_ratio": scene.get("aspect_ratio", "16:9"),
    }
    if scene.get("seed") is not None:
        payload["seed"] = int(scene["seed"])
    has_first = bool(scene.get("first_frame"))
    has_last = bool(scene.get("last_frame"))
    refs = [k for k in ("images", "audios", "videos") if scene.get(k)]
    if has_first or has_last:
        payload["mode"] = "keyframe"
        if has_first:
            payload["first_frame"] = scene["first_frame"]
        if has_last:
            payload["last_frame"] = scene["last_frame"]
    elif refs:
        payload["mode"] = "reference"
        for k in refs:
            payload[k] = scene[k]
    else:
        payload["mode"] = "text"
    return payload


def create_task(scene, attempt):
    code, d = req("POST", f"{BASE}/videos", build_payload(scene), timeout=90)
    if code == 200 and d.get("video_id"):
        return d["video_id"]
    log_err = d.get("error", d)
    return None, f"HTTP {code} {log_err}"


def poll_until_done(vid, scene_id, max_wait=3600):
    url = f"{BASE}/agnesapi?video_id={vid}&model_name={MODEL}"
    deadline = time.time() + max_wait
    last = None
    while time.time() < deadline:
        code, d = req("GET", url, timeout=60)
        if code != 200:
            time.sleep(30 if code == 429 else 8)
            continue
        st, pr = d.get("status"), d.get("progress")
        if (st, pr) != last:
            log_msg = f"  {scene_id} status={st} progress={pr}"
            print(log_msg, flush=True)
            last = (st, pr)
        if st == "completed" and d.get("url"):
            return d["url"], None
        if st == "failed":
            return None, d.get("error") or "failed"
        time.sleep(8)
    return None, "poll timeout"


def ensure_segment(root, seg_dir, scene, logfn):
    sid = scene["id"]
    out = os.path.join(seg_dir, f"{sid}.mp4")
    if os.path.exists(out) and os.path.getsize(out) > 100_000:
        logfn(f"{sid} already done")
        return True
    meta_path = os.path.join(seg_dir, f"{sid}.video_id")
    vid = open(meta_path).read().strip() if os.path.exists(meta_path) else None
    vid = vid or None
    attempt = 0
    while True:
        attempt += 1
        if vid is None:
            code, d = req("POST", f"{BASE}/videos", build_payload(scene), timeout=90)
            if code == 200 and d.get("video_id"):
                vid = d["video_id"]
                open(meta_path, "w").write(vid)
                logfn(f"{sid} CREATED {vid}")
            else:
                logfn(f"  create attempt {attempt}: HTTP {code} {d.get('error', d)}")
                time.sleep(min(45, 8 + (attempt % 12) * 3))
                continue
        vurl, err = poll_until_done(vid, sid, max_wait=3600)
        if vurl:
            download(vurl, out)
            logfn(f"{sid} SAVED {out} ({os.path.getsize(out)} bytes)")
            return True
        logfn(f"{sid} task problem: {err}")
        if err == "poll timeout":
            time.sleep(5)
            continue
        try:
            os.remove(meta_path)
        except OSError:
            pass
        vid = None
        time.sleep(5)


def main():
    global KEY
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--scenes", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    scenes_path = args.scenes or os.path.join(root, "scenes.json")
    seg_dir = args.out or os.path.join(root, "segments")
    os.makedirs(seg_dir, exist_ok=True)
    KEY = load_key()
    scenes = json.load(open(scenes_path))
    logfn = lambda m: log(root, m)
    modes = {}
    for s in scenes:
        p = build_payload(s)
        modes.setdefault(p["mode"], []).append(s["id"])
    logfn(f"start pipeline with {len(scenes)} scenes; modes={modes}")
    pending = list(scenes)
    rounds = 0
    while pending:
        rounds += 1
        logfn(f"round {rounds}, pending={[s['id'] for s in pending]}")
        nxt = []
        for s in pending:
            if not ensure_segment(root, seg_dir, s, logfn):
                nxt.append(s)
        pending = nxt
        if pending:
            logfn(f"still pending: {[s['id'] for s in pending]}, sleeping 20s")
            time.sleep(20)
    logfn("ALL SEGMENTS DONE")
    open(os.path.join(root, "ALL_DONE"), "w").write(str(time.time()))


if __name__ == "__main__":
    main()