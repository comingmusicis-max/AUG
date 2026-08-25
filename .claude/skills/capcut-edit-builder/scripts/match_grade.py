"""Match white balance and brightness across a job's footage, softly.

Usage:
    python match_grade.py <media_dir> [--ref FILE] [--write] [--preview]

Clinic footage from one shoot still drifts: the treatment room is warmer than
the counter, auto-exposure rides up when a face fills the frame, and the stills
come off a different camera than the clips. Cut together, every scene change
reads as a colour change.

This measures every file, picks one common white and one common brightness for
the whole job, and writes the ffmpeg chain that lands each file on it — plus a
final soft pass (lifted blacks, gentle desaturation) for the creamy white that
beauty briefs ask for.

Measurement is ffmpeg's signalstats, so there is nothing to pip install:

    YAVG        average luma          → brightness
    UAVG, VAVG  average Cb, Cr        → the colour cast, 128 being neutral

Read grade_report.json before running --write. A frame average is grey-world,
and grey-world is fooled by content: a clip that happens to hold a red logo or
a green scrub top reads as a colour cast that is not there. The report prints
how far each file is being moved so an obviously wrong one can be caught before
an hour of encoding. --ref pins the white to a clip already known to look right,
which beats the median whenever such a clip exists.
"""

import argparse
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".webp"}

# The "ละมุน" half of the grade — the part that is taste, not measurement.
# Everything above these lines only makes the files agree with each other; these
# lines decide what they agree *on*. Tune here, re-run, look at --preview.
SOFT = {
    # Where a mid-grey should land, 0..1. Beauty briefs read 0.5 as dull, so
    # aim a little brighter than a metered exposure would.
    "target_luma": 0.60,
    # Creamy rather than clinical: a touch less blue, a touch more red.
    # In Cb/Cr offsets from neutral 128 — negative U is warmer, positive V redder.
    "warm_u": -2.0,
    "warm_v": +2.0,
    # Lifted blacks. The single biggest contributor to "ละมุน" — it takes the
    # hard contrast out of the shot without touching the highlights.
    "black_lift": 0.045,
    "saturation": 0.95,
    "contrast": 0.97,
    # How far to pull each file onto the common white. 1.0 fully neutralises
    # every clip to the same average, which over-corrects a clip whose content
    # is genuinely coloured; 0.8 keeps most of the match and most of the safety.
    "wb_strength": 0.80,
    # A clip metered far from the target should not be dragged the whole way —
    # past this the noise floor comes up and the highlights flatten out.
    "gamma_range": (0.65, 1.55),
}

ENCODE = ["-c:v", "libx264", "-crf", "18", "-preset", "medium",
          "-pix_fmt", "yuv420p", "-c:a", "copy"]


# ── Measurement ───────────────────────────────────────────────────────


def media_files(media_dir: str) -> list:
    """Source media only — never this script's own output.

    Re-running in place is normal (measure, tweak SOFT, measure again), and
    measuring a graded file back in would drag the target toward the grade.
    """
    out = []
    for name in sorted(os.listdir(media_dir)):
        if not os.path.isfile(os.path.join(media_dir, name)):
            continue
        if name.endswith("_before_after.jpg"):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext in VIDEO_EXT or ext in IMAGE_EXT:
            out.append(name)
    return out


def measure(path: str, samples: int = 12) -> dict:
    """Average luma and chroma over frames spread across the file.

    Sampling beats reading every frame: a 40-second clip is a few hundred
    frames of the same room, and the average stops moving after a dozen.
    """
    is_video = os.path.splitext(path)[1].lower() in VIDEO_EXT
    # fps=... on a still is harmless; on a video it thins the stream out to
    # roughly `samples` frames without seeking around.
    vf = "scale=320:-2,signalstats,metadata=print:file=-"
    if is_video:
        dur = probe_duration(path) or 0
        if dur > 1:
            vf = (f"fps={max(samples / dur, 0.05):.4f},"
                  f"scale=320:-2,signalstats,metadata=print:file=-")

    try:
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path, "-vf", vf, "-f", "null", "-"],
            capture_output=True, text=True, timeout=900,
        )
    except FileNotFoundError:
        return {"error": "ffmpeg not installed"}
    except subprocess.TimeoutExpired:
        return {"error": "timed out while measuring"}

    vals = {"YAVG": [], "UAVG": [], "VAVG": []}
    for key, num in re.findall(r"lavfi\.signalstats\.(\w+)=([-\d.]+)", proc.stdout):
        if key in vals:
            vals[key].append(float(num))

    if not vals["YAVG"]:
        return {"error": "no frames measured: " + proc.stderr.strip()[:160]}

    return {
        "frames": len(vals["YAVG"]),
        "y": statistics.mean(vals["YAVG"]),
        "u": statistics.mean(vals["UAVG"]),
        "v": statistics.mean(vals["VAVG"]),
    }


