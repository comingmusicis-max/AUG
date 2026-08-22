"""Apply a written grade to every clip a rule matches, through the Resolve API.

This is the part that makes a look repeatable. The grade lives in a JSON file:
which clips, which LUT, which CDL numbers. Re-run it after a re-cut and the
timeline comes back identically graded — no drift, no clip quietly left
ungraded because it scrolled off screen.

    python scripts/apply_grade.py grade.json --project JJ --dry-run
    python scripts/apply_grade.py grade.json --project JJ

What the API can and cannot do is worth knowing before writing a grade file:
it can load a LUT into an existing node, set that node's CDL numbers, and copy
a whole graph from one clip to others. It cannot create nodes or move colour
wheels. So build the node graph once by hand (or in a PowerGrade), then drive
it from here.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from resolve_connect import get_project, get_resolve, get_timeline, video_items  # noqa: E402

SELECT_KEYS = {"all", "tracks", "names", "name_contains", "indexes", "range"}


def select(records, sel):
    """Records matching every criterion given. Pure — the tests lean on this.

    A record is {"track": int, "index": int, "name": str}. Criteria combine with
    AND, so {"tracks": [1], "name_contains": "DSC"} means stills on V1 only.
    """
    unknown = set(sel) - SELECT_KEYS
    if unknown:
        raise SystemExit(f"unknown select key(s): {', '.join(sorted(unknown))}\n"
                         f"valid: {', '.join(sorted(SELECT_KEYS))}")
    if not sel or sel.get("all"):
        if len(set(sel) - {"all"}) == 0:
            return list(records)

    out = []
    for rec in records:
        if "tracks" in sel and rec["track"] not in sel["tracks"]:
            continue
        if "names" in sel and rec["name"] not in sel["names"]:
            continue
        if "name_contains" in sel and sel["name_contains"].lower() not in rec["name"].lower():
            continue
        if "indexes" in sel and rec["index"] not in sel["indexes"]:
            continue
        if "range" in sel:
            lo, hi = sel["range"]
            if not lo <= rec["index"] <= hi:
                continue
        out.append(rec)
    return out


def cdl_payload(cdl):
    """Resolve wants CDL values as space-separated strings, not numbers."""
    def triple(key, default):
        vals = cdl.get(key, default)
        if len(vals) != 3:
            raise SystemExit(f"cdl.{key} must be three numbers [r, g, b]")
        return " ".join(f"{float(v):.6f}" for v in vals)

    return {
        "NodeIndex": str(cdl.get("node", 1)),
        "Slope": triple("slope", [1, 1, 1]),
        "Offset": triple("offset", [0, 0, 0]),
        "Power": triple("power", [1, 1, 1]),
        "Saturation": f"{float(cdl.get('saturation', 1.0)):.6f}",
    }


def check_node(rec, node, action):
    """Refuse a node index the clip does not have, rather than failing silently."""
    nodes = rec.get("nodes")
    if nodes is not None and node > nodes:
        raise SystemExit(
            f"{rec['name']} (V{rec['track']} #{rec['index']}) has {nodes} node(s), "
            f"but the grade wants to {action} on node {node}.\n"
            "The API cannot add nodes. Add them on the Color page (or apply a "
            "PowerGrade with the right graph), then re-run.")


def load_spec(path):
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    for grade in spec.get("grades", []):
        if "lut" not in grade and "cdl" not in grade:
            raise SystemExit(f"{path}: a grade entry has neither 'lut' nor 'cdl' — "
                             "it would do nothing")
        lut = grade.get("lut")
        # A bare filename is resolved against Resolve's own LUT folder, so only
        # absolute paths can be checked from here.
        if lut and os.path.isabs(lut) and not os.path.isfile(lut):
            raise SystemExit(f"{path}: LUT not found: {lut}\n"
                             "Run make_lut.py first, or pass the name as it "
                             "appears in Resolve's LUT list.")
    return spec


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", nargs="?", help="grade JSON file")
    ap.add_argument("--project", help="project name (default: whatever is open)")
    ap.add_argument("--timeline", help="timeline name (default: the open one)")
    ap.add_argument("--list", action="store_true",
                    help="print the timeline's clips and exit, changing nothing")
    ap.add_argument("--dry-run", action="store_true",
                    help="say what would be applied to which clip, change nothing")
    args = ap.parse_args()

    if not args.spec and not args.list:
        ap.error("give a grade file, or --list to see what is on the timeline")

    resolve = get_resolve()
    project = get_project(resolve, args.project)
    spec = load_spec(args.spec) if args.spec else {}
    timeline = get_timeline(project, args.timeline or spec.get("timeline"))

    found = video_items(timeline)
    items = {}
    records = []
    for track, index, item in found:
        try:
            nodes = item.GetNumNodes()
            nodes = int(nodes) if nodes else None
        except Exception:
            nodes = None
        rec = {"track": track, "index": index, "name": item.GetName(), "nodes": nodes}
        records.append(rec)
        items[(track, index)] = item

    print(f"{project.GetName()!r} / {timeline.GetName()!r}: {len(records)} video clips")

    if args.list:
        for rec in records:
            nodes = f"  ({rec['nodes']} nodes)" if rec["nodes"] else ""
            print(f"  V{rec['track']} #{rec['index']:>3}  {rec['name']}{nodes}")
        return

    if not args.dry_run:
        # SetLUT resolves bare names against this list, and it goes stale as
        # soon as make_lut.py writes a new file.
        project.RefreshLUTList()
        resolve.OpenPage("color")

    applied = 0
    for n, grade in enumerate(spec.get("grades", []), start=1):
        chosen = select(records, grade.get("select", {}))
        label = grade.get("name", f"grade {n}")
        if not chosen:
            print(f"  {label}: matched no clips — check its select block")
            continue

        for rec in chosen:
            item = items[(rec["track"], rec["index"])]
            where = f"V{rec['track']} #{rec['index']} {rec['name']}"

            if "lut" in grade:
                node = int(grade.get("lut_node", 1))
                check_node(rec, node, "load a LUT")
                if args.dry_run:
                    print(f"  would set LUT node {node} = {grade['lut']}  on {where}")
                elif not item.SetLUT(node, grade["lut"]):
                    raise SystemExit(
                        f"SetLUT failed on {where} (node {node}, {grade['lut']}).\n"
                        "Usually the LUT is not in Resolve's LUT folder, or the "
                        "path has a typo. make_lut.py --install puts it in the "
                        "right place.")

            if "cdl" in grade:
                node = int(grade["cdl"].get("node", 1))
                check_node(rec, node, "set CDL")
                payload = cdl_payload(grade["cdl"])
                if args.dry_run:
                    print(f"  would set CDL node {node} = {payload}  on {where}")
                elif not item.SetCDL(payload):
                    raise SystemExit(f"SetCDL failed on {where} (node {node})")

            if "mark" in grade and not args.dry_run:
                # A clip colour makes it obvious in the timeline which clips the
                # script touched, which matters when a human grades the rest.
                item.SetClipColor(grade["mark"])

            applied += 1

    for pair in spec.get("match", []):
        sources = select(records, pair["source"])
        targets = select(records, pair["targets"])
        if len(sources) != 1:
            raise SystemExit(f"match.source must pick exactly one clip, it picked "
                             f"{len(sources)}: {[s['name'] for s in sources]}")
        if not targets:
            raise SystemExit(f"match.targets picked no clips: {pair['targets']}")

        src = items[(sources[0]["track"], sources[0]["index"])]
        names = ", ".join(t["name"] for t in targets)
        if args.dry_run:
            print(f"  would copy the grade from {sources[0]['name']} to {names}")
            continue
        if not src.CopyGrades([items[(t['track'], t['index'])] for t in targets]):
            raise SystemExit(f"CopyGrades failed from {sources[0]['name']} to {names}")
        print(f"  copied the grade from {sources[0]['name']} to {names}")
        applied += len(targets)

    verb = "would be graded" if args.dry_run else "graded"
    print(f"{applied} clip application(s) {verb}.")
    if not args.dry_run:
        print("Resolve keeps this in undo — Ctrl+Z on the Color page steps it back.")


if __name__ == "__main__":
    main()
