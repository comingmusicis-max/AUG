# What the Resolve scripting API can actually do to colour

Written down because the API docs list the methods but not the wall you hit
about ten minutes in.

## The wall

**You cannot build a node graph from a script.** There is no AddNode, no
SetPrimaryWheel, no way to touch a curve. The colour page's whole interface is
absent from the API.

What exists is narrow but enough:

| Method | On | Does |
|---|---|---|
| `SetLUT(nodeIndex, path)` | TimelineItem | loads a `.cube` into an **existing** node |
| `GetLUT(nodeIndex)` | TimelineItem | reads back what is loaded there |
| `SetCDL(dict)` | TimelineItem | slope / offset / power / saturation on one node |
| `CopyGrades([items])` | TimelineItem | copies this clip's whole graph onto others |
| `GetNumNodes()` | TimelineItem | how many nodes the clip has (newer versions only) |
| `SetClipColor(name)` | TimelineItem | the timeline swatch — useful as a "done" marker |
| `RefreshLUTList()` | Project | after writing a new `.cube`, or `SetLUT` won't find it |
| `GrabStill()` | Timeline | current frame into the gallery |
| `ExportStills(...)` | GalleryStillAlbum | stills out to disk, for before/after checks |

So the working method is: **shape the look as a file, drive the file from
Python.** A `.cube` for the look, CDL numbers for per-clip trims, `CopyGrades`
to hold two shots identical. Anything needing a real node graph gets built once
by hand and saved as a PowerGrade.

`SetCDL` wants strings, not numbers:

```python
item.SetCDL({"NodeIndex": "1", "Slope": "1.05 1.0 0.98",
             "Offset": "0.0 0.0 0.004", "Power": "1.0 1.0 1.0",
             "Saturation": "1.1"})
```

## Getting connected

The module ships with Resolve; nothing is installed from pip.

| | path |
|---|---|
| Windows API | `%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting` |
| Windows lib | `C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll` |
| macOS API | `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting` |
| Linux API | `/opt/resolve/Developer/Scripting` |

```python
import DaVinciResolveScript as dvr
resolve = dvr.scriptapp("Resolve")
```

Three things gate it, and all three fail the same way — `scriptapp` returns
`None`:

1. **Resolve must be running**, with a project open.
2. **Preferences > System > General > External scripting using: Local.**
   Default is `None`. Needs a restart.
3. **External scripting is a Studio feature.** The free version runs scripts
   only from `Workspace > Console` (switch it to Py3 and paste). Every script
   here detects the injected `resolve` object, so pasting works.

## Colour management changes what a LUT means

Check `project.GetSetting("colorScienceMode")` before writing a look:

- **`davinciYRGB`** — clips arrive display-referred. A Rec.709 LUT like the ones
  `make_lut.py` builds is correct.
- **`davinciYRGBColorManagedv2`** (RCM) — the timeline is in DaVinci Wide Gamut
  or similar. A Rec.709 LUT dropped in a node will look wrong; it belongs after
  the output transform, or the look needs rebuilding for that space.

`inspect_project.py` reports this, which is why it is worth running first.

## Frames, not seconds

`GetStart()`, `GetEnd()`, `GetDuration()` are all frames at the timeline rate.
Divide by `project.GetSetting("timelineFrameRate")` for seconds.

## Undo

Everything above lands in Resolve's normal undo stack. Ctrl+Z on the Color page
steps back a scripted grade, one clip at a time — so a wrong run is annoying,
not destructive. Still worth a `--dry-run` first on a long timeline.
