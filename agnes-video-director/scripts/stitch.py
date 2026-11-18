#!/usr/bin/env python3
"""Stitch segments with crossfade + timed per-phrase subtitle + TTS mixed over ambient.

Parameterized version of xiaoyao/stitch.py — pass --root DIR [--out FILE].
"""
import json, argparse, os, subprocess, sys

FONT = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
XFADE = 1.0  # seconds overlap
FPS = 24
FONT_SIZE = 36


def esc_text(text: str) -> str:
    return (text.replace("\\", "\\\\").replace("'", "\\'")
                .replace(":", "\\:").replace("%", "%%").replace(",", "\\,"))


def drawtext_chain(tts_dir, sid, zh_fallback, frame_w, scene_dur):
    """One drawtext per phrase, each enabled only while that phrase is spoken."""
    times_path = os.path.join(tts_dir, f"{sid}.times.json")
    base = (
        f"drawtext=fontfile='{FONT}':text=%s:"
        f"fontcolor=white:fontsize={FONT_SIZE}:borderw=2:bordercolor=black@0.7:"
        f"x=(w-text_w)/2:y=h-70:box=1:boxcolor=black@0.35:boxborderw=12"
    )
    if os.path.exists(times_path):
        meta = json.load(open(times_path))
        phrases = meta["phrases"]
        parts = []
        for i, ph in enumerate(phrases):
            t0 = float(ph["start"])
            if i + 1 < len(phrases):
                t1 = float(phrases[i + 1]["start"])
            else:
                t1 = min(scene_dur, float(ph["end"]) + 0.40)
            if t1 <= t0:
                t1 = t0 + 1.0 / FPS
            text = esc_text(ph["text"])
            max_chars = max(4, int((frame_w * 0.92) / FONT_SIZE))
            if len(ph["text"]) > max_chars:
                fs = max(18, int(frame_w * 0.92 / len(ph["text"])))
                frag = (
                    f"drawtext=fontfile='{FONT}':text={text}:"
                    f"fontcolor=white:fontsize={fs}:borderw=2:bordercolor=black@0.7:"
                    f"x=(w-text_w)/2:y=h-70:box=1:boxcolor=black@0.35:boxborderw=12"
                )
            else:
                frag = base % text
            frag += f":enable='between(t\\,{t0:.3f}\\,{t1:.3f})'"
            parts.append(frag)
        if parts:
            return ",".join(parts)
    text = esc_text(zh_fallback)
    return base % text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    ROOT = os.path.abspath(args.root)
    SEG = os.path.join(ROOT, "segments")
    TTS_DIR = os.path.join(ROOT, "tts_fit")
    OUT = args.out or os.path.join(ROOT, "final.mp4")
    os.makedirs(os.path.join(ROOT, "frames"), exist_ok=True)

    scenes = json.load(open(os.path.join(ROOT, "scenes.json")))
    segs = []
    for s in scenes:
        p = os.path.join(SEG, f"{s['id']}.mp4")
        if not os.path.exists(p):
            print("missing", p); sys.exit(1)
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
    for i, (s, p) in enumerate(zip(scenes, segs)):
        sid = s["id"]
        npath = os.path.join(ROOT, "frames", f"{sid}_n.mp4")
        tts_path = os.path.join(TTS_DIR, f"{sid}.m4a")
        scene_dur = None
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", p], capture_output=True, text=True)
        if r.stdout.strip():
            scene_dur = float(r.stdout.strip())
        draw = drawtext_chain(TTS_DIR, sid, s["zh"], W, scene_dur or 12.0)
        vf = (
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS},{draw}"
        )

        has_audio = False
        r_audio = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", p],
            capture_output=True, text=True)
        if r_audio.stdout.strip():
            has_audio = True

        if os.path.exists(tts_path) and os.path.getsize(tts_path) > 500:
            if has_audio:
                fc = (
                    f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
                    f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS},{draw}[vout];"
                    f"[0:a]aresample=48000,pan=stereo|c0=c0|c1=c1,volume=0.25[bg];"
                    f"[1:a]aresample=48000,pan=stereo|c0=c0|c1=c1,apad[voice];"
                    f"[bg][voice]amix=inputs=2:duration=first:dropout_transition=3:normalize=0[aout]"
                )
            else:
                fc = (
                    f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
                    f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS},{draw}[vout];"
                    f"anullsrc=r=48000:cl=stereo:d=9999[amb];"
                    f"[amb]atrim=0:{(scene_dur or 12.0):.3f},volume=0.25[bg];"
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
        print("normalize", sid, "tts=" + ("yes" if os.path.exists(tts_path) else "no"), flush=True)
        subprocess.run(cmd, check=True)
        norm.append(npath)

    inputs = []
    for p in norm:
        inputs += ["-i", p]

    durs = []
    for p in norm:
        r = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration",
                            "-of","csv=p=0", p], capture_output=True, text=True)
        durs.append(float(r.stdout.strip()))
    print("durs", durs, "total without fade", sum(durs))

    fc = []
    prev = "[0:v]"
    prev_a = "[0:a]"
    total = durs[0]
    for i in range(1, len(norm)):
        off = durs[0] - XFADE if i == 1 else sum(durs[:i]) - i * XFADE
        outl = f"[v{i}]"
        fc.append(f"{prev}[{i}:v]xfade=transition=fade:duration={XFADE}:offset={off:.3f}{outl}")
        prev = outl
        outa = f"[a{i}]"
        fc.append(f"{prev_a}[{i}:a]acrossfade=d={XFADE}:c1=tri:c2=tri{outa}")
        prev_a = outa
        total = sum(durs[:i+1]) - i * XFADE
    if prev == "[0:v]":
        subprocess.run(
            ["ffmpeg","-y"]+inputs+
            ["-c:v","libx264","-preset","medium","-crf","18",
             "-c:a","aac","-b:a","192k", OUT],
            check=True,
        )
    else:
        fcmap = ";".join(fc)
        cmd = (
            ["ffmpeg","-y"]+inputs+
            ["-filter_complex", fcmap,
             "-map", prev, "-map", prev_a,
             "-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p",
             "-c:a","aac","-b:a","192k", OUT]
        )
        print("filter", fcmap)
        subprocess.run(cmd, check=True)
    print("OUT", OUT, os.path.getsize(OUT), "expected~", total)


if __name__ == "__main__":
    main()