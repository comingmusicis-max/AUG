"""Download brief media to local disk and probe it with ffprobe.

Usage:
    python fetch_media.py media.json [--dest DIR]

media.json:
    {"dest": "D:/ClinicVideo/job-name",
     "files": [{"name": "C1004.MP4", "url": "https://www.dropbox.com/..."}]}

Writes <dest>/media_report.json describing every file that landed: duration,
display dimensions, rotation and whether it carries audio. Read that before
building a timeline — it is what catches a trim point past the end of a clip.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

# Dropbox share links render a preview page unless asked for the bytes.
DROPBOX_HOSTS = ("dropbox.com", "www.dropbox.com")


def direct_url(url: str) -> str:
    """Rewrite a share link so it serves the file rather than a viewer page."""
    parts = urllib.parse.urlsplit(url)
    if not any(parts.netloc.endswith(h) for h in DROPBOX_HOSTS):
        return url
    q = urllib.parse.parse_qs(parts.query)
    q["dl"] = ["1"]
    return urllib.parse.urlunsplit(
        parts._replace(query=urllib.parse.urlencode(q, doseq=True))
    )


def download(url: str, out: str) -> None:
    req = urllib.request.Request(
        direct_url(url),
        # Dropbox serves the HTML preview to clients it does not recognise.
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    tmp = out + ".part"
    with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    os.replace(tmp, out)  # a partial download must never look complete


def probe(path: str) -> dict:
    """Duration, display dimensions and audio presence for one file."""
    try:
        raw = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", path],
            capture_output=True, text=True, check=True,
        ).stdout
    except FileNotFoundError:
        return {"error": "ffprobe not installed"}
    except subprocess.CalledProcessError as exc:
        return {"error": f"unreadable: {exc.stderr.strip()[:200]}"}

    info = json.loads(raw)
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if not video:
        return {"error": "no video or image stream"}

    w, h = int(video["width"]), int(video["height"])
    rotation = 0
    for sd in video.get("side_data_list", []):
        if "rotation" in sd:
            rotation = int(sd["rotation"])
    # A rotation flag means the stored frame is sideways; report what a viewer
    # actually sees, since that is what the timeline has to match.
    if abs(rotation) in (90, 270):
        w, h = h, w

    try:
        duration = round(float(info["format"]["duration"]), 3)
    except (KeyError, ValueError):
        duration = None  # stills have no duration

    return {
        "duration": duration,
        "width": w, "height": h, "rotation": rotation,
        "portrait": h > w,
        "has_audio": any(s["codec_type"] == "audio" for s in info["streams"]),
        "bytes": os.path.getsize(path),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--dest", help="overrides dest in the manifest")
    args = ap.parse_args()

    with open(args.manifest, encoding="utf-8") as f:
        manifest = json.load(f)

    dest = args.dest or manifest.get("dest")
    if not dest:
        print("no dest given, in the manifest or on the command line")
        return 2
    os.makedirs(dest, exist_ok=True)

    files = manifest["files"]
    report, failed = {}, []

    for i, entry in enumerate(files, 1):
        name, url = entry["name"], entry["url"]
        out = os.path.join(dest, name)

        if os.path.exists(out) and os.path.getsize(out) > 0:
            print(f"[{i}/{len(files)}] skip  {name}")
        else:
            try:
                download(url, out)
                mb = os.path.getsize(out) / (1 << 20)
                print(f"[{i}/{len(files)}] ok    {name}  {mb:.1f} MB")
            except Exception as exc:
                print(f"[{i}/{len(files)}] FAIL  {name}  {exc}")
                failed.append(name)
                if os.path.exists(out):
                    os.remove(out)
                continue

        report[name] = probe(out)

    report_path = os.path.join(dest, "media_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\nreport: {report_path}")
    print(f"{'file':<18}{'duration':>10}  {'size':>11}  notes")
    for name, m in report.items():
        if "error" in m:
            print(f"{name:<18}{'—':>10}  {'—':>11}  ERROR: {m['error']}")
            continue
        dur = f"{m['duration']:.2f}s" if m["duration"] else "still"
        notes = []
        if not m["portrait"]:
            notes.append("landscape")
        if not m["has_audio"]:
            notes.append("no audio")
        print(f"{name:<18}{dur:>10}  {m['width']:>5}x{m['height']:<5}  "
              f"{', '.join(notes)}")

    if failed:
        print(f"\n{len(failed)} failed: {', '.join(failed)}")
        print("re-run to retry — completed files are skipped")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
