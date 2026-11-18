#!/usr/bin/env python3
"""Generate recitation-style TTS: natural speech rate, scale only inter-phrase pauses to fill scene.

Parameterized version of xiaoyao/gen_tts_pause.py — pass --root DIR.
"""
import asyncio, argparse, json, os, re, subprocess, tempfile
import edge_tts

VOICE = "zh-CN-YunyangNeural"
RATE = "-25%"           # slower recitation pace
BASE_PAUSE = 0.50       # seconds after a short clause (，、：)
LONG_PAUSE = 0.75       # seconds after a sentence end (。！？；…)
FIT_MARGIN = 0.45       # leave a beat at scene end before crossfade
TARGET_SR = 48000
MAX_GAP = 1.6           # don't make one pause absurdly long

# split after Chinese punctuation, keep the punctuation with the phrase
SPLIT_RE = re.compile(r'(?<=[，。；？！、：…])')

def ffprobe_dur(path):
    r = subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0", path],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())

def phrase_pause(phrase: str) -> float:
    if not phrase:
        return BASE_PAUSE
    if phrase[-1] in "。！？…":
        return LONG_PAUSE
    if phrase[-1] in "，；、：":
        return BASE_PAUSE
    return 0.15  # no punctuation — small breath

async def tts_phrase(text: str, path: str):
    c = edge_tts.Communicate(text, VOICE, rate=RATE)
    await c.save(path)
    if os.path.getsize(path) < 200:
        raise RuntimeError(f"tts empty for phrase: {text!r}")

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    ROOT = os.path.abspath(args.root)
    SEG = os.path.join(ROOT, "segments")
    TTS_RAW = os.path.join(ROOT, "tts")
    TTS_FIT = os.path.join(ROOT, "tts_fit")
    os.makedirs(TTS_RAW, exist_ok=True)
    os.makedirs(TTS_FIT, exist_ok=True)
    scenes = json.load(open(os.path.join(ROOT, "scenes.json")))
    tmpdir = tempfile.mkdtemp(prefix="tts_phrase_")

    for s in scenes:
        sid = s["id"]
        raw_text = s["zh"]
        phrases = [p for p in SPLIT_RE.split(raw_text) if p.strip()]
        # merge orphan fragments (e.g. lone '…') into previous phrase
        merged = []
        for p in phrases:
            if merged and (p in ('…', '...') or len(p) <= 1 and not p[0].isalnum()):
                merged[-1] += p
            else:
                merged.append(p)
        phrases = merged
        print(f"[{sid}] phrases={len(phrases)} {phrases}", flush=True)

        # TTS each phrase at natural rate
        phrase_files = []
        for i, ph in enumerate(phrases):
            mp3 = os.path.join(tmpdir, f"{sid}_{i:02d}.mp3")
            await tts_phrase(ph, mp3)
            phrase_files.append((mp3, phrase_pause(ph)))

        # durations of speech
        durs = [ffprobe_dur(p) for p, _ in phrase_files]
        speech = sum(durs)
        base_gaps = sum(g for _, g in phrase_files[:-1])  # no pause after last phrase
        tail = 0.25
        natural_total = speech + base_gaps + tail

        scene_dur = ffprobe_dur(os.path.join(SEG, f"{sid}.mp4"))
        target = scene_dur - FIT_MARGIN

        # scale only the gaps (not speech) so total ≈ target
        n_gaps = max(1, len(phrase_files) - 1)
        need_extra = target - speech - tail
        if need_extra < n_gaps * 0.12:
            gap_scale = 1.0
            gap_each = [g for _, g in phrase_files[:-1]]
            pad = max(0.0, target - speech - sum(gap_each) - tail)
        else:
            gap_each = [g for _, g in phrase_files[:-1]]
            base_sum = sum(gap_each) or (n_gaps * BASE_PAUSE)
            raw_gaps = [g * (need_extra / base_sum) for g in gap_each] if base_sum else [need_extra/n_gaps]*n_gaps
            gap_each = [min(MAX_GAP, max(0.2, g)) for g in raw_gaps]
            used = sum(gap_each)
            pad = max(0.0, target - speech - used - tail)
            gap_scale = used / base_sum if base_sum else 1.0

        print(f"[{sid}] speech={speech:.2f}s gaps={sum(gap_each):.2f}s "
              f"pad={pad:.2f}s target={target:.2f}s scene={scene_dur:.2f}s", flush=True)

        wavs = []
        for i, ((mp3, _), g) in enumerate(zip(phrase_files, gap_each + [0])):
            wav = os.path.join(tmpdir, f"{sid}_{i:02d}.wav")
            subprocess.run(
                ["ffmpeg","-y","-i",mp3,"-ar",str(TARGET_SR),"-ac","2", wav],
                check=True, capture_output=True)
            wavs.append(wav)
            if g > 0.01 and i < len(gap_each):
                sil = os.path.join(tmpdir, f"{sid}_{i:02d}_sil.wav")
                subprocess.run(
                    ["ffmpeg","-y","-f","lavfi",
                     "-i", f"anullsrc=r={TARGET_SR}:cl=stereo:d={g:.3f}", sil],
                    check=True, capture_output=True)
                wavs.append(sil)
        if pad > 0.01:
            sil = os.path.join(tmpdir, f"{sid}_pad.wav")
            subprocess.run(
                ["ffmpeg","-y","-f","lavfi",
                 "-i", f"anullsrc=r={TARGET_SR}:cl=stereo:d={pad:.3f}", sil],
                check=True, capture_output=True)
            wavs.append(sil)

        clist = os.path.join(tmpdir, f"{sid}_list.txt")
        with open(clist, "w") as f:
            for w in wavs:
                f.write(f"file '{w}'\n")
        joined = os.path.join(tmpdir, f"{sid}_joined.wav")
        subprocess.run(
            ["ffmpeg","-y","-f","concat","-safe","0","-i",clist,"-c","copy", joined],
            check=True, capture_output=True)

        # per-phrase speech windows (for timed subtitles)
        times = []
        t = 0.0
        for i, ((mp3, _), g) in enumerate(zip(phrase_files, gap_each + [0])):
            d = durs[i]
            times.append({
                "text": phrases[i],
                "start": round(t, 3),
                "end": round(t + d, 3),
            })
            t += d
            if i < len(gap_each):
                t += gap_each[i]
        with open(os.path.join(TTS_FIT, f"{sid}.times.json"), "w") as f:
            json.dump({"target": round(target, 3), "phrases": times}, f, ensure_ascii=False, indent=2)

        out = os.path.join(TTS_FIT, f"{sid}.m4a")
        subprocess.run(
            ["ffmpeg","-y","-i",joined,
             "-af", f"atrim=0:{target:.3f},apad=whole_dur={target:.3f},aresample={TARGET_SR}",
             "-ar",str(TARGET_SR),"-ac","2","-c:a","aac","-b:a","192k", out],
            check=True, capture_output=True)

        joined_mp3 = os.path.join(TTS_RAW, f"{sid}.mp3")
        subprocess.run(
            ["ffmpeg","-y","-i",joined,"-c:a","libmp3lame","-q:a","2", joined_mp3],
            check=True, capture_output=True)

        out_dur = ffprobe_dur(out)
        print(f"[{sid}] natural={natural_total:.2f}s -> fit={out_dur:.2f}s", flush=True)

    print("ALL DONE")

if __name__ == "__main__":
    asyncio.run(main())