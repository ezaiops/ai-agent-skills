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
import argparse, base64, json, os, time, urllib.request, urllib.error

BASE = "https://apihub.agnes-ai.com/v1"
AUTH = "/data/home/.local/share/opencode/auth.json"


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
    args = ap.parse_args()

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
