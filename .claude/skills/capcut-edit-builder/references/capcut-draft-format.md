# CapCut desktop draft format

Notes taken from CapCut 9.2.0 on Windows (draft `new_version` 181.0.0). Read this
when a generated draft fails to open, when CapCut changes its schema after an
update, or when adding a track type `build_draft.py` does not yet produce.

## Contents

- [Where drafts live](#where-drafts-live)
- [Is the draft readable?](#is-the-draft-readable)
- [Files in a draft folder](#files-in-a-draft-folder)
- [draft_content.json](#draft_contentjson)
- [Segments](#segments)
- [Materials](#materials)
- [Text](#text)
- [draft_meta_info.json](#draft_meta_infojson)
- [Things that will bite](#things-that-will-bite)

## Where drafts live

```
%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\<project name>\
```

The folder name is the project name shown in CapCut's launcher. Sibling folders
`com.lveditor.cloud.draft_*` hold cloud projects — leave those alone.

Installed versions are listed under `%LOCALAPPDATA%\CapCut\Apps\`, newest last.

## Is the draft readable?

Everything here depends on `draft_content.json` being plain JSON. Check before
assuming:

```bash
python -c "import json;json.load(open(r'<path>/draft_content.json',encoding='utf-8'));print('plain JSON')"
```

If a future CapCut build encrypts or binary-packs drafts, this fails and the
whole approach is off the table — say so plainly rather than producing a project
that cannot open.

## Files in a draft folder

Only two need writing:

| File | Role |
|---|---|
| `draft_content.json` | the timeline: tracks, segments, materials |
| `draft_meta_info.json` | the launcher entry — **without it the project is invisible** |

The rest (`draft_settings`, `attachment_editing.json`, `attachment_pc_common.json`,
`draft_agency_config.json`, `performance_opt_info.json`, `draft_cover.jpg`, and
the empty `Resources/`, `matting/`, `subdraft/` … directories) are copied
wholesale from an existing draft. CapCut regenerates most of them, but starting
from real ones avoids guessing at formats that carry no useful information.

Delete `draft_content.json.bak`, `template.tmp` and `template-2.tmp` from the
copy — they are stale snapshots of the template's timeline, not of the new one.

## draft_content.json

Top level, with only the fields that matter:

```json
{
  "id": "UUID",
  "new_version": "181.0.0",
  "version": 360000,
  "duration": 74960000,
  "fps": 30.0,
  "canvas_config": {"ratio": "original", "width": 1080, "height": 1920,
                    "background": null},
  "tracks": [ ... ],
  "materials": { "videos": [], "audios": [], "texts": [], ... }
}
```

**Every time value is in microseconds.** `duration` must equal the end of the
last segment or the timeline renders short.

A track:

```json
{"id": "UUID", "type": "video", "attribute": 0, "flag": 0,
 "is_default_name": true, "name": "", "segments": [ ... ]}
```

Types seen in the wild: `video`, `audio`, `text`, `sticker`. Track order in the
array is bottom-to-top on screen, so the video track goes first and text after it.

## Segments

A segment places one material on a track:

```json
{
  "id": "UUID",
  "material_id": "UUID of the entry in materials.videos / .audios / .texts",
  "extra_material_refs": ["UUID", "..."],
  "source_timerange": {"start": 0, "duration": 2440000},
  "target_timerange": {"start": 0, "duration": 2440000},
  "volume": 1.0,
  "render_index": 0,
  "track_render_index": 0,
  "clip": {"scale": {...}, "transform": {...}, "rotation": 0.0, "alpha": 1.0}
}
```

- `source_timerange` is the in-point **inside the source file** — this is where
  trimming happens. `null` for text.
- `target_timerange` is where it sits **on the timeline**.
- To trim to 59s–69s: `source_timerange.start = 59_000_000`, `duration = 10_000_000`.
- `volume: 0.0` mutes a clip, which is what you want under a voiceover.
- `render_index` increments per segment; text conventionally starts around 14000.

CapCut is strict about missing keys — a segment lacking `responsive_layout` or
`hdr_settings` can make the draft unopenable. `build_draft.py`'s `segment()`
carries the full set; extend that rather than writing a leaner dict.

## Materials

`materials` is an object of parallel arrays. Present-but-empty arrays are fine;
missing ones are not, so build the whole set.

**Every video segment** needs `extra_material_refs` with exactly one id from
each of:

`speeds`, `placeholder_infos`, `canvases`, `sound_channel_mappings`,
`material_colors`, `vocal_separations`

**Audio segments** use: `speeds`, `placeholder_infos`, `beats`,
`sound_channel_mappings`, `vocal_separations` — `beats` in place of the visual
tables.

These entries are per-segment, never shared. Reusing one id across two segments
produces a draft that opens but behaves strangely.

A video material:

```json
{"id": "UUID", "type": "video", "path": "D:/ClinicVideo/job/C1004.MP4",
 "material_name": "C1004.MP4", "duration": 6720000,
 "width": 1080, "height": 1920, "has_audio": true,
 "crop": {"upper_left_x": 0.0, ...}, "crop_ratio": "free", "crop_scale": 1.0}
```

- `type` is `"photo"` for stills, `"video"` otherwise.
- Paths use **forward slashes**, absolute.
- Stills use the sentinel duration `10800000000`; their on-screen length comes
  from `target_timerange` instead.
- **`width`/`height` are display dimensions.** Camera files are often stored
  1920×1080 with a rotation-90 side-data flag and display as 1080×1920 — record
  the rotated values or every clip appears sideways.

Audio materials use `type: "extract_music"` when pulling sound off a video file.

## Text

The text material carries the styling twice: once as a JSON string in `content`
(what CapCut renders) and once as flat sibling fields (what its UI reads). Both
must agree or the editing panel shows something different from the canvas.

```json
{
  "id": "UUID", "type": "text",
  "content": "{\"text\":\"ฉีดปากแค่ 1 CC\",\"styles\":[{...}]}",
  "font_path": "C:/Users/.../DB Heavent Blk Cond v3.2.1.ttf",
  "text_color": "#0044c6", "border_color": "#ffffff",
  "font_size": 15.0, "alignment": 1, "is_rich_text": true
}
```

Inside `content`, `styles[].range` is `[0, len(text)]` in characters, colours are
`[r, g, b]` floats 0–1, and `font.path` repeats `font_path`.

Text segments need one `material_animations` entry in `extra_material_refs`
(`type: "sticker_animation"`, empty `animations`), `source_timerange: null`, and
`hdr_settings: null`.

Position and size live on the segment's `clip`: `transform.y` runs −0.5 (top) to
0.5 (bottom), `scale` around 1.55 for a normal caption.

To match an existing look, read `materials.texts[0]` from a recent draft and copy
`font_path`, `text_color`, `border_color` — this is what `detect_house_style()`
does.

## draft_meta_info.json

Copy the template's and override:

```json
{"draft_id": "UUID", "draft_name": "lip-filler-review",
 "draft_fold_path": "C:/Users/.../com.lveditor.draft/lip-filler-review",
 "draft_root_path": "C:/Users/.../com.lveditor.draft",
 "draft_cover": "draft_cover.jpg",
 "tm_draft_create": 1787020093306555,
 "tm_draft_modified": 1787020093306555,
 "tm_duration": 74960000,
 "draft_materials": [], "draft_segment_extra_info": [],
 "draft_timeline_materials_size_": 1610612736}
```

`tm_*` timestamps are microseconds since epoch. Clear `draft_materials` and
`draft_segment_extra_info` — carrying the template's over points at media the
new project does not use.

## Things that will bite

**CapCut must be closed.** It holds open drafts in memory and rewrites them on
exit, silently discarding anything written underneath it.

**Never write into an existing project folder.** Client edits represent hours of
work and there is no undo here. New folder, distinct name.

**Verify media before building, not after.** `ffprobe` on every file catches the
trim point past the end of a clip and the download that returned an HTML error
page instead of an MP4. A draft referencing a missing or truncated file opens
with silent gaps.

**Validating the JSON is not proof it opens.** Structural checks catch typos, not
schema drift after a CapCut update. Opening the project is the real test and it
belongs to the person at the keyboard — say so instead of implying it is verified.
