#!/usr/bin/env python3
"""Recitation-style edge-tts: natural phrase rate, scale only inter-phrase pauses to fit scene.

Usage:
  python3 gen_tts_pause.py [--root DIR] [--voice ...] [--rate -25%]

Reads {root}/scenes.json (fields: id, zh) and {root}/segments/{id}.mp4 (for duration).
Writes {root}/tts_fit/{id}.m4a (exact target duration) and {root}/tts/{id}.mp3 (natural join).

Approved defaults: voice zh-CN-YunyangNeural, rate -25%, clause 0.50s, sentence 0.75s.
"""
import argparse, asyncio, json, os, re, subprocess, tempfile
import edge_tts

SPLIT_RE = re.compile(r'(?<=[，。；？！、：…])')


def ffprobe_dur(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def phrase_pause(phrase, base, long_):
    if not phrase:
        return base
    if phrase[-1] in "。！？…":
        return long_
    if phrase[-1] in "，；、：":
        return base
    return 0.15


def merge_phrases(raw_text):
    phrases = [p for p in SPLIT_RE.split(raw_text) if p.strip()]
    merged = []
    for p in phrases:
        if merged and (p in ("…", "...") or (len(p) <= 1 and not p[0].isalnum())):
            merged[-1] += p
        else:
            merged.append(p)
    return merged


async def tts_phrase(text, path, voice, rate):
    c = edge_tts.Communicate(text, voice, rate=rate)
    await c.save(path)
    if os.path.getsize(path) < 200:
        raise RuntimeError(f"tts empty for phrase: {text!r}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--voice", default="zh-CN-YunyangNeural")
    ap.add_argument("--rate", default="-25%")
    ap.add_argument("--base-pause", type=float, default=0.50)
    ap.add_argument("--long-pause", type=float, default=0.75)
    ap.add_argument("--max-gap", type=float, default=1.6)
    ap.add_argument("--fit-margin", type=float, default=0.45)
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    seg = os.path.join(root, "segments")
    tts_raw = os.path.join(root, "tts")
    tts_fit = os.path.join(root, "tts_fit")
    target_sr = 48000
    os.makedirs(tts_raw, exist_ok=True)
    os.makedirs(tts_fit, exist_ok=True)
    scenes = json.load(open(os.path.join(root, "scenes.json")))
    tmpdir = tempfile.mkdtemp(prefix="tts_phrase_")

    for s in scenes:
        sid = s["id"]
        phrases = merge_phrases(s["zh"])
        print(f"[{sid}] phrases={len(phrases)} {phrases}", flush=True)

        phrase_files = []
        for i, ph in enumerate(phrases):
            mp3 = os.path.join(tmpdir, f"{sid}_{i:02d}.mp3")
            await tts_phrase(ph, mp3, args.voice, args.rate)
            phrase_files.append((mp3, phrase_pause(ph, args.base_pause, args.long_pause)))

        durs = [ffprobe_dur(p) for p, _ in phrase_files]
        speech = sum(durs)
        tail = 0.25
        natural_total = speech + sum(g for _, g in phrase_files[:-1]) + tail

        scene_path = os.path.join(seg, f"{sid}.mp4")
        if not os.path.exists(scene_path):
            raise SystemExit(f"missing segment {scene_path}; run generate_video.py first")
        scene_dur = ffprobe_dur(scene_path)
        target = scene_dur - args.fit_margin

        n_gaps = max(1, len(phrase_files) - 1)
        gap_each = [g for _, g in phrase_files[:-1]]
        need_extra = target - speech - tail
        if need_extra >= n_gaps * 0.12:
            base_sum = sum(gap_each) or (n_gaps * args.base_pause)
            raw_gaps = [g * (need_extra / base_sum) for g in gap_each] if base_sum else [need_extra / n_gaps] * n_gaps
            gap_each = [min(args.max_gap, max(0.2, g)) for g in raw_gaps]
        pad = max(0.0, target - speech - sum(gap_each) - tail)

        print(f"[{sid}] speech={speech:.2f}s gaps={sum(gap_each):.2f}s "
              f"pad={pad:.2f}s target={target:.2f}s scene={scene_dur:.2f}s", flush=True)

        wavs = []
        for i, ((mp3, _), g) in enumerate(zip(phrase_files, gap_each + [0])):
            wav = os.path.join(tmpdir, f"{sid}_{i:02d}.wav")
            subprocess.run(["ffmpeg", "-y", "-i", mp3, "-ar", str(target_sr), "-ac", "2", wav],
                           check=True, capture_output=True)
            wavs.append(wav)
            if g > 0.01 and i < len(gap_each):
                sil = os.path.join(tmpdir, f"{sid}_{i:02d}_sil.wav")
                subprocess.run(
                    ["ffmpeg", "-y", "-f", "lavfi",
                     "-i", f"anullsrc=r={target_sr}:cl=stereo:d={g:.3f}", sil],
                    check=True, capture_output=True)
                wavs.append(sil)
        if pad > 0.01:
            sil = os.path.join(tmpdir, f"{sid}_pad.wav")
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi",
                 "-i", f"anullsrc=r={target_sr}:cl=stereo:d={pad:.3f}", sil],
                check=True, capture_output=True)
            wavs.append(sil)

        clist = os.path.join(tmpdir, f"{sid}_list.txt")
        with open(clist, "w") as f:
            for w in wavs:
                f.write(f"file '{w}'\n")
        joined = os.path.join(tmpdir, f"{sid}_joined.wav")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", clist,
                        "-c", "copy", joined], check=True, capture_output=True)

        out = os.path.join(tts_fit, f"{sid}.m4a")
        subprocess.run(
            ["ffmpeg", "-y", "-i", joined,
             "-af", f"atrim=0:{target:.3f},apad=whole_dur={target:.3f},aresample={target_sr}",
             "-ar", str(target_sr), "-ac", "2", "-c:a", "aac", "-b:a", "192k", out],
            check=True, capture_output=True)

        joined_mp3 = os.path.join(tts_raw, f"{sid}.mp3")
        subprocess.run(["ffmpeg", "-y", "-i", joined, "-c:a", "libmp3lame", "-q:a", "2", joined_mp3],
                       check=True, capture_output=True)
        print(f"[{sid}] natural={natural_total:.2f}s -> fit={ffprobe_dur(out):.2f}s", flush=True)

    print("ALL DONE")


if __name__ == "__main__":
    asyncio.run(main())
