"""Get a handle on a running DaVinci Resolve, or say exactly why not.

Every other script here needs the same three things: the scripting module on
sys.path, a running Resolve, and an open project. Getting any of them wrong
produces the same unhelpful ImportError, so the diagnosis lives here once.

Inside Resolve's own Console the `resolve` object already exists and the
import is unnecessary — that path is handled too, which is what makes these
scripts usable on the free version.
"""

import os
import sys

# Where Blackmagic installs the scripting module, per platform. RESOLVE_SCRIPT_API
# overrides all of these when the user has set it.
API_PATHS = {
    "win32": [
        r"%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting",
    ],
    "darwin": [
        "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting",
    ],
    "linux": [
        "/opt/resolve/Developer/Scripting",
        "/home/resolve/Developer/Scripting",
    ],
}

LIB_PATHS = {
    "win32": [
        r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll",
    ],
    "darwin": [
        "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so",
    ],
    "linux": [
        "/opt/resolve/libs/Fusion/fusionscript.so",
    ],
}


def platform_key():
    if sys.platform.startswith("win"):
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def expand(p):
    return os.path.expanduser(os.path.expandvars(p))


def api_candidates():
    out = []
    env = os.environ.get("RESOLVE_SCRIPT_API")
    if env:
        out.append(expand(env))
    out.extend(expand(p) for p in API_PATHS[platform_key()])
    return out


def lib_candidates():
    out = []
    env = os.environ.get("RESOLVE_SCRIPT_LIB")
    if env:
        out.append(expand(env))
    out.extend(expand(p) for p in LIB_PATHS[platform_key()])
    return out


def find_api():
    """Directory holding Modules/DaVinciResolveScript.py, or None."""
    for base in api_candidates():
        if os.path.isfile(os.path.join(base, "Modules", "DaVinciResolveScript.py")):
            return base
    return None


def find_lib():
    for path in lib_candidates():
        if os.path.isfile(path):
            return path
    return None


def get_resolve():
    """A Resolve handle. Raises SystemExit with a fixable message if it can't."""
    # Running inside Resolve's Console: the app injects these, and the free
    # version allows nothing else.
    injected = globals().get("resolve") or sys.modules["__main__"].__dict__.get("resolve")
    if injected is not None:
        return injected

    api = find_api()
    if api is None:
        raise SystemExit(
            "DaVinciResolveScript.py not found.\n"
            "Looked in:\n  " + "\n  ".join(api_candidates()) + "\n"
            "Run scripts/doctor.py — it prints the exact paths for this machine."
        )

    modules = os.path.join(api, "Modules")
    if modules not in sys.path:
        sys.path.append(modules)

    lib = find_lib()
    if lib and not os.environ.get("RESOLVE_SCRIPT_LIB"):
        os.environ["RESOLVE_SCRIPT_LIB"] = lib

    try:
        import DaVinciResolveScript as dvr
    except ImportError as e:
        raise SystemExit(f"could not import DaVinciResolveScript: {e}\nRun scripts/doctor.py")

    handle = dvr.scriptapp("Resolve")
    if handle is None:
        raise SystemExit(
            "Resolve is not answering. Three things do it, in this order:\n"
            "  1. DaVinci Resolve must be open, with a project loaded.\n"
            "  2. Preferences > System > General > 'External scripting using'\n"
            "     must be set to Local (not None). Restart Resolve after changing it.\n"
            "  3. External scripting needs Resolve Studio. On the free version,\n"
            "     paste the script into Workspace > Console instead."
        )
    return handle


def get_project(resolve, name=None):
    """The named project, or the open one. Opens it if it isn't current."""
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()

    if name:
        if project is None or project.GetName() != name:
            opened = pm.LoadProject(name)
            if opened is None:
                available = pm.GetProjectListInCurrentFolder() or []
                raise SystemExit(
                    f"no project named {name!r} in the current Project Manager folder.\n"
                    "Here it holds: " + (", ".join(available) if available else "(nothing)") + "\n"
                    "If it lives in a subfolder or another database, open it in "
                    "Resolve first and re-run without --project."
                )
            project = opened

    if project is None:
        raise SystemExit("no project is open in Resolve. Open one and re-run.")
    return project


def get_timeline(project, name=None):
    if name:
        for i in range(1, (project.GetTimelineCount() or 0) + 1):
            tl = project.GetTimelineByIndex(i)
            if tl and tl.GetName() == name:
                project.SetCurrentTimeline(tl)
                return tl
        names = [project.GetTimelineByIndex(i).GetName()
                 for i in range(1, (project.GetTimelineCount() or 0) + 1)]
        raise SystemExit(f"no timeline named {name!r}. This project has: {', '.join(names) or '(none)'}")

    tl = project.GetCurrentTimeline()
    if tl is None:
        raise SystemExit("no timeline is open. Open one, or pass --timeline.")
    return tl


def video_items(timeline):
    """Every video clip in the timeline as (track, index_in_track, item)."""
    out = []
    for track in range(1, (timeline.GetTrackCount("video") or 0) + 1):
        items = timeline.GetItemListInTrack("video", track) or []
        for i, item in enumerate(items, start=1):
            out.append((track, i, item))
    return out
