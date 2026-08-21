"""Report what an existing CapCut draft actually contains.

Subtitles and re-cuts have to line up with the timeline the editor has now, not
the one that was generated — they trim clips, split tracks and add text. Run
this before touching a project someone has been working in.

Usage:
    python read_timeline.py <project-name> [--draft-root DIR] [--clips OUT.json]

`--clips` writes the audible clips as a manifest for transcribe_audio.py, with
each clip's placement and trim already worked out.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_draft import US, DEFAULT_DRAFT_ROOT  # noqa: E402


def load(draft_root: str, project: str) -> dict:
    path = os.path.join(draft_root, project, "draft_content.json")
    if not os.path.exists(path):
        raise SystemExit(f"no such project: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def describe(draft: dict):
    """Every segment, resolved back to the media or text behind it."""
    kinds = {}
    for m in draft["materials"].get("videos") or []:
        kinds[m["id"]] = (m.get("type", "video"), m.get("path", ""))
    for m in draft["materials"].get("audios") or []:
        kinds[m["id"]] = ("audio", m.get("path", ""))
    for m in draft["materials"].get("texts") or []:
        try:
            body = json.loads(m.get("content") or "{}").get("text", "")
        except ValueError:
            body = ""
        kinds[m["id"]] = ("text", body)

    rows = []
    for ti, track in enumerate(draft["tracks"]):
        for s in track["segments"]:
            kind, ref = kinds.get(s["material_id"], ("?", "?"))
            src = s.get("source_timerange") or {}
            rows.append({
                "track": ti, "track_type": track["type"], "kind": kind,
                "ref": ref,
                "name": os.path.basename(ref) if kind != "text" else ref,
                "start": s["target_timerange"]["start"] / US,
                "dur": s["target_timerange"]["duration"] / US,
                "src": (src.get("start", 0) / US) if src else 0.0,
                "volume": s.get("volume", 1.0),
            })
    rows.sort(key=lambda r: (r["track"], r["start"]))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--draft-root", default=DEFAULT_DRAFT_ROOT)
    ap.add_argument("--clips", help="write an audible-clip manifest here")
    args = ap.parse_args()

    draft = load(args.draft_root, args.project)
    rows = describe(draft)

    print(f"duration: {draft['duration'] / US:.2f}s   fps={draft.get('fps')}")
    current = None
    for r in rows:
        if r["track"] != current:
            current = r["track"]
            print(f"\n-- track {current} ({r['track_type']}) --")
        end = r["start"] + r["dur"]
        extra = ""
        if r["kind"] in ("video", "audio"):
            extra = f"  src@{r['src']:.2f}"
            if r["volume"] == 0:
                extra += "  MUTED"
        label = r["name"].replace("\n", " / ")[:50]
        print(f"  {r['start']:6.2f}-{end:6.2f} ({r['dur']:5.2f}s) "
              f"{r['kind']:6} {label}{extra}")

    # Only unmuted video/audio can carry speech worth transcribing.
    audible = [r for r in rows
               if r["kind"] in ("video", "audio") and r["volume"] > 0
               and os.path.exists(r["ref"])]
    print(f"\n-- audible clips: {len(audible)} --")
    for r in audible:
        print(f"  {r['name']:16} at {r['start']:6.2f}s  "
              f"src {r['src']:.2f}  len {r['dur']:.2f}")

    if args.clips:
        manifest = [{"path": r["ref"], "timeline": round(r["start"], 3),
                     "src": round(r["src"], 3), "len": round(r["dur"], 3),
                     "voiceover": r["track_type"] == "audio"}
                    for r in audible]
        with open(args.clips, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(f"\nclip manifest -> {args.clips}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
