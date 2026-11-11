#!/usr/bin/env python3
"""Stitch segments: subtitle drawtext, optional TTS mix, xfade+acrossfade chain.

Usage:
  python3 stitch.py [--root DIR] [--out final.mp4] [--font PATH] [--xfade 1.0] [--fps 24]

Reads {root}/scenes.json, {root}/segments/{id}.mp4, optional {root}/tts_fit/{id}.m4a.
"""
import argparse, json, os, subprocess, sys


def ffprobe_dur(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def esc_drawtext(text):
    return (text.replace("\\", "\\\\").replace("'", "\\'")
                .replace(":", "\\:").replace("%", "%%"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--out", default=None)
    ap.add_argument("--font", default="/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc")
    ap.add_argument("--xfade", type=float, default=1.0)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--fontsize", type=int, default=36)
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    seg = os.path.join(root, "segments")
    tts_dir = os.path.join(root, "tts_fit")
    frames = os.path.join(root, "frames")
    out = args.out or os.path.join(os.path.dirname(root), "out.mp4")
    if not args.out and root.rstrip("/").endswith("xiaoyao"):
        out = "/data/home/videospace/xiaoyou_you.mp4"
    os.makedirs(frames, exist_ok=True)
    xfade = args.xfade
    fps = args.fps

    scenes = json.load(open(os.path.join(root, "scenes.json")))
    segs = []
    for s in scenes:
        p = os.path.join(seg, f"{s['id']}.mp4")
        if not os.path.exists(p):
            print("missing", p)
            sys.exit(1)
        segs.append(p)

    probes = []
    for p in segs:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", p],
            capture_output=True, text=True)
        w, h = map(int, r.stdout.strip().split(",")[:2])
        probes.append((w, h))
    W = min(w for w, _ in probes)
    H = min(h for _, h in probes)
    W -= W % 2
    H -= H % 2

    norm = []
    for s, p in zip(scenes, segs):
        sid = s["id"]
        npath = os.path.join(frames, f"{sid}_n.mp4")
        tts_path = os.path.join(tts_dir, f"{sid}.m4a")
        text = esc_drawtext(s.get("zh") or s.get("subtitle") or "")
        draw = (
            f"drawtext=fontfile='{args.font}':text='{text}':"
            f"fontcolor=white:fontsize={args.fontsize}:borderw=2:bordercolor=black@0.7:"
            f"x=(w-text_w)/2:y=h-70:box=1:boxcolor=black@0.35:boxborderw=12"
        )
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
              f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},{draw}")

        has_tts = os.path.exists(tts_path) and os.path.getsize(tts_path) > 500
        if has_tts:
            fc = (
                f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},{draw}[vout];"
                f"[0:a]aresample=48000,pan=stereo|c0=c0|c1=c1,volume=0.25[bg];"
                f"[1:a]aresample=48000,pan=stereo|c0=c0|c1=c1,apad[voice];"
                f"[bg][voice]amix=inputs=2:duration=first:dropout_transition=3:normalize=0[aout]"
            )
            cmd = [
                "ffmpeg", "-y", "-i", p, "-i", tts_path,
                "-filter_complex", fc,
                "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                npath,
            ]
        else:
            cmd = [
                "ffmpeg", "-y", "-i", p, "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                npath,
            ]
        print("normalize", sid, "tts=" + ("yes" if has_tts else "no"), flush=True)
        subprocess.run(cmd, check=True)
        norm.append(npath)

    inputs = []
    for p in norm:
        inputs += ["-i", p]

    durs = [ffprobe_dur(p) for p in norm]
    print("durs", durs, "total without fade", sum(durs))

    fc = []
    prev = "[0:v]"
    prev_a = "[0:a]"
    total = durs[0]
    for i in range(1, len(norm)):
        off = durs[0] - xfade if i == 1 else sum(durs[:i]) - i * xfade
        outl = f"[v{i}]"
        fc.append(f"{prev}[{i}:v]xfade=transition=fade:duration={xfade}:offset={off:.3f}{outl}")
        prev = outl
        outa = f"[a{i}]"
        fc.append(f"{prev_a}[{i}:a]acrossfade=d={xfade}:c1=tri:c2=tri{outa}")
        prev_a = outa
        total = sum(durs[:i + 1]) - i * xfade

    if prev == "[0:v]":
        subprocess.run(
            ["ffmpeg", "-y"] + inputs +
            ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-c:a", "aac", "-b:a", "192k", out],
            check=True,
        )
    else:
        fcmap = ";".join(fc)
        cmd = (
            ["ffmpeg", "-y"] + inputs +
            ["-filter_complex", fcmap,
             "-map", prev, "-map", prev_a,
             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", out]
        )
        print("filter", fcmap)
        subprocess.run(cmd, check=True)
    print("OUT", out, os.path.getsize(out), "expected~", total)


if __name__ == "__main__":
    main()
