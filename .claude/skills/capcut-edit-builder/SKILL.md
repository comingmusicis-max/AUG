---
name: capcut-edit-builder
description: Turn a video editing brief — numbered scenes, Dropbox or direct media links, on-screen text, and trim points — into downloaded footage plus a ready-to-open CapCut project with the timeline already laid out, and add karaoke subtitles that highlight each syllable as it is spoken. Use this whenever someone pastes a shot list or edit brief with scene numbers and media links, asks to download footage and set up a CapCut project, wants clips arranged in order on a timeline, wants word- or syllable-highlighted subtitles (the spoken word changing colour or size), or is building a clinic/beauty review edit (before-after, filler, botox, treatment results) — even when they never say the word "CapCut". Also use when re-cutting or rebuilding an edit from a brief that was handled before.
---

# CapCut Edit Builder

Clients send an edit brief: numbered scenes, a Dropbox link per shot, the text
that goes on screen, and sometimes "use seconds 0:59–1:09". Doing this by hand
means downloading fifteen files, hunting for each one in the CapCut media panel,
dragging them into the right order, and retyping every caption.

CapCut has no API — but its desktop drafts are plain JSON folders on disk, so a
timeline can be written directly. That turns an hour of dragging into a project
that opens with everything already in place, leaving the human free to do the
part that actually needs judgement: retouching, blurring, pacing, music.

## The split that makes this work

Reading a brief is interpretation — which clip belongs to which scene, what the
client meant by "0.59-1.09", which text goes where. Writing valid CapCut JSON is
exacting and unforgiving. Keep those apart:

**You** read the brief and write an **edit plan** (JSON).
**`scripts/build_draft.py`** turns that plan into a CapCut project.

If the draft comes out wrong, the fix is almost always in the plan, not the script.

## Workflow

### 1. Read the brief and restate it

Before downloading a gigabyte of footage, write out what you understood: scene
order, which file goes where, trim points, and the text for each scene. Briefs
are frequently ambiguous, and a 30-second check beats rebuilding the edit.

Watch for these, they come up constantly:

- **`0.59-1.09` means 59s to 1m09s**, not 0.59 seconds. Thai briefs write
  timecodes with a dot. When a value could be either, say which you assumed.
- **A "Voice" link is used for its audio only** — the video half is discarded.
  These are often horizontal clips while the edit is vertical; that is fine and
  worth *not* flagging as a problem.
- **The same still can appear in several scenes** (a before-photo in both the
  opener and the comparison). Download once, reference it as many times as needed.
- **A scene with both footage and a separate voice track** almost always wants
  the footage muted, since the voiceover is replacing its audio. Do that, and say
  so, so it can be undone with one click.

### 2. Download and verify

Write the download list as JSON and run the fetcher:

```bash
python scripts/fetch_media.py plan/media.json
```

```json
{
  "dest": "D:/ClinicVideo/<job-name>",
  "files": [
    {"name": "C1004.MP4", "url": "https://www.dropbox.com/scl/fi/..."},
    {"name": "DSC05998.JPG", "url": "https://www.dropbox.com/scl/fi/..."}
  ]
}
```

