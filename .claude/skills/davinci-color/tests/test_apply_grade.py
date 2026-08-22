"""Run apply_grade.py against a stand-in for the Resolve API.

There is no Resolve in CI, and grading bugs are expensive to find by hand — a
wrong node index or a phase running out of order does not throw, it quietly
produces a differently-graded timeline. So the API is faked and the calls are
checked.

Every case here started as a real bug.

    python tests/test_apply_grade.py
"""

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))

calls = []


class Item:
    def __init__(self, name, nodes=1, color=None):
        self.name, self.nodes, self.color = name, nodes, color

    def GetName(self): return self.name
    def GetNumNodes(self): return self.nodes
    def GetClipColor(self): return self.color
    def GetStart(self): return 0
    def GetDuration(self): return 100

    def SetLUT(self, n, p): calls.append(("SetLUT", self.name, n, p)); return True
    def SetCDL(self, d):
        calls.append(("SetCDL", self.name, int(d["NodeIndex"]), d["Saturation"]))
        return True
    def SetNodeLabel(self, n, l): calls.append(("Label", self.name, n, l)); return True
    def SetNodeEnabled(self, n, e): calls.append(("Enabled", self.name, n, e)); return True
    def SetClipColor(self, c):
        self.color = c
        calls.append(("Mark", self.name, c))
        return True

    def CopyGrades(self, targets):
        calls.append(("CopyGrades", self.name, [t.name for t in targets]))
        for t in targets:
            t.nodes = self.nodes     # a copied graph brings its nodes along
        return True


class Timeline:
    def __init__(self, items): self.items = items
    def GetName(self): return "MAIN"
    def GetTrackCount(self, kind): return 1 if kind == "video" else 0
    def GetItemListInTrack(self, kind, n): return self.items if kind == "video" else []
    def ApplyGradeFromDRX(self, path, mode, items):
        calls.append(("DRX", path, mode, [i.name for i in items]))
        return True


class Project:
    def __init__(self, timeline): self.timeline = timeline
    def GetName(self): return "jj"
    def GetCurrentTimeline(self): return self.timeline
    def RefreshLUTList(self): calls.append(("RefreshLUTList",)); return True


class Resolve:
    def __init__(self, project): self.project = project
    def GetProjectManager(self):
        project = self.project

        class PM:
            def GetCurrentProject(self): return project
            def LoadProject(self, name): return project if name == "jj" else None
            def GetProjectListInCurrentFolder(self): return ["jj"]
        return PM()
    def OpenPage(self, page): calls.append(("OpenPage", page)); return True
    def GetProductName(self): return "DaVinci Resolve Studio"
    def GetVersionString(self): return "19.0.0"


def run(spec, items, argv=()):
    """Apply a spec to a fake timeline; return the call log."""
    calls.clear()
    timeline = Timeline(items)
    # resolve_connect looks for an injected `resolve`, the way Resolve's own
    # Console provides one.
    sys.modules["__main__"].resolve = Resolve(Project(timeline))

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(spec, f)
        path = f.name
    try:
        import apply_grade
        sys.argv = ["apply_grade.py", path, *argv]
        apply_grade.main()
    finally:
        os.unlink(path)
    return list(calls)


def graph_spec():
    """The JJ graph, near enough: six nodes, a copy, and a trim after it."""
    return {
        "project": "jj",
        "grades": [{
            "name": "graph",
            "select": {"tracks": [1], "indexes": [1]},
            "mark": "Orange",
            "nodes": [
                {"label": "01 BALANCE", "cdl": {"saturation": 1.0}},
                {"label": "02 EXPOSURE", "cdl": {"slope": [1.03, 1.03, 1.03]}},
                {"label": "03 LOOK", "lut": "golden_hour.cube"},
                {"label": "04 SKIN", "cdl": {"saturation": 0.97}},
                {"label": "05 SKY", "enabled": False},
                {"label": "06 TRIM", "cdl": {"saturation": 1.0}},
            ],
        }],
        "match": [{"source": {"tracks": [1], "indexes": [1]},
                   "targets": {"tracks": [1]}}],
        "trims": [],
    }


