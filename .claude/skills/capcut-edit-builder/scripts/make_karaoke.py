"""Add syllable-highlighted (karaoke) subtitles to an existing CapCut draft.

The effect: the whole line sits on screen in grey, and the syllable being spoken
right now is pink and a step larger — "โปร" lights up, then drops back to grey as
"แกรม" takes over. CapCut renders this from a single text material carrying two
style ranges, so each syllable is one short segment showing the same line with a
different range highlighted.

Timings can come from either:
  --words  transcript JSON  [{"text","start","end"}, ...]  (timeline seconds)
  --from-track N            reuse the timings of an existing text track

Never edits the source project: output always goes to a new draft folder, since
the source usually holds hours of an editor's own work.

Usage:
    python make_karaoke.py <source-project-name> <new-project-name> \
        [--words words.json | --from-track 4] [--track-name "ซับ"]
"""

import argparse
import json
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_draft import (  # noqa: E402
    US, DEFAULT_DRAFT_ROOT, MATERIAL_BUCKETS, uid, hex_to_rgb, segment,
    capcut_running,
)

# Defaults lifted from the editor's own hand-made subtitles, so generated lines
# sit in the same place and read the same as the ones already on the timeline.
STYLE = {
    "font": "C:/Users/mueth/AppData/Local/Microsoft/Windows/Fonts/"
            "DB Heavent Blk Cond v3.2.1.ttf",
    "active_color": "#ff68a3", "active_size": 17.0,
    "idle_color": "#3f3f3f", "idle_size": 15.0,
    "stroke": "#ffffff", "stroke_width": 0.0253,
    "scale": 2.0839565589996973, "y": -0.4354446177847114,
}

# Below this a highlight reads as a flicker rather than a beat.
MIN_SYLLABLE = 0.12
# A pause longer than this ends the on-screen line.
LINE_GAP = 0.40
# Thai has no spaces, so lines are capped by character count instead of words.
LINE_MAX_CHARS = 16


def syllabify(text: str):
    """Split Thai text into syllables, keeping every character accounted for.

    pythainlp gets Thai right — โปรแกรม becomes โปร + แกรม, exactly the beat the
    highlight should follow — but it mangles runs that contain spaces, so split
    on whitespace first and hand back the separators as their own pieces. The
    concatenation of the result has to equal the input, because highlight ranges
    are character offsets into the original line.
    """
    try:
        from pythainlp.tokenize import syllable_tokenize
    except ImportError:
        return [text]

    out = []
    for part in re.split(r"(\s+)", text):
        if not part:
            continue
        if part.isspace():
            out.append(part)
            continue
        try:
            pieces = [s for s in syllable_tokenize(part) if s]
        except Exception:
            pieces = [part]
        # Only trust the split when nothing was dropped or invented.
        out.extend(pieces if "".join(pieces) == part else [part])
    return out or [text]


def text_material(line: str, hi_start: int, hi_end: int) -> dict:
    """One text material: the whole line grey, [hi_start, hi_end) pink."""
    def style(rng, color, size):
        return {
            "fill": {"content": {"render_type": "solid",
                                 "solid": {"color": hex_to_rgb(color)}}},
            "font": {"path": STYLE["font"], "id": ""},
            "strokes": [{"content": {"render_type": "solid",
                                     "solid": {"color": hex_to_rgb(STYLE["stroke"])}},
                         "width": STYLE["stroke_width"], "mode": 0}],
            "size": size, "useLetterColor": True, "range": rng,
        }

    styles = []
    if hi_start > 0:
        styles.append(style([0, hi_start], STYLE["idle_color"], STYLE["idle_size"]))
    styles.append(style([hi_start, hi_end], STYLE["active_color"],
                        STYLE["active_size"]))
    if hi_end < len(line):
        styles.append(style([hi_end, len(line)], STYLE["idle_color"],
                            STYLE["idle_size"]))

    return {
        "id": uid(), "type": "text",
        "content": json.dumps({"text": line, "styles": styles},
                              ensure_ascii=False),
        "font_path": STYLE["font"], "font_size": STYLE["idle_size"],
        "text_size": 30, "text_color": STYLE["idle_color"], "text_alpha": 1.0,
        "border_color": STYLE["stroke"], "border_alpha": 1.0,
        "border_width": STYLE["stroke_width"], "border_mode": 0,
        "is_rich_text": True, "alignment": 1, "line_spacing": 0.02,
        "letter_spacing": 0.0, "line_max_width": 0.82, "typesetting": 0,
        "line_feed": 1, "global_alpha": 1.0, "layer_weight": 1,
        "has_shadow": False, "check_flag": 15, "font_title": "none",
        "add_type": 0, "sub_type": 0, "recognize_type": 0, "fonts": [],
        "words": {"start_time": [], "end_time": [], "text": []},
    }


