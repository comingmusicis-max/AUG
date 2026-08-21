"""Find where CapCut actually keeps its drafts, and say what is in there.

`build_draft.py` writes to one hardcoded default. CapCut has shipped several
draft locations across versions and lets the user move the folder in Settings,
so a build that prints success while the project list stays empty usually means
the draft landed somewhere this installation does not read.

This prints every draft root it can find, what is inside each, and the exact
--draft-root to pass. It writes nothing.
"""

import argparse
import json
import os
import time

CANDIDATES = [
    r"%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft",
    r"%APPDATA%\CapCut\User Data\Projects\com.lveditor.draft",
    r"%LOCALAPPDATA%\CapCut\User Data\Projects",
    r"%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft",
    r"%APPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft",
    "~/Movies/CapCut/User Data/Projects/com.lveditor.draft",
    "~/Library/Application Support/CapCut/User Data/Projects/com.lveditor.draft",
]

# CapCut records a moved draft folder in its own settings. The key name has
# changed between versions, so match on values that look like a path rather
# than on any one key.
SETTINGS_FILES = [
    r"%LOCALAPPDATA%\CapCut\User Data\Config\globalSetting",
    r"%LOCALAPPDATA%\CapCut\User Data\Config\globalSetting.json",
    r"%APPDATA%\CapCut\User Data\Config\globalSetting",
]


def expand(p):
    return os.path.expanduser(os.path.expandvars(p))


def from_settings():
    """Draft folders named inside CapCut's own settings files."""
    found = []
    for raw in SETTINGS_FILES:
        path = expand(raw)
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
        except Exception:
            continue

        def walk(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    walk(v)
            elif isinstance(obj, str) and len(obj) < 260 and os.path.isdir(obj):
                if "draft" in obj.lower() or "projects" in obj.lower():
                    found.append((obj, f"named in {os.path.basename(path)}"))
        walk(data)
    return found


def scan_profile(limit_depth=6):
    """Last resort: hunt for com.lveditor.draft under the user's profile."""
    home = expand("%USERPROFILE%") if os.name == "nt" else os.path.expanduser("~")
    if not os.path.isdir(home):
        return []
    skip = {"node_modules", ".git", "Temp", "Windows", "Cache"}
    hits = []
    base_depth = home.rstrip(os.sep).count(os.sep)
    for root, dirs, _ in os.walk(home):
        if root.count(os.sep) - base_depth >= limit_depth:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in skip and not d.startswith("$")]
        if "com.lveditor.draft" in dirs:
            hits.append((os.path.join(root, "com.lveditor.draft"),
                         "found by scanning your profile"))
            dirs.remove("com.lveditor.draft")
    return hits


def projects_in(root):
    out = []
    try:
        names = os.listdir(root)
    except OSError:
        return out
    for name in names:
        content = os.path.join(root, name, "draft_content.json")
        if os.path.exists(content):
            st = os.stat(content)
            out.append((name, st.st_size, st.st_mtime))
    return sorted(out, key=lambda r: r[2], reverse=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expect", nargs="*", default=[],
                    help="project names you expected to find")
    ap.add_argument("--scan", action="store_true",
                    help="also hunt through the whole user profile (slow)")
    args = ap.parse_args()

    roots, seen = [], set()
    for raw in CANDIDATES:
        p = expand(raw)
        if os.path.isdir(p) and p.lower() not in seen:
            seen.add(p.lower())
            roots.append((p, "standard location"))
    for p, why in from_settings():
        if p.lower() not in seen:
            seen.add(p.lower())
            roots.append((p, why))
    if args.scan:
        for p, why in scan_profile():
            if p.lower() not in seen:
                seen.add(p.lower())
                roots.append((p, why))

    if not roots:
        print("no CapCut draft folder found.")
        print("open CapCut, save one empty project, then run this again.")
        if not args.scan:
            print("or re-run with --scan to search your whole user profile.")
        return 1

    expected = set(args.expect)
    hit_anywhere = {}
    for root, why in roots:
        items = projects_in(root)
        print(f"\n{root}\n  ({why}) - {len(items)} project(s)")
        for name, size, mtime in items[:12]:
            stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
            mark = "  <-- expected" if name in expected else ""
            print(f"    {stamp}  {size/1024:8.0f} KB  {name}{mark}")
            if name in expected:
                hit_anywhere.setdefault(name, root)
        if len(items) > 12:
            print(f"    ... and {len(items) - 12} more")

    if expected:
        print()
        for name in sorted(expected):
            where = hit_anywhere.get(name)
            if where:
                print(f"'{name}' is on disk at {where}")
            else:
                print(f"'{name}' is NOT in any draft folder - the build did not "
                      "write it, or wrote it somewhere none of these cover")
        if hit_anywhere:
            print("\nif CapCut's list still does not show it, quit CapCut "
                  "completely and reopen - it reads the folder at startup.")

    print("\nto build into a specific one:")
    print(f'  python build_draft.py <plan> --draft-root "{roots[0][0]}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
