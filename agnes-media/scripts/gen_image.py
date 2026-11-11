#!/usr/bin/env python3
"""Generate one or more images via Agnes images/generations.

Usage:
  python3 gen_image.py --prompt "..." --out out.png
  python3 gen_image.py --prompt "..." --model agnes-image-2.5-flash --ratio 16:9 --size 1K
"""
import argparse, base64, json, os, time, urllib.request, urllib.error

BASE = "https://apihub.agnes-ai.com/v1"
AUTH = "/data/home/.local/share/opencode/auth.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--out", default="image.png")
    ap.add_argument("--model", default="agnes-image-2.5-flash")
    ap.add_argument("--size", default="1K")
    ap.add_argument("--ratio", default="16:9")
    ap.add_argument("--timeout", type=float, default=300)
    args = ap.parse_args()

    key = json.load(open(AUTH))["agnes"]["key"]
    payload = {
        "model": args.model,
        "prompt": args.prompt,
        "size": args.size,
        "ratio": args.ratio,
        "return_base64": True,
    }
    req = urllib.request.Request(
        f"{BASE}/images/generations",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")

    item = d["data"][0]
    if item.get("b64_json"):
        open(args.out, "wb").write(base64.b64decode(item["b64_json"]))
    elif item.get("url"):
        urllib.request.urlretrieve(item["url"], args.out)
    else:
        raise SystemExit(f"unexpected response: {json.dumps(d)[:300]}")
    print(f"saved {args.out} ({os.path.getsize(args.out)} bytes) in {time.time()-t:.1f}s")


if __name__ == "__main__":
    main()