Default destination is `D:\ClinicVideo\<job-name>\`. Dropbox `dl=0` links are
rewritten to direct downloads automatically, and files already present are
skipped, so a re-run after a failure is cheap.

The fetcher probes every file with ffprobe and writes `media_report.json`
(duration, dimensions, rotation, audio). **Read it before building.** It is how
you catch a trim point that runs past the end of a clip — better to find that now
than to hand over a project with a blank gap in it.

### 3. Match the colour across the job

One shoot still drifts — the treatment room is warmer than the counter, auto
exposure rides up when a face fills the frame, the stills come off a different
body than the clips. Cut together, every scene change reads as a colour change,
and clinic clients notice it immediately because the same face changes shade.

```bash
python scripts/match_grade.py D:/ClinicVideo/<job-name> --preview
python scripts/match_grade.py D:/ClinicVideo/<job-name> --write
```

The first run only measures: it prints each file's luma and Cb/Cr average, picks
one common white and one common brightness, and writes `grade_report.json` plus
before/after stills in `grade_preview/`. The second run renders corrected copies
into `graded/`, which is what the edit plan's `media_dir` should point at.

**Look at the report before rendering.** The measurement is grey-world, so a clip
holding a red logo or a green scrub top reads as a colour cast that is not there;
the script flags any file it is moving more than 6 points. When one clip already
looks right, `--ref C2451.MP4` pins the whole job to it, which beats the median.

`SOFT` at the top of the script holds the look itself — target brightness, how
warm the white sits, how far the blacks lift. The defaults aim at the soft creamy
white beauty briefs ask for; that is taste, so tune and re-run `--preview`.

### 4. Write the edit plan

Save as `plan/edit_plan.json`:

```json
{
  "project": "lip-filler-review",
  "media_dir": "D:/ClinicVideo/lip-filler-2026-08-19",
  "canvas": {"width": 1080, "height": 1920},
  "fps": 30,
  "scenes": [
    {
      "name": "ก่อนฉีด",
      "clips": [{"file": "DSC05998.JPG", "still": 2.0}],
      "text":  [{"content": "3 2 1"}]
    },
    {
      "name": "ปรึกษาคุณหมอ",
      "clips": [{"file": "C2477.MP4", "in": 59, "out": 69, "mute": true}],
      "voice": [{"file": "C1012.MP4", "in": 0, "out": 5},
                {"file": "C1011.MP4", "in": 0, "out": 2}],
      "text":  [{"content": "อยากได้ปากทรงสวย เป็นธรรมชาติ"}]
    }
  ]
}
```

Field reference — everything optional except `file`:

| Where | Field | Meaning |
|---|---|---|
| `clips` | `in` / `out` | trim points in seconds; omit for the whole clip |
| | `still` | hold time for a photo, in seconds |
| | `mute` | silence this clip's own audio |
| `voice` | `in` / `out` | trim points |
| | `at` | start, in seconds from scene start; defaults to running back-to-back |
| `text` | `at` / `dur` | timing within the scene; defaults to spanning the whole scene |
| | `y` | vertical position, −0.5 top to 0.5 bottom; default −0.32 |
| | `size` | relative scale; default 1.0, use ~0.65 for disclaimers |

To hold a still for exactly as long as its voiceover runs, write any placeholder
`still` and let the fitter do the arithmetic once the voiceover has been probed:

```bash
python scripts/fit_stills.py plan/edit_plan.json          # shows the change
python scripts/fit_stills.py plan/edit_plan.json --write  # saves it
```

It divides the voice track evenly across a scene's stills, and only touches
scenes that are all stills and carry a voice — a scene with footage in it sets
its own length and is left alone. Re-run it after any re-cut of the voiceover;
it is idempotent.

### 5. Build

```bash
python scripts/build_draft.py plan/edit_plan.json
```

The script refuses to run while CapCut is open — CapCut holds drafts in memory
and would overwrite the generated one on exit. It also refuses to overwrite an
existing project unless `--force` is passed, because a client's real edit living
under a similar name is not worth the risk.

It prints a scene-by-scene timeline. Check the total runtime against the platform
the client is posting to; anything past ~60s for TikTok or Reels is worth
mentioning, especially when one scene is eating half the video.

**The build says it wrote the project but CapCut's list is empty.** The two
causes look identical from the terminal, so check rather than guess:

```bash
python scripts/doctor.py --expect <project-name>
```

It lists every draft root on the machine and says which one the project is
actually in. If it is on disk and still not listed, CapCut is holding a stale
list — quit it completely and reopen, since it reads the folder at startup.
If it is nowhere, the build wrote to a root this CapCut does not read; pass the
one `doctor.py` names via `--draft-root`. CapCut has moved this folder between
versions and lets the user relocate it in Settings, so the hardcoded default is
a starting guess, not a fact.

### 6. Hand it over

Write `SCRIPT.md` into the media folder — timeline table plus, importantly, a
checklist of what still needs doing by hand. **Say plainly that opening CapCut is
the real test.** The JSON validating is not proof the project opens; that check
belongs to the person at the keyboard, and claiming otherwise is how trust gets
lost.

## Karaoke subtitles

The effect: the line sits on screen in grey and the syllable being spoken right
now is pink and a step larger — "โปร" lights up, drops back, then "แกรม" takes
over. CapCut renders it from one text material carrying several style ranges, so
each syllable is a short segment showing the same line with a different range
highlighted.

### Working on a project someone has been editing

Almost always the case, and it changes everything. Read the current draft first
— editors trim clips, split tracks and add their own text, so the timeline is no
longer the one that was generated:

```bash
python scripts/read_timeline.py <project> --clips plan/clips.json
```

Nothing here edits a source project; every script writes a new draft folder. A
client's edit is hours of work with no undo.

Before choosing colours, look for subtitles they made by hand. One styled line
says exactly what they want, and matching it beats any default — and beats
reading colours off a screenshot they sent, which is never quite the same hex:

```bash
python scripts/read_timeline.py <project> --styles
```

That prints the fill, stroke, size and font behind every text material in the
draft, and breaks out the ranges wherever a line carries more than one colour —
which is exactly the idle/active pair a highlight needs.

`STYLE` at the top of `make_karaoke.py` holds the defaults, but they are one
client's look. Put a job's own colours in `plan/karaoke_style.json` and pass
`--style` instead of editing the script, so a new client's palette does not
follow every other job in the repo. An unknown key is refused rather than
ignored, since a typo would otherwise show up as "the colours did not change".

### Getting the timings

The highlighting is mechanical; where the timings come from is the real choice.

**From a text track that already exists** — the shortest path. CapCut's own
auto-captions produce a timed Thai track; converting it needs no model download
and no correction pass:

```bash
python scripts/make_karaoke.py <source> <new> --from-track 4
```

**From Whisper** — when there is no caption track to work from:

```bash
python scripts/transcribe_audio.py plan/clips.json plan/transcript.json
python scripts/prepare_subtitles.py plan/transcript.json plan/syllables.json --fixes plan/fixes.json
python scripts/make_karaoke.py <source> <new> --words plan/syllables.json
```

Read `plan/transcript.json` before building. Whisper's Thai is good on ordinary
speech and unreliable on exactly the words a client checks first — their clinic
name, product names, prices. Put those in `fixes.json` using the brief's own
wording:

```json
{"replace": {"โปรแกม": "โปรแกรม", "โซฟไซคินิก": "โซลไซด์คลินิก"},
 "voiceover": ["C1182.MP4"]}
