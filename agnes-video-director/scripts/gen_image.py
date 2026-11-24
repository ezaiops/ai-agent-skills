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

Rate limiting (free tier allows only 5 concurrent in-flight requests):
  every call takes a shared cross-process slot (default max 4) and retries
  HTTP 429 / 5xx with exponential backoff. Tune with --max-concurrent and
  --max-attempts. Running many of these in parallel is therefore safe.

Batch mode (one JSON file, capped parallelism):
  python3 gen_image.py --batch jobs.json --max-concurrent 4
  jobs.json = [{"prompt": "...", "out": "a.png", "ratio": "4:3", "size": "1K"}, ...]
"""
import argparse, base64, json, os, sys, time, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _ratelimit import Slot, with_retry, DEFAULT_MAX_CONCURRENT

BASE = "https://apihub.agnes-ai.com/v1"
AUTH = os.path.expanduser("~/.local/share/opencode/auth.json")


def to_data_uri(path):
    mime = "image/png"
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    elif ext == ".webp":
        mime = "image/webp"
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    return f"data:{mime};base64,{b64}"


def generate(prompt, out, model="agnes-image-2.5-flash", size="1K", ratio="16:9",
             images=None, timeout=300, max_concurrent=DEFAULT_MAX_CONCURRENT,
             max_attempts=8, verbose=True):
    key = json.load(open(AUTH))["agnes"]["key"]
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "ratio": ratio,
        "return_base64": True,
    }
    if images:
        imgs = []
        for img in images:
            imgs.append(to_data_uri(img)
                        if not img.startswith(("http://", "https://", "data:")) else img)
        # img2img/multi-image: images live in extra_body.image; use b64 output via extra_body.response_format
        payload["extra_body"] = {"image": imgs, "response_format": "b64_json"}
        payload.pop("return_base64", None)

    def once():
        req = urllib.request.Request(
            f"{BASE}/images/generations",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)

    t = time.time()
    with Slot(max_concurrent=max_concurrent, verbose=verbose):
        d = with_retry(once, max_attempts=max_attempts, verbose=verbose, what=out)

    item = d["data"][0]
    if item.get("b64_json"):
        open(out, "wb").write(base64.b64decode(item["b64_json"]))
    elif item.get("url"):
        urllib.request.urlretrieve(item["url"], out)
    else:
        raise RuntimeError(f"unexpected response: {json.dumps(d)[:300]}")
    if verbose:
        print(f"saved {out} ({os.path.getsize(out)} bytes) in {time.time()-t:.1f}s",
              flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt")
    ap.add_argument("--out", default="image.png")
    ap.add_argument("--model", default="agnes-image-2.5-flash")
    ap.add_argument("--size", default="1K")
    ap.add_argument("--ratio", default="16:9")
    ap.add_argument("--image", action="append", default=None,
                    help="input image: local path (auto Data-URI) or public URL. Repeatable for multi-image.")
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--max-concurrent", type=int, default=DEFAULT_MAX_CONCURRENT,
                    help="max in-flight requests across all processes (server allows 5)")
    ap.add_argument("--max-attempts", type=int, default=8,
                    help="retry attempts on HTTP 429 / 5xx")
    ap.add_argument("--batch", help="JSON file: list of {prompt,out,ratio,size,image}")
    args = ap.parse_args()

    if args.batch:
        jobs = json.load(open(args.batch))
        from concurrent.futures import ThreadPoolExecutor, as_completed
        os.makedirs(os.path.dirname(os.path.abspath(
            os.path.join(os.path.dirname(args.batch), jobs[0].get("out", "x")))), exist_ok=True)
        results, failed = [], []
        with ThreadPoolExecutor(max_workers=args.max_concurrent) as ex:
            futs = {}
            for j in jobs:
                imgs = j.get("image")
                if isinstance(imgs, str):
                    imgs = [imgs]
                futs[ex.submit(
                    generate,
                    j["prompt"], j["out"],
                    j.get("model", args.model), j.get("size", args.size),
                    j.get("ratio", "4:3"), imgs, args.timeout,
                    args.max_concurrent, args.max_attempts,
                )] = j["out"]
            for f in as_completed(futs):
                name = futs[f]
                try:
                    results.append(f.result())
                except Exception as e:
                    failed.append((name, repr(e)[:200]))
                    print(f"FAILED {name}: {repr(e)[:200]}", flush=True)
        print(f"done: {len(results)} ok, {len(failed)} failed")
        if failed:
            print("failed jobs:", failed)
            sys.exit(1)
        return

    if not args.prompt:
        ap.error("--prompt is required unless --batch is used")
    generate(args.prompt, args.out, args.model, args.size, args.ratio, args.image,
             args.timeout, args.max_concurrent, args.max_attempts)


if __name__ == "__main__":
    main()