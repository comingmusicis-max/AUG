"""Dump a Resolve project's structure to JSON so it can be read away from the machine.

Grading a timeline you cannot see is guesswork. Run this on the machine with
Resolve, hand over the JSON, and the look can be written against the real clip
names, the real node counts, and the real colour management setting rather than
an assumption about them.

It only reads. Nothing in the project is touched.

    python scripts/inspect_project.py --project JJ --out jj_project.json
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from resolve_connect import get_project, get_resolve, video_items  # noqa: E402

# Colour management decides what a LUT is even allowed to assume about its
# input, so these three settings matter more than anything else here.
PROJECT_SETTINGS = [
    "colorScienceMode",
    "rcmPresetMode",
    "colorSpaceInput",
    "colorSpaceTimeline",
    "colorSpaceOutput",
    "timelineFrameRate",
    "timelineResolutionWidth",
    "timelineResolutionHeight",
]


def timecode(frames, fps):
    if not fps:
        return None
    fps = int(round(float(fps)))
    f = int(frames)
    return f"{f // (fps * 3600):02d}:{f // (fps * 60) % 60:02d}:{f // fps % 60:02d}:{f % fps:02d}"


def node_count(item):
    """How many nodes the clip's graph has — None if this version won't say."""
    try:
        n = item.GetNumNodes()
        return int(n) if n else None
    except Exception:
        return None


def existing_luts(item, nodes):
    out = {}
    for n in range(1, (nodes or 1) + 1):
        try:
            lut = item.GetLUT(n)
        except Exception:
            continue
        if lut and lut not in ("", "None"):
            out[str(n)] = lut
    return out


def describe_item(track, index, item, fps):
    info = {
        "track": track,
        "index": index,
        "name": item.GetName(),
        "start": item.GetStart(),
        "duration": item.GetDuration(),
        "start_tc": timecode(item.GetStart(), fps),
    }
    nodes = node_count(item)
    info["nodes"] = nodes
    luts = existing_luts(item, nodes)
    if luts:
        info["luts"] = luts
    try:
        colour = item.GetClipColor()
        if colour:
            info["clip_color"] = colour
    except Exception:
        pass
    mp = item.GetMediaPoolItem()
    if mp:
        for prop, key in (("File Path", "file"), ("Resolution", "resolution")):
            try:
                val = mp.GetClipProperty(prop)
            except Exception:
                continue
            if val:
                info[key] = val
    return info


def describe_timeline(timeline, fps, with_clips):
    out = {
        "name": timeline.GetName(),
        "video_tracks": timeline.GetTrackCount("video"),
        "audio_tracks": timeline.GetTrackCount("audio"),
        "start_frame": timeline.GetStartFrame(),
        "end_frame": timeline.GetEndFrame(),
    }
    if with_clips:
        out["clips"] = [describe_item(t, i, item, fps)
                        for t, i, item in video_items(timeline)]
        out["clip_count"] = len(out["clips"])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", help="project name (default: whatever is open)")
    ap.add_argument("--timeline", help="only this timeline (default: every one)")
    ap.add_argument("--out", default="project_report.json")
    args = ap.parse_args()

    resolve = get_resolve()
    project = get_project(resolve, args.project)

    report = {
        "resolve_version": resolve.GetVersionString(),
        "product": resolve.GetProductName(),   # 'Studio' here means scripting from outside works
        "project": project.GetName(),
        "settings": {},
    }
    for key in PROJECT_SETTINGS:
        try:
            report["settings"][key] = project.GetSetting(key)
        except Exception:
            pass

    fps = report["settings"].get("timelineFrameRate")
    current = project.GetCurrentTimeline()
    report["current_timeline"] = current.GetName() if current else None

    timelines = []
    for i in range(1, (project.GetTimelineCount() or 0) + 1):
        tl = project.GetTimelineByIndex(i)
        if tl is None:
            continue
        # Reading every clip on every timeline is slow on a big project, so
        # only the requested one (or the open one) is walked in full.
        wanted = args.timeline == tl.GetName() if args.timeline else (
            current is not None and tl.GetName() == current.GetName())
        timelines.append(describe_timeline(tl, fps, with_clips=wanted))
    report["timelines"] = timelines

    if args.timeline and not any(t["name"] == args.timeline for t in timelines):
        raise SystemExit(f"no timeline named {args.timeline!r} in {project.GetName()!r}. "
                         f"It has: {', '.join(t['name'] for t in timelines) or '(none)'}")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"{report['product']} {report['resolve_version']}  project {report['project']!r}")
    print(f"colour science: {report['settings'].get('colorScienceMode')} / "
          f"timeline space: {report['settings'].get('colorSpaceTimeline')}")
    for t in timelines:
        detail = f", {t['clip_count']} video clips" if "clip_count" in t else " (not walked)"
        print(f"  timeline {t['name']!r}: {t['video_tracks']} video tracks{detail}")
    print(f"\nwrote {args.out} — send that file over.")


if __name__ == "__main__":
    main()