```

Correct only what the brief supports. Guessing at a half-heard word puts a
sentence on screen that nobody said.

`prepare_subtitles.py` also drops clip audio that a voiceover talks over —
without it two speakers get subtitled at the same instant.

Thai syllable splitting needs `pip install pythainlp python-crfsuite`. Without it
the scripts degrade to whole-word highlighting rather than failing — and with
`--from-track`, where each caption arrives as a single "word", that degrades all
the way to one highlight per line, which is not the effect at all. If the run
reports about as many syllable segments as it does lines, that is the missing
package, not the timings.

### Two Whisper details that cost hours to rediscover

`segment.text` is properly decoded Thai; the per-word entries are sub-word tokens
that lose tone marks alone — หน้าแห้ง arrives as ห, น, ้, า. Build lines from the
sentences and take timing from the tokens. `transcribe_audio.py` saves both.

`RuntimeError: Invalid string length in model.bin` means the download is corrupt,
not that the code is wrong. Check its SHA256 against
`https://huggingface.co/api/models/<repo>/tree/main` — a file with the right byte
count and the wrong hash is the signature of failing RAM, and that machine is
silently corrupting the editor's exports too. Say so.

## What this cannot do, and must be said out loud

The generated project is a timeline, not a finished edit. These are craft work
and no script produces them — list them explicitly rather than letting the client
discover the gap:

- **Blurring** needles, faces, brand names — near-universal in injection footage
- **Retouching** — briefs routinely ask for the after-photo to read as clearly
  better than the before; that is a human call
- **Cropping stills** — a brief saying "zoom on the lips" still arrives as a
  42-megapixel full-frame photo that nobody has cropped
- Music, transitions, pacing, and fine text placement

Under-promising here is the whole game. A client told up front that the needle
blur is theirs to do will handle it; one who finds out after posting will not.

## Working notes

- **Never touch existing drafts.** Always a new project folder with a name that
  cannot collide with the client's own work.
- Match the house text style. Read an existing draft's `materials.texts[0]` for
  the font path, colour, and stroke already in use rather than picking new ones —
  a caption in the wrong font is instantly visible.
- Camera footage is often stored 1920×1080 with a rotation flag, displaying as
  vertical. The script handles this; do not "fix" the canvas because ffprobe
  reported landscape.
- Reply in the language of the brief. These briefs arrive in Thai, and so should
  `SCRIPT.md`.

`references/capcut-draft-format.md` documents the on-disk format — read it when
the draft fails to open, when CapCut updates its schema, or when adding a track
type the script does not yet build.