def probe_duration(path: str):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=60,
        ).stdout.strip()
        return float(out)
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        return None


# ── The grade ─────────────────────────────────────────────────────────


def norm_luma(y: float) -> float:
    """signalstats reports raw Y; video is normally limited range 16-235."""
    return min(max((y - 16.0) / 219.0, 0.01), 0.99)


def build_chain(m: dict, target_u: float, target_v: float) -> dict:
    """The per-file correction, as ffmpeg filters and as human numbers."""
    du = (target_u - m["u"]) * SOFT["wb_strength"]
    dv = (target_v - m["v"]) * SOFT["wb_strength"]

    measured = norm_luma(m["y"])
    target = SOFT["target_luma"]
    # y^(1/gamma) = target, solved for gamma. Gamma rather than a brightness
    # offset because it leaves 0 and 1 pinned — a lift that does not clip the
    # whites off a bright clinic wall.
    gamma = (math.log(measured) / math.log(target)) if measured != target else 1.0
    lo, hi = SOFT["gamma_range"]
    clamped = not (lo <= gamma <= hi)
    gamma = min(max(gamma, lo), hi)

    lift = SOFT["black_lift"]
    chain = [
        f"lutyuv=u='clip(val+{du:.2f},0,255)':v='clip(val+{dv:.2f},0,255)'",
        f"eq=gamma={gamma:.4f}:saturation={SOFT['saturation']}:"
        f"contrast={SOFT['contrast']}",
        f"curves=all='0/{lift:.3f} 0.5/{0.5 + lift / 3:.3f} 1/1'",
    ]
    return {
        "du": du, "dv": dv, "gamma": gamma, "gamma_clamped": clamped,
        "measured_luma": measured,
        # CapCut's sliders run -50..50 and are not calibrated to Cb/Cr, so this
        # is a starting position to nudge from, not a conversion.
        "capcut_temperature": round(-du * 1.6, 1),
        "capcut_tint": round(dv * 1.6, 1),
        "capcut_brightness": round((target - measured) * 100, 1),
        "vf": ",".join(chain),
    }


# ── Rendering ─────────────────────────────────────────────────────────


def render(src: str, dst: str, vf: str) -> bool:
    ext = os.path.splitext(src)[1].lower()
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", vf]
    if ext in IMAGE_EXT:
        cmd += ["-q:v", "2"]
    else:
        cmd += ENCODE
    cmd.append(dst)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"      FAIL {r.stderr.strip()[:200]}")
        return False
    return True


def preview(src: str, dst_dir: str, vf: str, name: str) -> None:
    """One frame, ungraded beside graded, so the grade can be judged by eye."""
    out = os.path.join(dst_dir, os.path.splitext(name)[0] + "_before_after.jpg")
    # A still has no duration to seek into; -ss on one would seek past the end
    # and quietly write nothing, which is how the photos went missing.
    dur = probe_duration(src)
    seek = ["-ss", f"{dur / 2:.2f}"] if dur and dur > 0.5 else []
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *seek, "-i", src,
         "-frames:v", "1", "-filter_complex",
         f"[0:v]scale=540:-2,split=2[a][b];[b]{vf}[g];[a][g]hstack",
         "-q:v", "3", out],
        capture_output=True, text=True,
    )


