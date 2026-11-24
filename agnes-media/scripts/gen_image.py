#!/usr/bin/env python3
"""Generate one or more images via Agnes images/generations.

Text-to-image (default):
  python3 gen_image.py --prompt "..." --out out.png
  python3 gen_image.py --prompt "..." --model agnes-image-2.5-flash --ratio 16:9 --size 1K

Image-to-image (img2img): pass --image with a local path (auto Data-URI) or URL.
  Use it to keep a character/scene while changing pose, mood, or lighting:
  python3 gen_image.py --prompt "Same old Daoist scholar, now sitting upright..." \
      --image ref.png --out out.png

Multi-image composition: repeat --image ref1.png --image ref2.png ...
"""
import argparse, base64, http.client, json, os, random, time, urllib.request, urllib.error

BASE = "https://apihub.agnes-ai.com/v1"
AUTH = os.path.expanduser("~/.local/share/opencode/auth.json")

# --- Retry/wait budget ---
# Normal retry pace: 60~90s per attempt.
# After FAIL_RESET consecutive failures take a long cooldown (10~20 min),
# then resume the fast 60~90s pace. Repeats: 20 fast, cooldown, 20 fast, ...
WAIT_FAST = (60, 90)
WAIT_COOLDOWN = (600, 1200)
FAIL_RESET = 20
RETRY_ERRORS = (urllib.error.HTTPError, TimeoutError, ConnectionError, OSError, http.client.HTTPException)

# Minimum gap enforced between two *successful* generations (cross-process).
# Even if calls are scripted back-to-back, the next request waits until at least
# this many seconds have passed since the previous image was generated.
MIN_GAP_BETWEEN_IMAGES = 60
GAP_STATE_FILE = os.path.expanduser("~/.cache/agnes-image-gap")


def respect_min_gap(min_gap=MIN_GAP_BETWEEN_IMAGES, state_file=GAP_STATE_FILE):
    """Sleep so that consecutive image generations are >= min_gap apart."""
    last = None
    try:
        with open(state_file) as f:
            last = float(f.read().strip())
    except (OSError, ValueError):
        pass
    now = time.time()
    if last is not None:
        elapsed = now - last
        if elapsed < min_gap:
            wait = min_gap - elapsed
            print(f"[min-gap] last image {elapsed:.0f}s ago, wait {wait:.0f}s before next request", flush=True)
            time.sleep(wait)
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, "w") as f:
        f.write(str(time.time()))


class Backoff:
    """Success resets the consecutive-failure counter; every FAIL_RESET-th
    consecutive failure returns a long cooldown wait."""

    def __init__(self):
        self._fails = 0

    def record_success(self):
        self._fails = 0

    def record_failure(self):
        self._fails += 1

    def next(self):
        if self._fails and self._fails % FAIL_RESET == 0:
            return random.randint(*WAIT_COOLDOWN)
        return random.randint(*WAIT_FAST)


def to_data_uri(path):
    mime = "image/png"
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    elif ext == ".webp":
        mime = "image/webp"
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    return f"data:{mime};base64,{b64}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--out", default="image.png")
    ap.add_argument("--model", default="agnes-image-2.5-flash")
    ap.add_argument("--size", default="1K")
    ap.add_argument("--ratio", default="16:9")
    ap.add_argument("--image", action="append", default=None,
                    help="input image: local path (auto Data-URI) or public URL. Repeatable for multi-image.")
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--min-gap", type=float, default=MIN_GAP_BETWEEN_IMAGES,
                    help=f"min seconds between two image generations (default {MIN_GAP_BETWEEN_IMAGES})")
    args = ap.parse_args()

    respect_min_gap(min_gap=args.min_gap)

    key = json.load(open(AUTH))["agnes"]["key"]
    payload = {
        "model": args.model,
        "prompt": args.prompt,
        "size": args.size,
        "ratio": args.ratio,
        "return_base64": True,
    }
    if args.image:
        imgs = []
        for img in args.image:
            imgs.append(to_data_uri(img) if not img.startswith(("http://", "https://", "data:")) else img)
        # img2img/multi-image: images live in extra_body.image; use b64 output via extra_body.response_format
        payload["extra_body"] = {"image": imgs, "response_format": "b64_json"}
        payload.pop("return_base64", None)
    req = urllib.request.Request(
        f"{BASE}/images/generations",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    t = time.time()
    bo = Backoff()
    attempt = 0
    while True:
        attempt += 1
        try:
            with urllib.request.urlopen(req, timeout=args.timeout) as r:
                d = json.load(r)
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:500]
            if e.code == 403 or "restricted" in body.lower():
                raise SystemExit(f"HTTP {e.code}: account restricted, aborting. {body}")
            bo.record_failure()
            wait = bo.next()
            print(f"attempt {attempt}: HTTP {e.code} — wait {wait}s")
            time.sleep(wait)
        except RETRY_ERRORS as e:
            bo.record_failure()
            wait = bo.next()
            print(f"attempt {attempt}: {e!r} — wait {wait}s")
            time.sleep(wait)

    bo.record_success()

    item = d["data"][0]
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    if item.get("b64_json"):
        open(args.out, "wb").write(base64.b64decode(item["b64_json"]))
    elif item.get("url"):
        urllib.request.urlretrieve(item["url"], args.out)
    else:
        raise SystemExit(f"unexpected response: {json.dumps(d)[:300]}")
    print(f"saved {args.out} ({os.path.getsize(args.out)} bytes) in {time.time()-t:.1f}s")


if __name__ == "__main__":
    main()