def build_lines(words):
    """Group timed words into on-screen lines, then into timed syllables.

    Each word's own span is subdivided by syllable length, so the highlight
    stays anchored to real speech rather than drifting across a whole line.
    """
    lines, cur = [], []
    for w in words:
        text = (w.get("text") or "").strip()
        if not text:
            continue
        gap = text and cur and w["start"] - cur[-1]["end"] > LINE_GAP
        too_long = sum(len(c["text"]) for c in cur) + len(text) > LINE_MAX_CHARS
        if cur and (gap or too_long):
            lines.append(cur)
            cur = []
        cur.append({"text": text, "start": w["start"], "end": w["end"]})
    if cur:
        lines.append(cur)

    out = []
    for group in lines:
        line = "".join(c["text"] for c in group)
        beats, cursor = [], 0
        for c in group:
            sylls = syllabify(c["text"])
            total = sum(len(s) for s in sylls) or 1
            span = max(c["end"] - c["start"], MIN_SYLLABLE)
            t = c["start"]
            for s in sylls:
                d = span * (len(s) / total)
                # A space gets time but never the highlight — pausing the pink
                # on a gap between words is what makes the effect read as speech.
                if not s.isspace():
                    beats.append({"start": t, "end": t + d,
                                  "range": (cursor, cursor + len(s))})
                elif beats:
                    beats[-1]["end"] += d
                t += d
                cursor += len(s)
        out.append({"line": line, "beats": beats})
    return out


def words_from_track(draft: dict, track_index: int):
    """Reuse an existing text track's timings when there is no transcript."""
    texts = {}
    for m in draft["materials"].get("texts") or []:
        try:
            texts[m["id"]] = json.loads(m.get("content") or "{}").get("text", "")
        except ValueError:
            texts[m["id"]] = ""
    track = draft["tracks"][track_index]
    if track["type"] != "text":
        raise SystemExit(f"track {track_index} is {track['type']}, not text")
    out = []
    for s in sorted(track["segments"], key=lambda s: s["target_timerange"]["start"]):
        t = texts.get(s["material_id"], "").replace("\n", " ").strip()
        if not t:
            continue
        start = s["target_timerange"]["start"] / US
        out.append({"text": t, "start": start,
                    "end": start + s["target_timerange"]["duration"] / US})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("dest")
    ap.add_argument("--words")
    ap.add_argument("--from-track", type=int)
    ap.add_argument("--track-name", default="")
    ap.add_argument("--draft-root", default=DEFAULT_DRAFT_ROOT)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if capcut_running():
        raise SystemExit("CapCut is running — close it so it cannot overwrite "
                         "the generated draft.")

    src_dir = os.path.join(args.draft_root, args.source)
    if not os.path.isdir(src_dir):
        raise SystemExit(f"no such project: {src_dir}")
    out_dir = os.path.join(args.draft_root, args.dest)
    if os.path.exists(out_dir) and not args.force:
        raise SystemExit(f"{args.dest!r} already exists — pick another name or "
                         "pass --force")

    with open(os.path.join(src_dir, "draft_content.json"), encoding="utf-8") as f:
        draft = json.load(f)

    if args.words:
        with open(args.words, encoding="utf-8") as f:
            words = json.load(f)
    elif args.from_track is not None:
        words = words_from_track(draft, args.from_track)
    else:
        raise SystemExit("pass --words or --from-track")

    lines = build_lines(words)
    if not lines:
        raise SystemExit("no usable timings — nothing to subtitle")

    for bucket in MATERIAL_BUCKETS:
        draft["materials"].setdefault(bucket, [])

    segments = []
    for ln in lines:
        for beat in ln["beats"]:
            dur = int(round((beat["end"] - beat["start"]) * US))
            if dur < int(MIN_SYLLABLE * US * 0.5):
                continue
            mat = text_material(ln["line"], *beat["range"])
            draft["materials"]["texts"].append(mat)
            anim = uid()
            draft["materials"]["material_animations"].append({
                "id": anim, "type": "sticker_animation", "animations": [],
                "multi_language_current": "none",
            })
            seg = segment(mat["id"], [anim], None, dur,
                          int(round(beat["start"] * US)),
                          render_index=20000 + len(segments),
                          track_render_index=len(draft["tracks"]))
            seg["clip"]["scale"] = {"x": STYLE["scale"], "y": STYLE["scale"]}
            seg["clip"]["transform"] = {"x": 0.0, "y": STYLE["y"]}
            seg["hdr_settings"] = None
            seg["enable_lut"] = False
            seg["enable_adjust"] = False
            segments.append(seg)

    draft["tracks"].append({
        "id": uid(), "type": "text", "attribute": 0, "flag": 0,
        "is_default_name": not args.track_name, "name": args.track_name,
        "segments": segments,
    })

    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    shutil.copytree(src_dir, out_dir)
    for stale in ("draft_content.json.bak", "template.tmp", "template-2.tmp"):
        p = os.path.join(out_dir, stale)
        if os.path.exists(p):
            os.remove(p)

    with open(os.path.join(out_dir, "draft_content.json"), "w",
              encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False)

    meta_path = os.path.join(out_dir, "draft_meta_info.json")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    now = int(time.time() * US)
    meta.update({
        "draft_id": uid(), "draft_name": args.dest,
        "draft_fold_path": out_dir.replace("\\", "/"),
        "tm_draft_create": now, "tm_draft_modified": now,
    })
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)

    print(f"source : {args.source}  (untouched)")
    print(f"output : {out_dir}")
    print(f"lines  : {len(lines)}   syllable segments: {len(segments)}")
    print()
    for ln in lines[:12]:
        first, last = ln["beats"][0], ln["beats"][-1]
        sylls = " · ".join(ln["line"][b["range"][0]:b["range"][1]]
                           for b in ln["beats"])
        print(f"  {first['start']:6.2f}–{last['end']:6.2f}  {sylls}")
    if len(lines) > 12:
        print(f"  … {len(lines) - 12} more lines")
    print("\nopen CapCut and confirm the project loads — that is the real check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
