@python -c "" >nul 2>&1 && (python -x "%~f0" %* & ver >nul) || (py -3 -c "" >nul 2>&1 && (py -3 -x "%~f0" %* & ver >nul) || (echo.&echo   Python 3 does not run on this machine.&echo.&echo   Install it from  https://www.python.org/downloads/&echo   and TICK "Add python.exe to PATH" on the first setup screen.&echo   Resolve needs the same Python for scripting, so this is&echo   required either way.&echo.&echo   Then double-click this file again.&echo.))&pause&exit /b
"""Grade C0001 in the DaVinci project 'jj'. One file, nothing else needed.

Save this anywhere and run it. It writes its own LUT, finds Resolve, and puts
a six-node graph on the clip. No repo, no Administrator, no folder structure —
the LUT goes somewhere writable and Resolve is handed the full path, which
SetLUT accepts.

    py jj_grade.py

Before running: open project jj in Resolve, go to the Color page, select
C0001, and add serial nodes until it has six. That part cannot be scripted —
Resolve's API has no way to create a node.
"""

import colorsys
import os
import sys

# ── the look ────────────────────────────────────────────────────────────────
# C0001 is an indoor rehearsal room. Its white balance is already close, so
# this corrects lightly rather than fighting a cast that is not there: a little
# off the warmth, the contrast the room lacks, and skin held back from the
# saturation lift because the singer is the whole frame.
LOOK = {
    "temp": -3.0,          # + warmer (more red, less blue)
    "tint": 1.0,           # + greener
    "exposure": 0.05,      # stops
    "contrast": 1.06,
    "pivot": 0.435,
    "saturation": 1.06,
    "skin_protect": 0.8,   # 0..1, how much to spare skin hues
    "lift": [0.006, 0.006, 0.010],
    "gamma": [1.0, 1.0, 1.0],
    "gain": [1.0, 1.0, 0.995],
}

LUT_NAME = "jj_c0001.cube"
LUT_SIZE = 33
PROJECT = "jj"
CLIP = "C0001"

# Node 5 is left empty and switched off on purpose: windows and qualifiers
# cannot be scripted, so it waits in the right place in the chain.
GRAPH = [
    ("01 BALANCE",  {"sat": 1.0}),
    ("02 EXPOSURE", {"slope": 1.03}),
    ("03 LOOK",     {"lut": True}),
    ("04 SKIN",     {"sat": 0.97}),
    ("05 WINDOW - add by hand", {"off": True}),
    ("06 TRIM",     {"sat": 1.0}),
]

GAMMA = 2.2
SKIN_HUE, SKIN_WIDTH = 0.072, 0.055


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def skin_weight(r, g, b):
    h, s, _ = colorsys.rgb_to_hsv(r, g, b)
    d = abs(h - SKIN_HUE)
    d = min(d, 1.0 - d)
    return (2.718281828 ** (-(d * d) / (2 * SKIN_WIDTH ** 2))) * min(s / 0.25, 1.0)


def apply_look(r, g, b):
    kr, kb = 1.0 + LOOK["temp"] / 500.0, 1.0 - LOOK["temp"] / 500.0
    kg = 1.0 + LOOK["tint"] / 500.0
    r, g, b = r * kr, g * kg, b * kb

    if LOOK["exposure"]:
        scale = 2.0 ** LOOK["exposure"]
        r, g, b = [(clamp(v) ** GAMMA * scale) ** (1.0 / GAMMA) for v in (r, g, b)]

    out = []
    for v, lift, gam, gain in zip((r, g, b), LOOK["lift"], LOOK["gamma"], LOOK["gain"]):
        out.append(clamp(v * gain + lift) ** (1.0 / gam))
    r, g, b = out

    if LOOK["contrast"] != 1.0:
        c, p = LOOK["contrast"], LOOK["pivot"]
        r, g, b = [(v - p) * c + p for v in (r, g, b)]

    if LOOK["saturation"] != 1.0:
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        sat = LOOK["saturation"]
        if LOOK["skin_protect"]:
            w = skin_weight(clamp(r), clamp(g), clamp(b))
            sat = 1.0 + (sat - 1.0) * (1.0 - LOOK["skin_protect"] * w)
        r, g, b = [lum + (v - lum) * sat for v in (r, g, b)]

    return clamp(r), clamp(g), clamp(b)


def write_lut():
    """Somewhere writable, so this never needs Administrator."""
    folder = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                          "jj-grade")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, LUT_NAME)

    step = LUT_SIZE - 1
    lines = [f'TITLE "jj_c0001"', f"LUT_3D_SIZE {LUT_SIZE}",
             "DOMAIN_MIN 0.0 0.0 0.0", "DOMAIN_MAX 1.0 1.0 1.0", ""]
    for bi in range(LUT_SIZE):                 # .cube runs red fastest
        for gi in range(LUT_SIZE):
            for ri in range(LUT_SIZE):
                r, g, b = apply_look(ri / step, gi / step, bi / step)
                lines.append(f"{r:.6f} {g:.6f} {b:.6f}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def get_resolve():
    injected = sys.modules["__main__"].__dict__.get("resolve")
    if injected is not None:
        return injected

    bases = [os.path.expandvars(p) for p in (
        os.environ.get("RESOLVE_SCRIPT_API", ""),
        r"%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting",
        "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting",
        "/opt/resolve/Developer/Scripting",
    ) if p]
    for base in bases:
        mod = os.path.join(base, "Modules")
        if os.path.isfile(os.path.join(mod, "DaVinciResolveScript.py")):
            sys.path.append(mod)
            break
    else:
        die("Cannot find DaVinci Resolve's scripting module.",
            "Is Resolve installed on this machine?",
            "Looked in:", *[f"  {b}" for b in bases])

    for lib in (r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll",
                "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/"
                "Libraries/Fusion/fusionscript.so",
                "/opt/resolve/libs/Fusion/fusionscript.so"):
        if os.path.isfile(lib) and not os.environ.get("RESOLVE_SCRIPT_LIB"):
            os.environ["RESOLVE_SCRIPT_LIB"] = lib
            break

    import DaVinciResolveScript as dvr
    handle = dvr.scriptapp("Resolve")
    if handle is None:
        die("Resolve is not answering. Three things do it, in this order:",
            "  1. DaVinci Resolve must be open, with project jj loaded.",
            "  2. Preferences > System > General > 'External scripting using'",
            "     must be Local, not None. Restart Resolve after changing it.",
            "  3. External scripting needs Resolve Studio. On the free version,",
            "     paste this file into Workspace > Console (set to Py3) instead.")
    return handle


def die(*lines):
    print()
    for l in lines:
        print(f"  {l}")
    print()
    input("Press Enter to close...")
    sys.exit(1)


def main():
    print("=" * 52)
    print(" JJ - grade C0001")
    print("=" * 52)

    print("\n[1/3] building the LUT...")
    lut = write_lut()
    print(f"      {lut}")

    print("\n[2/3] connecting to Resolve...")
    resolve = get_resolve()
    print(f"      {resolve.GetProductName()} {resolve.GetVersionString()}")

    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    if project is None or project.GetName() != PROJECT:
        opened = pm.LoadProject(PROJECT)
        if opened is None:
            die(f"No project called {PROJECT!r} is open.",
                "Open it in Resolve and run this again.")
        project = opened
    timeline = project.GetCurrentTimeline()
    if timeline is None:
        die("No timeline is open in that project.")
    print(f"      project {project.GetName()!r}, timeline {timeline.GetName()!r}")

    item = None
    for track in range(1, (timeline.GetTrackCount("video") or 0) + 1):
        for candidate in timeline.GetItemListInTrack("video", track) or []:
            if CLIP.lower() in candidate.GetName().lower():
                item = candidate
                break
        if item:
            break
    if item is None:
        die(f"No clip with {CLIP!r} in its name on any video track.")

    try:
        nodes = item.GetNumNodes()
        nodes = int(nodes) if nodes is not None else None
    except Exception:
        nodes = None                      # older Resolve will not say

    if nodes is not None and nodes < len(GRAPH):
        short = len(GRAPH) - nodes
        die(f"{item.GetName()} has {nodes} node(s); the graph needs {len(GRAPH)}.",
            f"Add {short} more, then run this again:",
            "  - Color page, select the clip",
            f"  - press Alt+S {short} time(s)",
            "  - with an empty graph, right-click the node editor first:",
            "    Add Node > Add Serial",
            "",
            "Resolve's API cannot create nodes. This is the only manual step.")

    print(f"\n[3/3] applying {len(GRAPH)} nodes to {item.GetName()}...")
    project.RefreshLUTList()
    resolve.OpenPage("color")

    for index, (label, op) in enumerate(GRAPH, start=1):
        if op.get("lut"):
            if not item.SetLUT(index, lut):
                die(f"SetLUT failed on node {index} with:", f"  {lut}")
        elif not op.get("off"):
            if not item.SetCDL({
                "NodeIndex": str(index),
                "Slope": " ".join([f"{op.get('slope', 1.0):.6f}"] * 3),
                "Offset": "0.0 0.0 0.0",
                "Power": "1.0 1.0 1.0",
                "Saturation": f"{op.get('sat', 1.0):.6f}",
            }):
                die(f"SetCDL failed on node {index}")
        try:
            item.SetNodeLabel(index, label)
            if op.get("off"):
                item.SetNodeEnabled(index, False)
        except AttributeError:
            pass                           # older Resolve; the grade still landed
        print(f"      {index}. {label}")

    try:
        item.SetClipColor("Orange")
    except Exception:
        pass

    print("\n" + "=" * 52)
    print(" Done. Still by hand:")
    print("   node 05: switch it on, put a soft window on the singer")
    print("   node 06: the last word, once you have watched it through")
    print(" Ctrl+Z on the Color page steps all of this back.")
    print("=" * 52)
    input("\nPress Enter to close...")


if __name__ == "__main__":
    main()
