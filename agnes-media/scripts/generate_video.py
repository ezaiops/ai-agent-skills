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
import argparse, json, os, random, sys, time, urllib.request, urllib.error

BASE = "https://apihub.agnes-ai.com/v1"
MODEL = "agnes-video-2.5-flash"
AUTH = os.path.expanduser("~/.local/share/opencode/auth.json")

# --- Retry/wait budget ---
# Normal retry pace: 60~90s per attempt.
# After a random 5~10 consecutive failures, pause for 1~2 hours (random),
# reset the counter, and resume. Success resets the counter.
WAIT_FAST = (60, 90)
WAIT_COOLDOWN = (3600, 7200)
FAIL_MIN, FAIL_MAX = 5, 10


class Backoff:
    """Success resets the consecutive-failure counter. Every time the random
    failure threshold (5~10) is reached, reset and return a 1~2h cooldown."""

    def __init__(self):
        self._fails = 0
        self._threshold = random.randint(FAIL_MIN, FAIL_MAX)

    def record_success(self):
        self._fails = 0

    def record_failure(self):
        self._fails += 1

    def next(self):
        if self._fails >= self._threshold:
            self._fails = 0
            self._threshold = random.randint(FAIL_MIN, FAIL_MAX)
            return random.randint(*WAIT_COOLDOWN)
        return random.randint(*WAIT_FAST)


def is_account_restricted(code, err=""):
    return code == 403 or "restricted" in str(err).lower()


def load_key():
    with open(AUTH) as f:
        return json.load(f)["agnes"]["key"]


KEY = None


class AccountRestricted(Exception):
    """Raised when the API reports an account-level block (HTTP 403)."""


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
    """Download with retries — SSL handshake timeouts / truncated reads happen on
    large video files and must not kill the whole pipeline."""
    tmp = path + ".part"
    last = None
    for attempt in range(1, 9):
        try:
            with urllib.request.urlopen(url, timeout=300) as resp, open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            os.replace(tmp, path)
            return
        except Exception as e:  # noqa: BLE001 - any network error should retry
            last = e
            try:
                os.remove(tmp)
            except OSError:
                pass
            wait = min(60, 5 * attempt)
            print(f"  download attempt {attempt} failed: {e!r} — retry in {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"download failed after retries: {last}")


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
    bo = Backoff()
    while time.time() < deadline:
        code, d = req("GET", url, timeout=60)
        if is_account_restricted(code, d.get("error", "") if isinstance(d, dict) else d):
            return None, f"account restricted (HTTP {code})"
        if code != 200:
            bo.record_failure()
            wait = bo.next()
            print(f"  {scene_id} HTTP {code}, wait {wait}s", flush=True)
            time.sleep(wait)
            continue
        bo.record_success()
        st, pr = d.get("status"), d.get("progress")
        if (st, pr) != last:
            log_msg = f"  {scene_id} status={st} progress={pr}"
            print(log_msg, flush=True)
            last = (st, pr)
        if st == "completed" and d.get("url"):
            return d["url"], None
        if st == "failed":
            return None, d.get("error") or "failed"
        time.sleep(bo.next())
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
    bo = Backoff()
    attempt = 0
    while True:
        attempt += 1
        if vid is None:
            code, d = req("POST", f"{BASE}/videos", build_payload(scene), timeout=90)
            if code == 200 and d.get("video_id"):
                vid = d["video_id"]
                open(meta_path, "w").write(vid)
                bo.record_success()
                logfn(f"{sid} CREATED {vid}")
            elif is_account_restricted(code, d.get("error", "") if isinstance(d, dict) else d):
                logfn(f"{sid} create blocked by account restriction (HTTP {code}); aborting pipeline")
                raise AccountRestricted(sid)
            else:
                bo.record_failure()
                wait = bo.next()
                logfn(f"  create attempt {attempt}: HTTP {code} {d.get('error', d)} — wait {wait}s")
                time.sleep(wait)
                continue
        vurl, err = poll_until_done(vid, sid, max_wait=3600)
        if vurl:
            download(vurl, out)
            logfn(f"{sid} SAVED {out} ({os.path.getsize(out)} bytes)")
            return True
        logfn(f"{sid} task problem: {err}")
        if "account restricted" in str(err):
            logfn("poll blocked by account restriction; aborting pipeline")
            raise AccountRestricted(sid)
        if err == "poll timeout":
            bo.record_failure()
            wait = bo.next()
            logfn(f"  {sid} poll timeout, next attempt in {wait}s")
            time.sleep(wait)
            continue
        try:
            os.remove(meta_path)
        except OSError:
            pass
        vid = None
        bo.record_failure()
        wait = bo.next()
        logfn(f"  {sid} retry in {wait}s")
        time.sleep(wait)


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
    try:
        while pending:
            rounds += 1
            logfn(f"round {rounds}, pending={[s['id'] for s in pending]}")
            next_pending = []
            for s in pending:
                # serial execution: one scene fully finished before the next starts
                if not ensure_segment(root, seg_dir, s, logfn):
                    next_pending.append(s)
            pending = next_pending
            if pending:
                wait = Backoff().next()
                logfn(f"still pending: {[s['id'] for s in pending]}, sleeping {wait}s")
                time.sleep(wait)
    except AccountRestricted:
        logfn("account restricted; aborting pipeline")
        raise SystemExit(2)
    logfn("ALL SEGMENTS DONE")
    open(os.path.join(root, "ALL_DONE"), "w").write(str(time.time()))


if __name__ == "__main__":
    main()