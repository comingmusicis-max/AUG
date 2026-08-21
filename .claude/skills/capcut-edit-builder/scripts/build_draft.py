"""Build a CapCut desktop draft from an edit plan.

Usage:
    python build_draft.py edit_plan.json [--force] [--draft-root DIR]

CapCut exposes no API, but its drafts are plain JSON folders on disk, so a
timeline can be written directly and opened as a normal project. The schema is
read from the drafts CapCut itself wrote on this machine rather than hardcoded,
so the output tracks whatever version is installed.

See references/capcut-draft-format.md for the on-disk layout.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid

US = 1_000_000  # CapCut stores every time value in microseconds

DEFAULT_DRAFT_ROOT = os.path.expandvars(
    r"%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft"
)
FALLBACK_STYLE = {
    "font": "", "color": "#ffffff", "stroke": "#000000", "size": 15.0,
}
STILL_MATERIAL_DURATION = 10800000000  # CapCut's stock "a photo never ends" length


def uid() -> str:
    """CapCut writes uppercase UUIDs with the version group in lowercase."""
    a, b, c, d, e = str(uuid.uuid4()).upper().split("-")
    return f"{a}-{b}-{c.lower()}-{d}-{e}"


def hex_to_rgb(h: str):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]


# ── Environment discovery ─────────────────────────────────────────────


def capcut_running() -> bool:
    if sys.platform != "win32":
        return False
    try:
        out = subprocess.run(["tasklist"], capture_output=True, text=True,
                             timeout=30).stdout.lower()
    except Exception:
        return False  # can't tell; the overwrite guard still protects us
    return "capcut.exe" in out


def find_template(draft_root: str) -> str:
    """The smallest existing draft, used for its auxiliary files.

    CapCut writes a dozen small side files next to draft_content.json
    (draft_settings, attachment_*.json …). Copying a real draft's copies is far
    more robust than trying to synthesise them, and the smallest draft is the
    one least likely to drag along heavy leftovers.
    """
    best, best_size = None, None
    for name in os.listdir(draft_root):
        content = os.path.join(draft_root, name, "draft_content.json")
        if not os.path.exists(content):
            continue
        size = os.path.getsize(content)
        if best_size is None or size < best_size:
            best, best_size = os.path.join(draft_root, name), size
    if not best:
        raise SystemExit(
            f"no existing CapCut draft found under {draft_root}\n"
            "create and save one empty project in CapCut first — its side files "
            "are used as the template."
        )
    return best


def detect_house_style(draft_root: str) -> dict:
    """Reuse the font and colours already used on this machine.

    A caption in the wrong font stands out immediately, so prefer whatever the
    most recent draft with text in it was using over an arbitrary default.
    """
    drafts = sorted(
        (os.path.join(draft_root, n) for n in os.listdir(draft_root)),
        key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0,
        reverse=True,
    )
    for d in drafts:
        content = os.path.join(d, "draft_content.json")
        if not os.path.exists(content):
            continue
        try:
            with open(content, encoding="utf-8") as f:
                texts = json.load(f).get("materials", {}).get("texts") or []
        except (OSError, ValueError):
            continue
        for t in texts:
            font = t.get("font_path") or ""
            if font and os.path.exists(font):
                return {
                    "font": font.replace("\\", "/"),
                    "color": t.get("text_color") or "#ffffff",
                    "stroke": t.get("border_color") or "#000000",
                    "size": float(t.get("font_size") or 15.0),
                }
    return dict(FALLBACK_STYLE)


def detect_schema_version(template_dir: str, draft_root: str) -> str:
    """Match the draft version CapCut is currently writing.

    Hardcoding this would silently produce stale drafts after a CapCut update,
    so take the highest version seen on disk.
    """
    best = None
    for name in os.listdir(draft_root):
        content = os.path.join(draft_root, name, "draft_content.json")
        if not os.path.exists(content):
            continue
        try:
            with open(content, encoding="utf-8") as f:
                v = json.load(f).get("new_version")
        except (OSError, ValueError):
            continue
        if v and (best is None or _ver(v) > _ver(best)):
            best = v
    return best or "181.0.0"


def _ver(s: str):
    try:
        return tuple(int(p) for p in s.split("."))
    except ValueError:
        return (0,)


# ── Media ─────────────────────────────────────────────────────────────


def probe(path: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True, check=True,
    ).stdout
    info = json.loads(out)
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if not video:
        raise SystemExit(f"{path}: no video or image stream")

    w, h = int(video["width"]), int(video["height"])
    for sd in video.get("side_data_list", []):
        # A rotation flag means the frame is stored sideways. CapCut materials
        # record display dimensions, so swap rather than leaving it landscape.
        if abs(int(sd.get("rotation", 0))) in (90, 270):
            w, h = h, w
    try:
        dur = int(float(info["format"]["duration"]) * US)
    except (KeyError, ValueError):
        dur = 0
    return {
        "path": os.path.abspath(path).replace("\\", "/"),
        "dur": dur, "w": w, "h": h,
        "audio": any(s["codec_type"] == "audio" for s in info["streams"]),
        "name": os.path.basename(path),
    }


# ── Draft pieces ──────────────────────────────────────────────────────

# Each segment must point at one entry in several small material tables, or
# CapCut treats the draft as corrupt. Bodies are constant; only the ids vary.
VIDEO_REFS = [
    ("speeds", {"type": "speed", "mode": 0, "speed": 1.0, "curve_speed": None}),
    ("placeholder_infos", {"type": "placeholder_info", "meta_type": "none",
                           "res_path": "", "res_text": "", "error_path": "",
                           "error_text": ""}),
    ("canvases", {"type": "canvas_color", "color": "", "blur": 0.0, "image": "",
                  "album_image": "", "source_platform": 0}),
    ("sound_channel_mappings", {"type": "none", "audio_channel_mapping": 0,
                                "is_config_open": False}),
    ("material_colors", {"is_color_clip": False, "is_gradient": False,
                         "solid_color": "", "gradient_colors": [],
                         "gradient_percents": [], "gradient_angle": 90.0,
                         "width": 0.0, "height": 0.0}),
    ("vocal_separations", {"type": "vocal_separation", "choice": 0,
                           "removed_sounds": [], "time_range": None,
                           "production_path": "", "final_algorithm": "",
                           "enter_from": ""}),
]

AUDIO_REFS = [
    ("speeds", {"type": "speed", "mode": 0, "speed": 1.0, "curve_speed": None}),
    ("placeholder_infos", {"type": "placeholder_info", "meta_type": "none",
                           "res_path": "", "res_text": "", "error_path": "",
                           "error_text": ""}),
    ("beats", {"type": "beats", "mode": 404, "gear": 404, "gear_count": 0,
               "enable_ai_beats": False, "user_beats": [],
               "user_delete_ai_beats": None,
               "ai_beats": {"beats_path": "", "beats_url": "", "melody_path": "",
                            "melody_url": "", "melody_percents": [0.0],
                            "beat_speed_infos": []}}),
    ("sound_channel_mappings", {"type": "none", "audio_channel_mapping": 0,
                                "is_config_open": False}),
    ("vocal_separations", {"type": "vocal_separation", "choice": 0,
                           "removed_sounds": [], "time_range": None,
                           "production_path": "", "final_algorithm": "",
                           "enter_from": ""}),
]

MATERIAL_BUCKETS = [
    "videos", "audios", "texts", "canvases", "speeds", "placeholder_infos",
    "sound_channel_mappings", "material_colors", "vocal_separations",
    "material_animations", "effects", "transitions", "audio_fades", "beats",
    "stickers", "drafts", "video_effects", "hsl", "images", "loudnesses",
    "masks", "realtime_denoises", "shapes", "smart_crops", "text_templates",
    "video_trackings", "digital_humans", "flowers", "green_screens",
    "log_color_wheels", "manual_deformations", "multi_language_refs",
    "plugin_effects", "primary_color_wheels", "time_marks", "tone_effects",
]


def segment(material_id, refs, src_start, dur, target_start,
            volume=1.0, render_index=0, track_render_index=0) -> dict:
    """The common segment body. CapCut rejects drafts with fields missing."""
    return {
        "id": uid(),
        "source_timerange": None if src_start is None
        else {"start": src_start, "duration": dur},
        "target_timerange": {"start": target_start, "duration": dur},
        "render_timerange": {"start": 0, "duration": 0},
        "material_id": material_id, "extra_material_refs": refs,
        "desc": "", "state": 0, "speed": 1.0, "is_loop": False,
        "is_tone_modify": False, "reverse": False, "intensifies_audio": False,
        "cartoon": False, "volume": volume, "last_nonzero_volume": volume or 1.0,
        "clip": {"scale": {"x": 1.0, "y": 1.0}, "rotation": 0.0,
                 "transform": {"x": 0.0, "y": 0.0},
                 "flip": {"vertical": False, "horizontal": False}, "alpha": 1.0},
        "uniform_scale": {"on": True, "value": 1.0},
        "render_index": render_index, "track_render_index": track_render_index,
        "keyframe_refs": [], "common_keyframes": [],
        "enable_lut": True, "enable_adjust": True, "enable_hsl": False,
        "enable_color_curves": True, "enable_hsl_curves": True,
        "enable_color_wheels": True, "enable_video_mask": True,
        "enable_mask_stroke": False, "enable_mask_shadow": False,
        "enable_color_adjust_pro": False, "enable_adjust_mask": False,
        "enable_smart_color_adjust": False, "enable_color_match_adjust": False,
        "enable_color_correct_adjust": False,
        "visible": True, "group_id": "", "is_placeholder": False,
        "template_id": "", "template_scene": "default", "track_attribute": 0,
        "hdr_settings": {"mode": 1, "intensity": 1.0, "nits": 1000},
        "caption_info": None, "lyric_keyframes": None,
        "responsive_layout": {"enable": False, "target_follow": "",
                              "size_layout": 0, "horizontal_pos_layout": 0,
                              "vertical_pos_layout": 0},
        "raw_segment_id": "", "digital_human_template_group_id": "",
        "color_correct_alg_result": "", "source": "segmentsourcenormal",
        "segment_color_tag": "",
    }


def add_refs(materials: dict, spec) -> list:
    ids = []
    for bucket, body in spec:
        rid = uid()
        materials[bucket].append({"id": rid, **body})
        ids.append(rid)
    return ids


# ── Build ─────────────────────────────────────────────────────────────


def build(plan: dict, draft_root: str, force: bool) -> None:
    media_dir = plan["media_dir"]
    canvas = plan.get("canvas") or {"width": 1080, "height": 1920}
    fps = float(plan.get("fps", 30))
    project = plan["project"]

    template = find_template(draft_root)
    style = {**detect_house_style(draft_root), **(plan.get("text_style") or {})}
    version = detect_schema_version(template, draft_root)

    cache = {}

    def media(name):
        if name not in cache:
            path = os.path.join(media_dir, name)
            if not os.path.exists(path):
                raise SystemExit(f"missing media: {path}")
            cache[name] = probe(path)
        return cache[name]

    materials = {k: [] for k in MATERIAL_BUCKETS}
    video_segs, text_segs, audio_segs = [], [], []
    cursor = 0
    timeline = []

    for scene in plan["scenes"]:
        scene_start = cursor

        for clip in scene.get("clips", []):
            m = media(clip["file"])
            is_still = "still" in clip

            if is_still:
                dur = int(float(clip["still"]) * US)
                src_start, mat_dur = 0, STILL_MATERIAL_DURATION
            else:
                src_start = int(float(clip.get("in", 0)) * US)
                end = int(float(clip["out"]) * US) if "out" in clip else m["dur"]
                dur = end - src_start
                mat_dur = m["dur"]
                if dur <= 0:
                    raise SystemExit(
                        f"{clip['file']}: in={clip.get('in', 0)} out={clip.get('out')} "
                        f"is an empty range"
                    )
                if end > m["dur"]:
                    raise SystemExit(
                        f"{clip['file']}: out={clip['out']}s runs past the clip, "
                        f"which is only {m['dur'] / US:.2f}s long"
                    )

            mat_id = uid()
            materials["videos"].append({
                "id": mat_id, "type": "photo" if is_still else "video",
                "path": m["path"], "material_name": m["name"],
                "duration": mat_dur, "width": m["w"], "height": m["h"],
                "has_audio": m["audio"] and not is_still,
                "crop": {"upper_left_x": 0.0, "upper_left_y": 0.0,
                         "upper_right_x": 1.0, "upper_right_y": 0.0,
                         "lower_left_x": 0.0, "lower_left_y": 1.0,
                         "lower_right_x": 1.0, "lower_right_y": 1.0},
                "crop_ratio": "free", "crop_scale": 1.0, "category_name": "local",
                "check_flag": 62978047, "source_platform": 0, "is_copyright": False,
                "extra_type_option": 0, "aigc_type": "none", "picture_from": "none",
                "matting": {"flag": 0, "path": "", "interactiveTime": [],
                            "strokes": [], "expansion": 0, "feather": 0,
                            "reverse": False},
                "stable": {"stable_level": 0, "matrix_path": "",
                           "time_range": {"start": 0, "duration": 0}},
            })
            video_segs.append(segment(
                mat_id, add_refs(materials, VIDEO_REFS), src_start, dur, cursor,
                volume=0.0 if clip.get("mute") else 1.0,
                render_index=len(video_segs),
            ))
            cursor += dur

        scene_dur = cursor - scene_start
        timeline.append({"name": scene.get("name", ""), "start": scene_start,
                         "duration": scene_dur})

        # Voiceover: laid back-to-back from the scene start unless placed with `at`.
        vo_cursor = scene_start
        for vo in scene.get("voice", []):
            m = media(vo["file"])
            src_start = int(float(vo.get("in", 0)) * US)
            end = int(float(vo["out"]) * US) if "out" in vo else m["dur"]
            dur = end - src_start
            if dur <= 0:
                raise SystemExit(f"{vo['file']}: voice trim is an empty range")
            at = scene_start + int(float(vo["at"]) * US) if "at" in vo else vo_cursor

            mat_id = uid()
            materials["audios"].append({
                "id": mat_id, "type": "extract_music", "path": m["path"],
                "name": m["name"], "duration": m["dur"], "music_id": uid(),
                "category_name": "local", "source_platform": 0, "check_flag": 1,
                "effect_id": "", "intensifies_path": "", "local_material_id": "",
                "wave_points": [], "is_ai_clone_tone": False,
                "is_text_edit_overdub": False,
            })
            audio_segs.append(segment(
                mat_id, add_refs(materials, AUDIO_REFS), src_start, dur, at))
            vo_cursor = at + dur

        # Text: spans the whole scene unless `at` / `dur` narrow it.
        for txt in scene.get("text", []):
            content = txt["content"]
            at = scene_start + int(float(txt.get("at", 0)) * US)
            dur = int(float(txt["dur"]) * US) if "dur" in txt else \
                scene_dur - (at - scene_start)
            if dur <= 0:
                continue

            mat_id = uid()
            materials["texts"].append({
                "id": mat_id, "type": "text",
                "content": json.dumps({
                    "text": content,
                    "styles": [{
                        "fill": {"content": {"render_type": "solid",
                                             "solid": {"color": hex_to_rgb(style["color"])}}},
                        "font": {"path": style["font"], "id": ""},
                        "strokes": [{"content": {"render_type": "solid",
                                                 "solid": {"color": hex_to_rgb(style["stroke"])}},
                                     "width": 0.0253, "mode": 0}],
                        "size": style["size"], "useLetterColor": True,
                        "range": [0, len(content)],
                    }],
                }, ensure_ascii=False),
                "font_path": style["font"], "font_size": float(style["size"]),
                "text_size": 30, "text_color": style["color"], "text_alpha": 1.0,
                "border_color": style["stroke"], "border_alpha": 1.0,
                "border_width": 0.0253, "border_mode": 0,
                "is_rich_text": True, "alignment": 1, "line_spacing": 0.02,
                "letter_spacing": 0.0, "line_max_width": 0.82, "typesetting": 0,
                "line_feed": 1, "global_alpha": 1.0, "layer_weight": 1,
                "has_shadow": False, "check_flag": 15, "font_title": "none",
                "add_type": 0, "sub_type": 0, "recognize_type": 0, "fonts": [],
                "words": {"start_time": [], "end_time": [], "text": []},
            })
            anim = uid()
            materials["material_animations"].append({
                "id": anim, "type": "sticker_animation", "animations": [],
                "multi_language_current": "none",
            })

            seg = segment(mat_id, [anim], None, dur, at,
                          render_index=14000 + len(text_segs),
                          track_render_index=1)
            scale = 1.55 * float(txt.get("size", 1.0))
            seg["clip"]["scale"] = {"x": scale, "y": scale}
            seg["clip"]["transform"] = {"x": 0.0, "y": float(txt.get("y", -0.32))}
            seg["hdr_settings"] = None
            seg["enable_lut"] = False
            seg["enable_adjust"] = False
            text_segs.append(seg)

    total = cursor
    if total == 0:
        raise SystemExit("the plan produced an empty timeline")

    tracks = [
        {"id": uid(), "type": "video", "attribute": 0, "flag": 0,
         "is_default_name": True, "name": "", "segments": video_segs},
        {"id": uid(), "type": "text", "attribute": 0, "flag": 0,
         "is_default_name": True, "name": "", "segments": text_segs},
        {"id": uid(), "type": "audio", "attribute": 0, "flag": 0,
         "is_default_name": True, "name": "", "segments": audio_segs},
    ]

    with open(os.path.join(template, "draft_content.json"), encoding="utf-8") as f:
        content = json.load(f)
    content.update({
        "id": uid(), "new_version": version, "version": 360000,
        "duration": total, "fps": fps, "name": "",
        "canvas_config": {"ratio": "original", "width": canvas["width"],
                          "height": canvas["height"], "background": None},
        "tracks": tracks,
        "materials": {**content.get("materials", {}), **materials},
    })

    out_dir = os.path.join(draft_root, project)
    if os.path.exists(out_dir):
        if not force:
            raise SystemExit(
                f"a project named {project!r} already exists.\n"
                "pick another name, or pass --force to replace it — but check "
                "first that it is not someone's real edit."
            )
        shutil.rmtree(out_dir)
    shutil.copytree(template, out_dir)
    for stale in ("draft_content.json.bak", "template.tmp", "template-2.tmp"):
        p = os.path.join(out_dir, stale)
        if os.path.exists(p):
            os.remove(p)

    with open(os.path.join(out_dir, "draft_content.json"), "w",
              encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False)

    # Without draft_meta_info.json the folder exists but never appears in
    # CapCut's project list.
    with open(os.path.join(template, "draft_meta_info.json"), encoding="utf-8") as f:
        meta = json.load(f)
    now = int(time.time() * US)
    meta.update({
        "draft_id": uid(), "draft_name": project,
        "draft_fold_path": out_dir.replace("\\", "/"),
        "draft_root_path": draft_root.replace("\\", "/"),
        "draft_cover": "draft_cover.jpg",
        "tm_draft_create": now, "tm_draft_modified": now, "tm_duration": total,
        "draft_materials": [], "draft_materials_copied_info": [],
        "draft_segment_extra_info": [],
        "draft_timeline_materials_size_": sum(
            os.path.getsize(m["path"]) for m in cache.values()),
    })
    with open(os.path.join(out_dir, "draft_meta_info.json"), "w",
              encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)

    print(f"project : {out_dir}")
    print(f"schema  : {version}   (template: {os.path.basename(template)})")
    if style["font"]:
        print(f"font    : {style['font']}")
    elif text_segs:
        print("font    : none found — CapCut will fall back to its default, which "
              "may render Thai text poorly. Set text_style.font in the plan.")
    print(f"runtime : {total / US:.2f}s   "
          f"video={len(video_segs)} text={len(text_segs)} voice={len(audio_segs)}")
    print()
    for row in timeline:
        start, dur = row["start"] / US, row["duration"] / US
        print(f"  {start:7.2f}s +{dur:6.2f}s   {row['name']}")

    longest = max(timeline, key=lambda r: r["duration"])
    if longest["duration"] > total * 0.4:
        print(f"\nnote: '{longest['name']}' is {longest['duration'] / US:.1f}s of "
              f"{total / US:.1f}s — worth checking that pacing")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--draft-root", default=DEFAULT_DRAFT_ROOT)
    ap.add_argument("--force", action="store_true",
                    help="replace an existing project of the same name")
    args = ap.parse_args()

    if not os.path.isdir(args.draft_root):
        raise SystemExit(f"CapCut draft folder not found: {args.draft_root}")
    # Only CapCut's own folder is at risk of being overwritten; writing a draft
    # somewhere else (a scratch copy, a test root) is safe while it runs.
    live = os.path.normcase(os.path.abspath(args.draft_root)) == \
        os.path.normcase(os.path.abspath(DEFAULT_DRAFT_ROOT))
    if live and capcut_running():
        raise SystemExit(
            "CapCut is running. It keeps drafts in memory and would overwrite "
            "this one on exit — close it and re-run."
        )

    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)

    build(plan, args.draft_root, args.force)
    print("\nopen CapCut and confirm the project loads — that is the real check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
