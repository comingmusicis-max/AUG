"""Check the LUT maths, including that looks meant to cut together do.

A LUT that clips whites or crushes blacks looks fine in a thumbnail and wrong
on a grade, so the checks here are on values, not vibes.

    python tests/test_make_lut.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))

from make_lut import DEFAULTS, apply_look, build_cube, load_look  # noqa: E402

LOOKS = os.path.join(SKILL, "looks")


def look(name):
    return load_look(os.path.join(LOOKS, name + ".json"))


def lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def test_defaults_are_identity():
    worst = 0.0
    for r in range(0, 33, 4):
        for g in range(0, 33, 4):
            for b in range(0, 33, 4):
                v = (r / 32, g / 32, b / 32)
                out = apply_look(*v, dict(DEFAULTS))
                worst = max(worst, max(abs(a - o) for a, o in zip(v, out)))
    assert worst == 0.0, f"a look with no settings changed the image by {worst}"


def test_every_shipped_look_stays_in_range():
    for name in ("clinic_clean", "clinic_warm", "premium_grey",
                 "golden_hour", "stage_indoor"):
        spec = look(name)
        for r in range(0, 33, 4):
            for g in range(0, 33, 4):
                for b in range(0, 33, 4):
                    out = apply_look(r / 32, g / 32, b / 32, spec)
                    assert all(0.0 <= v <= 1.0 for v in out), f"{name} went out of range: {out}"


def test_black_and_white_are_not_clipped_away():
    for name in ("clinic_clean", "golden_hour", "stage_indoor"):
        spec = look(name)
        white = apply_look(1.0, 1.0, 1.0, spec)
        assert min(white) > 0.7, f"{name} crushes white to {white}"
        black = apply_look(0.0, 0.0, 0.0, spec)
        assert max(black) < 0.15, f"{name} lifts black to {black}, that is fog"


def test_skin_protect_spares_skin_and_nothing_else():
    hot = dict(DEFAULTS, saturation=1.6, skin_protect=0.9)
    raw = dict(DEFAULTS, saturation=1.6)
    skin = (0.78, 0.60, 0.50)
    sky = (0.35, 0.55, 0.85)

    moved = lambda a, b: max(abs(x - y) for x, y in zip(a, b))
    assert moved(apply_look(*skin, hot), skin) < moved(apply_look(*skin, raw), skin), \
        "protection did not reduce the move on skin"
    assert moved(apply_look(*sky, hot), apply_look(*sky, raw)) < 0.001, \
        "protection leaked onto a colour that is not skin"


def test_the_two_jj_looks_cut_together():
    """Two lighting setups in one edit. If black level or skin jump at the cut,
    the audience reads it as a mistake — so the looks may differ in white
    balance and almost nothing else."""
    gold, stage = look("golden_hour"), look("stage_indoor")

    for probe in ((0.03, 0.03, 0.035), (0.435, 0.435, 0.435)):
        gap = abs(lum(apply_look(*probe, gold)) - lum(apply_look(*probe, stage)))
        assert gap < 0.02, f"levels split by {gap:.3f} at {probe}"

    # Skin as each setup delivers it: sunset warm, tungsten warmer still.
    g = apply_look(0.72, 0.55, 0.45, gold)
    s = apply_look(0.74, 0.53, 0.41, stage)
    assert max(abs(a - b) for a, b in zip(g, s)) < 0.03, \
        f"skin lands differently: {g} vs {s}"


def test_cube_file_is_well_formed():
    spec = dict(look("golden_hour"), size=9)
    lines = [l for l in build_cube(spec).splitlines() if l.strip()]
    assert lines[1] == "LUT_3D_SIZE 9"
    entries = [l for l in lines if len(l.split()) == 3 and l[0].isdigit()]
    assert len(entries) == 9 ** 3, f"expected {9**3} entries, got {len(entries)}"
    # Red varies fastest in a .cube; entry 1 must differ from entry 0 in red.
    first, second = [float(x) for x in entries[0].split()], [float(x) for x in entries[1].split()]
    assert second[0] > first[0], "entries are not ordered with red varying fastest"


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