# ── Main ──────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("media_dir")
    ap.add_argument("--ref", help="file whose white the job matches to; "
                                  "default is the median of every file")
    ap.add_argument("--write", action="store_true",
                    help="render graded copies into <media_dir>/graded")
    ap.add_argument("--preview", action="store_true",
                    help="write one before/after still per file")
    ap.add_argument("--only", nargs="*", help="limit to these filenames")
    args = ap.parse_args()

    media_dir = args.media_dir
    if not os.path.isdir(media_dir):
        print(f"no such folder: {media_dir}")
        return 2

    names = args.only or media_files(media_dir)
    if not names:
        print(f"no media in {media_dir}")
        return 2

    print(f"measuring {len(names)} files\n")
    stats, failed = {}, []
    for i, name in enumerate(names, 1):
        m = measure(os.path.join(media_dir, name))
        if "error" in m:
            print(f"[{i}/{len(names)}] SKIP  {name}  {m['error']}")
            failed.append(name)
            continue
        print(f"[{i}/{len(names)}] {name:<18} luma {norm_luma(m['y']):.3f}  "
              f"U {m['u']:6.1f}  V {m['v']:6.1f}  ({m['frames']} frames)")
        stats[name] = m

    if not stats:
        print("\nnothing measurable")
        return 1

    if args.ref:
        if args.ref not in stats:
            print(f"\n--ref {args.ref} was not measured")
            return 2
        base_u, base_v = stats[args.ref]["u"], stats[args.ref]["v"]
        origin = f"reference file {args.ref}"
    else:
        base_u = statistics.median(m["u"] for m in stats.values())
        base_v = statistics.median(m["v"] for m in stats.values())
        origin = "median of all files"

    target_u = base_u + SOFT["warm_u"]
    target_v = base_v + SOFT["warm_v"]

    lumas = [norm_luma(m["y"]) for m in stats.values()]
    print(f"\nspread before: luma {min(lumas):.3f}–{max(lumas):.3f}  "
          f"U {min(m['u'] for m in stats.values()):.1f}–"
          f"{max(m['u'] for m in stats.values()):.1f}  "
          f"V {min(m['v'] for m in stats.values()):.1f}–"
          f"{max(m['v'] for m in stats.values()):.1f}")
    print(f"common white from {origin}, warmed to U {target_u:.1f} / V {target_v:.1f}")
    print(f"common brightness: luma {SOFT['target_luma']}\n")

    grades = {n: build_chain(m, target_u, target_v) for n, m in stats.items()}

    print(f"{'file':<18}{'ΔU':>7}{'ΔV':>7}{'gamma':>8}   CapCut temp/tint/bright")
    for name, g in grades.items():
        flag = "  ← clipped, check by eye" if g["gamma_clamped"] else ""
        print(f"{name:<18}{g['du']:>7.1f}{g['dv']:>7.1f}{g['gamma']:>8.3f}   "
              f"{g['capcut_temperature']:>5} / {g['capcut_tint']:>4} / "
              f"{g['capcut_brightness']:>5}{flag}")

    big = [n for n, g in grades.items() if abs(g["du"]) > 6 or abs(g["dv"]) > 6]
    if big:
        print(f"\nmoved a long way on colour: {', '.join(big)}")
        print("check these against a --preview still before trusting the number —"
              " a strongly coloured subject reads as a cast that is not there.")

    report = {
        "media_dir": media_dir,
        "white_from": origin,
        "target": {"u": target_u, "v": target_v, "luma": SOFT["target_luma"]},
        "soft": {k: v for k, v in SOFT.items() if k != "gamma_range"},
        "files": {n: {**stats[n], **grades[n]} for n in grades},
        "unmeasurable": failed,
    }
    report_path = os.path.join(media_dir, "grade_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nreport: {report_path}")

    out_dir = os.path.join(media_dir, "graded")
    # Deliberately not inside graded/: the edit plan points media_dir at that
    # folder, and a contact sheet sitting in it would be picked up as a clip.
    preview_dir = os.path.join(media_dir, "grade_preview")

    if args.preview:
        os.makedirs(preview_dir, exist_ok=True)
        print("\nwriting before/after stills")
        for name, g in grades.items():
            preview(os.path.join(media_dir, name), preview_dir, g["vf"], name)
        print(f"      {preview_dir}/*_before_after.jpg — left ungraded, right graded")

    if not args.write:
        print("\nmeasured only. re-run with --write once the numbers look right.")
        return 0

    os.makedirs(out_dir, exist_ok=True)
    print(f"\nrendering into {out_dir}")
    bad = []
    for i, (name, g) in enumerate(grades.items(), 1):
        print(f"[{i}/{len(grades)}] {name}")
        if not render(os.path.join(media_dir, name),
                      os.path.join(out_dir, name), g["vf"]):
            bad.append(name)

    # A file that could not be measured still has to exist in the graded folder,
    # or an edit plan pointed at that folder loses a clip.
    for name in failed:
        shutil.copy2(os.path.join(media_dir, name), os.path.join(out_dir, name))
    if failed:
        print(f"copied ungraded: {', '.join(failed)}")

    if bad:
        print(f"\n{len(bad)} failed to render: {', '.join(bad)}")
        return 1

    print(f"\ndone. point media_dir in the edit plan at:\n  {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
