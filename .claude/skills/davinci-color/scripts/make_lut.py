"""Turn a written look into a .cube LUT.

The point of driving Resolve by script is that a look becomes a number you can
write down, re-run, and hand to someone else. Colour wheels can't be written
down; a LUT can. This builds one from a JSON look file so the same grade lands
identically on every clip, every job, every re-cut.

The maths runs on Rec.709 display-referred values (an ordinary camera clip with
the Rec.709 profile baked in — what a clinic shoot on a mirrorless produces).
Put the LUT after any input transform, not before.

    python scripts/make_lut.py looks/clinic_clean.json --install
"""

import argparse
import colorsys
import json
import os
import sys

DEFAULTS = {
    "name": "look",
    "size": 33,
    "temp": 0.0,          # + warmer (more red, less blue)
    "tint": 0.0,          # + greener, - magenta
    "exposure": 0.0,      # stops
    "contrast": 1.0,
    "pivot": 0.435,       # Resolve's own default contrast pivot
    "saturation": 1.0,
    "skin_protect": 0.0,  # 0..1, how much to spare skin hues from saturation
    "lift": [0.0, 0.0, 0.0],
    "gamma": [1.0, 1.0, 1.0],
    "gain": [1.0, 1.0, 1.0],
}

GAMMA = 2.2           # display gamma used to linearise for exposure
SKIN_HUE = 0.072      # ~26 deg, the centre of the skin band
SKIN_WIDTH = 0.055


def load_look(path):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    unknown = set(raw) - set(DEFAULTS) - {"note"}
    if unknown:
        raise SystemExit(f"{path}: unknown key(s): {', '.join(sorted(unknown))}\n"
                         f"valid keys: {', '.join(sorted(DEFAULTS))}")
    look = dict(DEFAULTS)
    look.update(raw)
    for key in ("lift", "gamma", "gain"):
        vals = look[key]
        if not isinstance(vals, list) or len(vals) != 3:
            raise SystemExit(f"{path}: {key} must be a list of three numbers [r, g, b]")
        look[key] = [float(v) for v in vals]
    if any(g <= 0 for g in look["gamma"]):
        raise SystemExit(f"{path}: gamma values must be greater than 0")
    if not 2 <= int(look["size"]) <= 65:
        raise SystemExit(f"{path}: size must be between 2 and 65 (33 is standard)")
    return look


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def skin_weight(r, g, b):
    """1 where the colour sits in the skin band, falling off to 0 elsewhere.

    Desaturated pixels get little weight: a grey wall shares its hue with skin
    but nobody minds if it saturates.
    """
    h, s, _ = colorsys.rgb_to_hsv(r, g, b)
    d = abs(h - SKIN_HUE)
    d = min(d, 1.0 - d)                       # hue wraps
    hue_w = 2.718281828 ** (-(d * d) / (2 * SKIN_WIDTH * SKIN_WIDTH))
    return hue_w * min(s / 0.25, 1.0)


def apply_look(r, g, b, look):
    # 1. White balance, as plain channel gains.
    kr = 1.0 + look["temp"] / 500.0
    kb = 1.0 - look["temp"] / 500.0
    kg = 1.0 + look["tint"] / 500.0
    r, g, b = r * kr, g * kg, b * kb

    # 2. Exposure belongs in linear light, or highlights curdle.
    if look["exposure"]:
        scale = 2.0 ** look["exposure"]
        r, g, b = [(clamp(v) ** GAMMA * scale) ** (1.0 / GAMMA) for v in (r, g, b)]

    # 3. Lift / gamma / gain, per channel — the ASC-style trio.
    out = []
    for v, lift, gam, gain in zip((r, g, b), look["lift"], look["gamma"], look["gain"]):
        v = clamp(v * gain + lift)
        out.append(v ** (1.0 / gam))
    r, g, b = out

    # 4. Contrast around the pivot.
    if look["contrast"] != 1.0:
        c, p = look["contrast"], look["pivot"]
        r, g, b = [(v - p) * c + p for v in (r, g, b)]

    # 5. Saturation, sparing skin by however much was asked for.
    if look["saturation"] != 1.0:
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        sat = look["saturation"]
        if look["skin_protect"]:
            w = skin_weight(clamp(r), clamp(g), clamp(b))
            sat = 1.0 + (sat - 1.0) * (1.0 - look["skin_protect"] * w)
        r, g, b = [lum + (v - lum) * sat for v in (r, g, b)]

    return clamp(r), clamp(g), clamp(b)


def build_cube(look):
    size = int(look["size"])
    lines = [
        f'TITLE "{look["name"]}"',
        f"LUT_3D_SIZE {size}",
        "DOMAIN_MIN 0.0 0.0 0.0",
        "DOMAIN_MAX 1.0 1.0 1.0",
        "",
    ]
    step = size - 1
    # .cube runs red fastest, then green, then blue.
    for bi in range(size):
        for gi in range(size):
            for ri in range(size):
                r, g, b = apply_look(ri / step, gi / step, bi / step, look)
                lines.append(f"{r:.6f} {g:.6f} {b:.6f}")
    return "\n".join(lines) + "\n"


def resolve_lut_dir():
    if sys.platform.startswith("win"):
        return os.path.expandvars(
            r"%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\LUT")
    if sys.platform == "darwin":
        return "/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT"
    return "/opt/resolve/LUT"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("look", help="JSON look file")
    ap.add_argument("--out", help="where to write the .cube (default: next to the look file)")
    ap.add_argument("--install", action="store_true",
                    help="write into Resolve's LUT folder so it shows up in the node menu")
    args = ap.parse_args()

    look = load_look(args.look)
    if look["name"] == "look":
        look["name"] = os.path.splitext(os.path.basename(args.look))[0]

    if args.out:
        out = args.out
    elif args.install:
        out = os.path.join(resolve_lut_dir(), look["name"] + ".cube")
    else:
        out = os.path.join(os.path.dirname(os.path.abspath(args.look)), look["name"] + ".cube")

    folder = os.path.dirname(os.path.abspath(out))
    if not os.path.isdir(folder):
        if args.install:
            raise SystemExit(
                f"Resolve's LUT folder is not where expected:\n  {folder}\n"
                "Pass --out with the folder Resolve lists under "
                "Project Settings > Color Management > Open LUT Folder.")
        os.makedirs(folder, exist_ok=True)

    try:
        with open(out, "w", encoding="utf-8") as f:
            f.write(build_cube(look))
    except PermissionError:
        raise SystemExit(
            f"no permission to write {out}\n"
            "Resolve's LUT folder is machine-wide. Run this terminal as "
            "Administrator, or use --out to write somewhere else and point "
            "apply_grade.py at that path instead.")

    n = int(look["size"]) ** 3
    print(f"wrote {out}  ({look['size']}^3 = {n} entries)")
    if args.install:
        print("In Resolve: right-click the LUT list > Update Lists, or run "
              "apply_grade.py, which refreshes it for you.")


if __name__ == "__main__":
    main()
