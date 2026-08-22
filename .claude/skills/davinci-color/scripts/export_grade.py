"""Save a clip's node graph to a .drx file.

A graph that exists only inside a project is one accidental delete away from
gone, and it cannot be reused on next month's job. Exporting it makes the whole
node tree a file: `apply_grade.py` can push it onto any set of clips, on any
timeline, in any project — including the nodes themselves, which is the one
thing the API cannot otherwise create.

Run it once the graph on the reference clip is right.

    python scripts/export_grade.py --project jj --clip 1 --out D:/grades
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from resolve_connect import get_project, get_resolve, get_timeline, video_items  # noqa: E402


def timecode(frames, fps):
    fps = int(round(float(fps)))
    f = int(frames)
    return f"{f // (fps * 3600):02d}:{f // (fps * 60) % 60:02d}:{f // fps % 60:02d}:{f % fps:02d}"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project")
    ap.add_argument("--timeline")
    ap.add_argument("--clip", type=int, default=1,
                    help="which V1 clip to take the graph from (default: the first)")
    ap.add_argument("--track", type=int, default=1)
    ap.add_argument("--out", default=".", help="folder for the .drx")
    ap.add_argument("--name", default="grade", help="filename prefix")
    ap.add_argument("--keep-still", action="store_true",
                    help="leave the grabbed still in the gallery (default: remove it)")
    args = ap.parse_args()

    resolve = get_resolve()
    project = get_project(resolve, args.project)
    timeline = get_timeline(project, args.timeline)
    resolve.OpenPage("color")

    wanted = [(t, i, item) for t, i, item in video_items(timeline)
              if t == args.track and i == args.clip]
    if not wanted:
        raise SystemExit(f"no clip #{args.clip} on V{args.track}. "
                         "apply_grade.py --list shows what is there.")
    _, _, item = wanted[0]

    fps = project.GetSetting("timelineFrameRate")
    # GrabStill takes the frame under the playhead, so the playhead has to be
    # parked on the clip whose graph is wanted.
    tc = timecode(item.GetStart() + 1, fps)
    if not timeline.SetCurrentTimecode(tc):
        raise SystemExit(f"could not move the playhead to {tc}")

    nodes = None
    try:
        nodes = item.GetNumNodes()
    except Exception:
        pass
    print(f"grabbing from {item.GetName()!r} at {tc}"
          + (f" ({nodes} nodes)" if nodes else ""))

    still = timeline.GrabStill()
    if not still:
        raise SystemExit("GrabStill returned nothing — is the Color page showing this clip?")

    album = project.GetGallery().GetCurrentStillAlbum()
    folder = os.path.abspath(args.out)
    os.makedirs(folder, exist_ok=True)

    # Resolve decides the exact filename, so the only reliable way to report it
    # is to see what appeared.
    before = set(os.listdir(folder))
    ok = album.ExportStills([still], folder, args.name, "drx")
    if not args.keep_still:
        album.DeleteStills([still])
    if not ok:
        raise SystemExit(f"ExportStills failed writing to {folder}")

    new = sorted(set(os.listdir(folder)) - before)
    if not new:
        raise SystemExit(f"ExportStills reported success but nothing appeared in {folder}")
    for f in new:
        print(f"wrote {os.path.join(folder, f)}")

    drx = next((f for f in new if f.lower().endswith(".drx")), new[0])
    print("\nUse it on every clip with a grade entry like:")
    print(f'  {{"select": {{"all": true}}, "drx": "{os.path.join(folder, drx)}"}}')


if __name__ == "__main__":
    main()