def fresh():
    return [Item("REF.MP4", nodes=6), Item("B.MP4"), Item("C.MP4")]


def test_nodes_land_in_order():
    log = run(graph_spec(), fresh())
    assert ("SetLUT", "REF.MP4", 3, "golden_hour.cube") in log
    assert ("Label", "REF.MP4", 5, "05 SKY") in log
    assert ("Enabled", "REF.MP4", 5, False) in log
    names = [c[0] for c in log]
    assert names.index("RefreshLUTList") < names.index("SetLUT"), \
        "SetLUT resolves bare names against a list that goes stale"
    assert names.index("SetLUT") < names.index("CopyGrades")


def test_trim_runs_after_the_copy():
    """A copied graph replaces the target, so a trim placed before it is lost."""
    spec = graph_spec()
    spec["trims"] = [{
        "name": "stage",
        "select": {"names": ["C.MP4"]},
        "nodes": [{"node": 3, "lut": "stage_indoor.cube"}],
    }]
    log = run(spec, fresh())
    copy_at = next(i for i, c in enumerate(log) if c[0] == "CopyGrades")
    trim_at = next(i for i, c in enumerate(log)
                   if c[0] == "SetLUT" and c[3] == "stage_indoor.cube")
    assert trim_at > copy_at
    assert not any(c[0] == "SetLUT" and c[1] == "B.MP4" for c in log), \
        "clips outside the trim keep the base look"


def test_trim_sees_nodes_the_copy_created():
    """Clip records are read before the copy; stale counts blocked the trim."""
    spec = graph_spec()
    spec["trims"] = [{"select": {"names": ["C.MP4"]},
                      "nodes": [{"node": 6, "cdl": {"saturation": 1.1}}]}]
    log = run(spec, fresh())          # C.MP4 starts with one node
    assert ("SetCDL", "C.MP4", 6, "1.100000") in log


def test_rerun_is_not_blocked_by_its_own_output():
    """Re-running after a re-cut is the whole point; the guard must allow it."""
    items = fresh()
    run(graph_spec(), items)
    assert all(i.color == "Orange" for i in items), "the copy must mark its targets"
    log = run(graph_spec(), items)    # same clips, now graded and marked
    assert any(c[0] == "CopyGrades" for c in log)


def test_handmade_graph_is_protected():
    items = fresh()
    items[1].nodes, items[1].color = 14, None    # somebody's own work
    try:
        run(graph_spec(), items)
    except SystemExit as e:
        assert "B.MP4" in str(e) and "14 nodes" in str(e)
    else:
        raise AssertionError("the guard should have stopped the copy")


def test_force_overrides_the_guard():
    items = fresh()
    items[1].nodes, items[1].color = 14, None
    log = run(graph_spec(), items, argv=("--force",))
    assert any(c[0] == "CopyGrades" for c in log)


def test_dry_run_changes_nothing():
    log = run(graph_spec(), fresh(), argv=("--dry-run",))
    assert not log, f"dry run touched Resolve: {log}"


def test_bad_spec_is_refused():
    import apply_grade
    for spec, expect in [
        ({"grades": [{"select": {"trackz": [1]}, "lut": "x.cube"}]}, "unknown select key"),
        ({"grades": [{"select": {}, "nodes": [{"lut": "x", "colour": "red"}]}]}, "unknown key"),
        ({"grades": [{"select": {}}]}, "would do nothing"),
        ({"grades": [{"select": {}, "lut": "x", "nodes": []}]}, "both 'nodes'"),
    ]:
        try:
            run(spec, fresh())
        except SystemExit as e:
            assert expect in str(e), f"wrong complaint for {spec}: {e}"
        else:
            raise AssertionError(f"accepted a bad spec: {spec}")
    assert apply_grade  # imported, silences the linter


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok   {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
