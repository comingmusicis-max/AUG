"""Stretch a scene's stills to cover its voiceover.

A brief that says "before photos, three angles, over this voice clip" never
says how long each photo holds — that number only exists once the voiceover
has been probed. Doing it by hand means opening media_report.json, dividing,
and editing three numbers in the plan, every time a clip is re-cut.

Run this between fetch_media.py and build_draft.py. It touches only scenes
whose clips are all stills and that carry a voice track, so scenes with
footage in them are left exactly as written.
"""

import argparse
import json
import os
import sys


def voice_duration(scene, report, scene_name):
    """How long the scene's voice track runs, in seconds."""
    total = 0.0
    for vo in scene.get("voice", []):
        name = vo["file"]
        if "in" in vo and "out" in vo:
            total += float(vo["out"]) - float(vo["in"])
            continue
        m = report.get(name)
        if m is None:
            raise SystemExit(f"{scene_name}: {name} is not in "
                             "media_report.json — run fetch_media.py first")
        if "error" in m:
            # The report records why a probe failed. Reporting that beats
            # accusing the clip of being a photo, which is what a missing
            # duration looks like from here.
            raise SystemExit(
                f"{name}: {m['error']} — media_report.json carries no "
                "durations, so there is nothing to fit.\n"
                "install ffmpeg, then re-run fetch_media.py: it keeps the "
                "files it already downloaded and only re-probes them."
            )
        if not m.get("duration"):
            raise SystemExit(f"{scene_name}: {name} has no duration; it probed "
                             "as a still, so it cannot be a voice track")
        # `at` places a clip later in the scene, so the track ends further out
        # than the clips' lengths added up.
        total = max(total, float(vo.get("at", 0)) + m["duration"])
    return total


def fit(plan, report):
    changes = []
    for scene in plan["scenes"]:
        name = scene.get("name", "?")
        clips = scene.get("clips", [])
        if not scene.get("voice") or not clips:
            continue
        if not all("still" in c for c in clips):
            continue  # footage sets its own length; only stills are elastic

        total = voice_duration(scene, report, name)
        if total <= 0:
            continue

        each = round(total / len(clips), 2)
        old = [c["still"] for c in clips]
        for c in clips:
            c["still"] = each
        # Rounding leaves a few hundredths on the table; give them to the last
        # still so the pictures end exactly with the voice rather than a frame
        # short of it.
        drift = round(total - each * len(clips), 2)
        if drift:
            clips[-1]["still"] = round(each + drift, 2)

        changes.append({"scene": name, "voice": round(total, 2),
                        "old": old, "new": [c["still"] for c in clips]})
    return changes


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("plan")
    ap.add_argument("--report", help="media_report.json "
                    "(default: media_report.json inside the plan's media_dir)")
    ap.add_argument("--write", action="store_true",
                    help="save the plan; without it nothing is written")
    args = ap.parse_args()

    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)

    report_path = args.report or os.path.join(plan["media_dir"],
                                              "media_report.json")
    if not os.path.exists(report_path):
        raise SystemExit(f"no media report at {report_path}\n"
                         "run fetch_media.py first — the still durations come "
                         "from the probed voiceover, not from the brief")
    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)

    changes = fit(plan, report)
    if not changes:
        print("no still-only scene with a voice track — nothing to fit")
        return

    for c in changes:
        print(f"{c['scene']}\n  voice {c['voice']}s over {len(c['new'])} "
              f"stills: {c['old']} -> {c['new']}")

    if not args.write:
        print("\ndry run — pass --write to save")
        return

    with open(args.plan, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"\nwrote {args.plan}")


if __name__ == "__main__":
    sys.exit(main())
