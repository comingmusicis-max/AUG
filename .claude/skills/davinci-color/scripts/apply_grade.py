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


def cdl_payload(cdl, node=None):
    """Resolve wants CDL values as space-separated strings, not numbers."""
    def triple(key, default):
        vals = cdl.get(key, default)
        if len(vals) != 3:
            raise SystemExit(f"cdl.{key} must be three numbers [r, g, b]")
        return " ".join(f"{float(v):.6f}" for v in vals)

    return {
        "NodeIndex": str(node if node is not None else cdl.get("node", 1)),
        "Slope": triple("slope", [1, 1, 1]),
        "Offset": triple("offset", [0, 0, 0]),
        "Power": triple("power", [1, 1, 1]),
        "Saturation": f"{float(cdl.get('saturation', 1.0)):.6f}",
    }


NODE_KEYS = {"node", "label", "lut", "cdl", "enabled", "note"}


def node_ops(grade):
    """One grade entry as a list of per-node operations.

    A graph is written as `nodes`, one entry per node in order. The older flat
    form — a `lut` plus `lut_node`, or a `cdl` — is the same thing with a single
    node, so both go through here and the rest of the script sees one shape.
    """
    if "nodes" in grade:
        if "lut" in grade or "cdl" in grade:
            raise SystemExit("a grade entry has both 'nodes' and a top-level "
                             "'lut'/'cdl'. Put them inside 'nodes'.")
        ops = []
        for position, spec in enumerate(grade["nodes"], start=1):
            unknown = set(spec) - NODE_KEYS
            if unknown:
                raise SystemExit(f"unknown key(s) in node {position}: "
                                 f"{', '.join(sorted(unknown))}\n"
                                 f"valid: {', '.join(sorted(NODE_KEYS))}")
            op = dict(spec)
            # Position in the list is the node number unless it says otherwise,
            # so a graph reads top-to-bottom the way it looks on the Color page.
            op["node"] = int(spec.get("node", position))
            ops.append(op)
        return ops

    ops = []
    if "lut" in grade:
        ops.append({"node": int(grade.get("lut_node", 1)), "lut": grade["lut"]})
    if "cdl" in grade:
        ops.append({"node": int(grade["cdl"].get("node", 1)), "cdl": grade["cdl"]})
    return ops


def check_node(rec, node, action):
    """Refuse a node index the clip does not have, rather than failing silently."""
    nodes = rec.get("nodes")
    if nodes is not None and node > nodes:
        raise SystemExit(
            f"{rec['name']} (V{rec['track']} #{rec['index']}) has {nodes} node(s), "
            f"but the grade wants to {action} on node {node}.\n"
            "The API cannot add nodes. Add them on the Color page (or apply a "
            "PowerGrade with the right graph), then re-run.")


def check_file(path, spec_path, kind, hint):
    """A bare LUT name resolves against Resolve's own folder, so only absolute
    paths can be checked from here — but a wrong absolute path is worth catching
    before half a timeline has been graded."""
    if path and os.path.isabs(path) and not os.path.isfile(path):
        raise SystemExit(f"{spec_path}: {kind} not found: {path}\n{hint}")


