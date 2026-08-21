"""Clean a transcript and split it into timed syllables for make_karaoke.py.

Three passes, in this order:

  1. **Corrections.** Whisper mishears brand names, clinic names and product
     terms — the words a client will notice first. Fix them against the brief's
     own wording; never invent a correction the brief does not support.
  2. **Overlap.** A scene often has a voiceover laid over footage that is also
     talking. Subtitling both puts two speakers on screen at once, so clip audio
     that a voiceover covers is dropped.
  3. **Syllables.** Each sentence is split with pythainlp and its time span
     shared out by syllable length, which is what drives the highlight.

Usage:
    python prepare_subtitles.py transcript.json out.json [--fixes fixes.json]

fixes.json: {"replace": {"โปรแกม": "โปรแกรม"}, "voiceover": ["C1182.MP4"]}
Clips already marked `"voiceover": true` by read_timeline.py count automatically.
"""

import argparse
import json
import sys


def syllabify(text: str):
    """Split Thai into syllables, keeping every character.

    pythainlp mangles runs containing spaces, so split on whitespace first. A
    split that does not reassemble into the original is discarded — highlight
    ranges are character offsets and cannot survive a dropped character.
    """
    try:
        from pythainlp.tokenize import syllable_tokenize
    except ImportError:
        return text.split()

    out = []
    for chunk in text.split():
        try:
            pieces = [s for s in syllable_tokenize(chunk) if s.strip()]
        except Exception:
            pieces = [chunk]
        out.extend(pieces if "".join(pieces) == chunk else [chunk])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("out")
    ap.add_argument("--fixes")
    args = ap.parse_args()

    with open(args.transcript, encoding="utf-8") as f:
        rows = json.load(f)

    replace, extra_vo = {}, set()
    if args.fixes:
        with open(args.fixes, encoding="utf-8") as f:
            cfg = json.load(f)
        replace = cfg.get("replace") or {}
        extra_vo = set(cfg.get("voiceover") or [])

    for r in rows:
        for bad, good in replace.items():
            if bad in r["text"]:
                print(f"  fix: {bad} -> {good}")
                r["text"] = r["text"].replace(bad, good)

    def is_vo(r):
        return bool(r.get("voiceover")) or r["clip"] in extra_vo

    vo_spans = [(r["start"], r["end"]) for r in rows if is_vo(r)]

    kept = []
    for r in sorted(rows, key=lambda r: r["start"]):
        # Any real overlap counts — half a competing sentence still collides.
        if not is_vo(r) and any(r["start"] < e and r["end"] > s
                                for s, e in vo_spans):
            print(f"  drop (voiceover covers it): {r['start']:.2f}s "
                  f"{r['text'][:40]}")
            continue
        if r["text"].strip():
            kept.append(r)

    words = []
    for r in kept:
        pieces = syllabify(" ".join(r["text"].split()))
        if not pieces:
            continue
        span = max(r["end"] - r["start"], 0.2)
        total = sum(len(p) for p in pieces) or 1
        t = r["start"]
        for p in pieces:
            d = span * (len(p) / total)
            words.append({"text": p, "start": round(t, 3),
                          "end": round(t + d, 3), "clip": r["clip"]})
            t += d

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=2)

    print(f"\n{len(kept)} sentences -> {len(words)} syllables -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
