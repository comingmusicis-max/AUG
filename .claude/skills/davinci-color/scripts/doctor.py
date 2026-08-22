"""Check whether this machine can drive Resolve by script, and say what is missing.

Scripting fails for four unrelated reasons that all look identical from the
outside: no Python, module not on the path, external scripting switched off, or
the free version refusing outside connections. This separates them and prints
the one fix that applies. It writes nothing and changes no setting.

    python scripts/doctor.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resolve_connect as rc  # noqa: E402


def line(ok, text):
    print(f"  [{'ok' if ok else '--'}] {text}")


def main():
    print(f"python {sys.version.split()[0]}  ({sys.platform})")
    if sys.version_info < (3, 6):
        print("  Resolve's scripting module needs Python 3.6 or newer.")

    print("\nscripting module (DaVinciResolveScript.py)")
    api = rc.find_api()
    if api:
        line(True, api)
    else:
        line(False, "not found. Looked in:")
        for p in rc.api_candidates():
            print(f"       {p}")
        print("     Resolve installs it with the app. If it is somewhere else, set")
        print("     RESOLVE_SCRIPT_API to the folder holding the Modules folder.")

    print("\nfusionscript library")
    lib = rc.find_lib()
    if lib:
        line(True, lib)
    else:
        line(False, "not found. Looked in:")
        for p in rc.lib_candidates():
            print(f"       {p}")

    print("\nenvironment")
    for var in ("RESOLVE_SCRIPT_API", "RESOLVE_SCRIPT_LIB", "PYTHONPATH"):
        val = os.environ.get(var)
        line(bool(val), f"{var}={val}" if val else f"{var} is not set")
    if api and not os.environ.get("RESOLVE_SCRIPT_API"):
        print("     Not fatal — these scripts add the path themselves. Set them only")
        print("     if you want to run other people's Resolve scripts too.")

    print("\nconnection")
    if api is None:
        line(False, "skipped, the module was not found")
        return 1
    try:
        resolve = rc.get_resolve()
    except SystemExit as e:
        line(False, "Resolve did not answer")
        for l in str(e).splitlines():
            print(f"       {l}")
        return 1

    product = resolve.GetProductName()
    line(True, f"{product} {resolve.GetVersionString()}")
    if "Studio" not in product:
        print("     This is the free version. It allows scripting only from inside")
        print("     the app: Workspace > Console, set to Py3, paste the script there.")
        print("     Running these files from a terminal needs Resolve Studio.")

    project = resolve.GetProjectManager().GetCurrentProject()
    if project is None:
        line(False, "no project open — open one before grading")
        return 1
    line(True, f"project {project.GetName()!r}")

    timeline = project.GetCurrentTimeline()
    if timeline is None:
        line(False, "no timeline open in that project")
        return 1
    line(True, f"timeline {timeline.GetName()!r}, "
               f"{timeline.GetTrackCount('video')} video track(s)")

    print("\nready. Next: inspect_project.py to dump what is in there.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