def load_spec(path):
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)

    unknown = set(spec) - {"project", "timeline", "grades", "match", "trims", "note"}
    if unknown:
        raise SystemExit(f"{path}: unknown top-level key(s): {', '.join(sorted(unknown))}")

    lut_hint = ("Run make_lut.py first, or pass the name as it appears in "
                "Resolve's LUT list.")
    for phase in ("grades", "trims"):
        for grade in spec.get(phase, []):
            if not {"lut", "cdl", "nodes", "drx"} & set(grade):
                raise SystemExit(f"{path}: a {phase[:-1]} entry has no 'nodes', "
                                 "'drx', 'lut' or 'cdl' — it would do nothing")
            check_file(grade.get("drx"), path, "grade file",
                       "Export one from a gallery still: right-click > Export, "
                       "format .drx.")
            check_file(grade.get("lut"), path, "LUT", lut_hint)
            for node in grade.get("nodes", []):
                check_file(node.get("lut"), path, "LUT", lut_hint)
            # node_ops does the rest of the validation, and raises the same way.
            node_ops(grade)
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
    ap.add_argument("--force", action="store_true",
                    help="allow a match to copy over clips that already have a graph")
    args = ap.parse_args()

    if not args.spec and not args.list:
        ap.error("give a grade file, or --list to see what is on the timeline")

    # Read the grade file before touching Resolve: a typo in the JSON should
    # fail immediately, not after loading a project.
    spec = load_spec(args.spec) if args.spec else {}

    resolve = get_resolve()
    project = get_project(resolve, args.project or spec.get("project"))
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
            n = rec["nodes"]
            nodes = f"  ({n} node{'' if n == 1 else 's'})" if n else ""
            print(f"  V{rec['track']} #{rec['index']:>3}  {rec['name']}{nodes}")
        return

    if not args.dry_run:
        # SetLUT resolves bare names against this list, and it goes stale as
        # soon as make_lut.py writes a new file.
        project.RefreshLUTList()
        resolve.OpenPage("color")

    def run_phase(entries, phase):
        """Apply one list of grade entries. Used for `grades` and again for `trims`."""
        count = 0
        for n, grade in enumerate(entries, start=1):
            chosen = select(records, grade.get("select", {}))
            label = grade.get("name", f"{phase} {n}")
            if not chosen:
                print(f"  {label}: matched no clips — check its select block")
                continue
            print(f"  {label}: {len(chosen)} clip(s)")

            for rec in chosen:
                item = items[(rec["track"], rec["index"])]
                where = f"V{rec['track']} #{rec['index']} {rec['name']}"

                # A whole graph in one file. This is the only way to get node
                # structure onto a clip from a script — the API cannot add nodes.
                if "drx" in grade:
                    continue

                for op in node_ops(grade):
                    node = op["node"]

                    if "lut" in op:
                        check_node(rec, node, "load a LUT")
                        if args.dry_run:
                            print(f"    would set LUT node {node} = {op['lut']}  on {where}")
                        elif not item.SetLUT(node, op["lut"]):
                            raise SystemExit(
                                f"SetLUT failed on {where} (node {node}, {op['lut']}).\n"
                                "Usually the LUT is not in Resolve's LUT folder, or "
                                "the path has a typo. make_lut.py --install puts it "
                                "in the right place.")

                    if "cdl" in op:
                        check_node(rec, node, "set CDL")
                        payload = cdl_payload(op["cdl"], node)
                        if args.dry_run:
                            print(f"    would set CDL node {node} = {payload}  on {where}")
                        elif not item.SetCDL(payload):
                            raise SystemExit(f"SetCDL failed on {where} (node {node})")

                    if "label" in op and not args.dry_run:
                        # Named nodes are the difference between a graph someone
                        # else can pick up and five grey boxes.
                        check_node(rec, node, "label a node")
                        try:
                            item.SetNodeLabel(node, op["label"])
                        except AttributeError:
                            pass  # older Resolve; the grade itself still landed

                    if "enabled" in op and not args.dry_run:
                        check_node(rec, node, "enable/disable a node")
                        try:
                            item.SetNodeEnabled(node, bool(op["enabled"]))
                        except AttributeError:
                            pass

                if "mark" in grade and not args.dry_run:
                    # A clip colour makes it obvious in the timeline which clips
                    # the script owns and which a human still has to grade.
                    item.SetClipColor(grade["mark"])

                count += 1

            if "drx" in grade:
                targets = [items[(r["track"], r["index"])] for r in chosen]
                mode = int(grade.get("drx_mode", 0))
                if args.dry_run:
                    print(f"    would apply the graph in {grade['drx']} to "
                          f"{len(targets)} clip(s)")
                elif not timeline.ApplyGradeFromDRX(grade["drx"], mode, targets):
                    raise SystemExit(
                        f"ApplyGradeFromDRX failed with {grade['drx']}.\n"
                        "Check the path, and that the .drx was exported from this "
                        "version of Resolve (right-click a gallery still > "
                        "Export, or grab one from a graded clip first).")
        return count

    applied = run_phase(spec.get("grades", []), "grade")

    for pair in spec.get("match", []):
        sources = select(records, pair["source"])
        targets = select(records, pair["targets"])
        if len(sources) != 1:
            raise SystemExit(f"match.source must pick exactly one clip, it picked "
                             f"{len(sources)}: {[s['name'] for s in sources]}")
        if not targets:
            raise SystemExit(f"match.targets picked no clips: {pair['targets']}")

        src = items[(sources[0]["track"], sources[0]["index"])]
        targets = [t for t in targets if (t["track"], t["index"])
                   != (sources[0]["track"], sources[0]["index"])]
        if not targets:
            print(f"  match: {sources[0]['name']} is its own only target, skipped")
            continue

        # CopyGrades replaces the target's graph outright. Someone's hand-built
        # nodes are worth more than this script's convenience, so a copy over
        # existing work has to be asked for.
        occupied = [t for t in targets if (t.get("nodes") or 1) > 1]
        if occupied and not args.force:
            listing = "\n".join(f"    V{t['track']} #{t['index']} {t['name']} "
                                 f"({t['nodes']} nodes)" for t in occupied[:8])
            more = f"\n    ... and {len(occupied) - 8} more" if len(occupied) > 8 else ""
            raise SystemExit(
                f"{len(occupied)} target clip(s) already carry a node graph, and "
                f"copying over them would replace it:\n{listing}{more}\n\n"
                "Either narrow the match's targets, or pass --force if replacing "
                "them is the intent. Export what is there first with "
                "export_grade.py — a .drx puts it back.")

        names = ", ".join(t["name"] for t in targets)
        if args.dry_run:
            print(f"  would copy the whole graph from {sources[0]['name']} to {names}")
            continue
        if not src.CopyGrades([items[(t['track'], t['index'])] for t in targets]):
            raise SystemExit(f"CopyGrades failed from {sources[0]['name']} to {names}")
        print(f"  copied the whole graph from {sources[0]['name']} to {names}")
        applied += len(targets)

    # Trims run last on purpose: a copied graph overwrites whatever was on the
    # clip, so per-clip corrections have to land after the copy, not before.
    applied += run_phase(spec.get("trims", []), "trim")

    verb = "would be graded" if args.dry_run else "graded"
    print(f"{applied} clip application(s) {verb}.")
    if not args.dry_run:
        print("Resolve keeps this in undo — Ctrl+Z on the Color page steps it back.")


if __name__ == "__main__":
    main()
