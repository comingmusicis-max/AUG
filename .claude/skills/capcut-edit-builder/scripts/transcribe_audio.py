"""Transcribe a timeline's audible clips, reporting times in timeline seconds.

Whisper times everything inside each source file; a subtitle track needs to know
where that speech lands on the timeline, so every result is shifted by the clip's
placement and clipped to the portion actually used.

Two things about Thai are worth knowing before reading the output:

  * `segment.text` is properly decoded, but the per-word entries are sub-word
    tokens that drop tone marks when taken alone (หน้าแห้ง arrives as ห, น, ้, า…).
    Both are saved — sentences for what goes on screen, tokens for timing.
  * Recognition of brand names and clinic names is unreliable. Correct them
    against the client's brief in prepare_subtitles.py rather than shipping
    whatever came out.

Usage:
    python transcribe_audio.py clips.json out.json [--model PATH] [--language th]

clips.json: [{"path", "timeline", "src", "len", "voiceover"}] — read_timeline.py
writes this straight out of an existing draft.
"""

import argparse
import json
import os
import sys

DEFAULT_MODEL = os.environ.get("WHISPER_MODEL", "medium")


def load_model(spec: str):
    """Load Whisper, retrying a few times.

    A half-written model file and failing RAM both surface here as the same
    RuntimeError. Retrying separates them: flaky hardware usually succeeds
    within a couple of attempts, a corrupt file never does.
    """
    from faster_whisper import WhisperModel

    last = None
    for attempt in range(1, 4):
        try:
            return WhisperModel(spec, device="cpu", compute_type="int8",
                                num_workers=1)
        except RuntimeError as exc:
            last = exc
            print(f"  load attempt {attempt} failed: {exc}", flush=True)
    raise SystemExit(
        f"could not load the model: {last}\n"
        "If this says 'Invalid string length in model.bin', the download is "
        "corrupt — verify its SHA256 against the Hugging Face API before reusing "
        "it. Repeated corruption of large files points at faulty RAM."
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("clips")
    ap.add_argument("out")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--language", default="th")
    ap.add_argument("--beam", type=int, default=5)
    args = ap.parse_args()

    with open(args.clips, encoding="utf-8") as f:
        clips = json.load(f)

    # Results are flushed after every clip and finished clips are skipped on a
    # re-run, so an interrupted pass costs one clip rather than all of them.
    results, done = [], set()
    if os.path.exists(args.out):
        try:
            with open(args.out, encoding="utf-8") as f:
                results = json.load(f)
            done = {r["clip"] for r in results}
            print(f"resuming — {len(done)} clip(s) already done", flush=True)
        except (OSError, ValueError):
            results = []

    def save():
        results.sort(key=lambda r: r["start"])
        tmp = args.out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        os.replace(tmp, args.out)

    pending = [c for c in clips if os.path.basename(c["path"]) not in done]
    if not pending:
        print(f"nothing to do — {len(results)} sentences in {args.out}")
        return 0

    print(f"loading {args.model}", flush=True)
    model = load_model(args.model)

    for c in pending:
        path, t0, s0, dur = c["path"], c["timeline"], c.get("src", 0.0), c["len"]
        name = os.path.basename(path)
        print(f"\n{name}  timeline {t0:.2f}s", flush=True)

        segments, _ = model.transcribe(
            path, language=args.language, word_timestamps=True,
            vad_filter=True, beam_size=args.beam,
        )
        for seg in segments:
            if seg.end < s0 or seg.start > s0 + dur:
                continue
            start = t0 + (max(seg.start, s0) - s0)
            end = t0 + (min(seg.end, s0 + dur) - s0)
            tokens = [
                {"text": w.word,
                 "start": round(t0 + (max(w.start, s0) - s0), 3),
                 "end": round(t0 + (min(w.end, s0 + dur) - s0), 3)}
                for w in (seg.words or [])
                if not (w.end < s0 or w.start > s0 + dur)
            ]
            results.append({
                "text": seg.text.strip(), "start": round(start, 3),
                "end": round(end, 3), "clip": name,
                "voiceover": bool(c.get("voiceover")), "tokens": tokens,
            })
            print(f"   {start:6.2f}-{end:6.2f}  {seg.text.strip()}", flush=True)

        save()

    print(f"\ndone — {len(results)} sentences -> {args.out}")
    print("Review the text before building subtitles: names and product terms "
          "are the parts Whisper gets wrong.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
