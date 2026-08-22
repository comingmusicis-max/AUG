---
name: davinci-color
description: Grade a DaVinci Resolve timeline by script instead of by hand — write a look as numbers in a JSON file, build it into a .cube LUT, and apply it to matching clips through Resolve's Python API, so the same grade lands identically on every clip and every re-cut. Use when someone wants to colour grade, dye, tint, or colour-match footage in DaVinci Resolve, wants a LUT built to a spec, wants before/after shots held to the same colour, wants a whole timeline graded in one pass, or asks what can be automated on Resolve's colour page. Also use to inspect a Resolve project's structure or diagnose why Resolve scripting will not connect.
---

# DaVinci Colour by Script

Colour wheels cannot be written down. That is fine for one film and useless for
a clinic that shoots the same treatment every month: the look drifts, the
before-shot and the after-shot end up half a degree apart, and nobody can say
what last month's grade actually was.

Driving Resolve from Python turns a look into a number. The number is in a file,
the file is in git, and re-running it after a re-cut restores exactly what was
there before.

## What the API allows, and what it does not

**It cannot build a node graph.** No adding nodes, no colour wheels, no curves.
Read `references/resolve-color-api.md` before promising anything — the gap
between what the colour page does and what a script can reach is the single
thing most worth knowing here.

What works: load a `.cube` into a node that already exists, set that node's CDL
numbers, copy a whole graph from one clip onto others. That is enough for a look
plus per-clip trims plus before/after matching, which is most clinic work.

## The split

**You** decide the look and write it as numbers.
**`make_lut.py`** turns those numbers into a `.cube`.
**`apply_grade.py`** puts it on every clip a rule matches.

If a grade lands wrong, the fix is almost always in the JSON, not the scripts.

## Workflow

### 1. Check the machine can connect

```bash
python scripts/doctor.py
```

Scripting fails for four unrelated reasons that look identical from outside — no
module, wrong path, external scripting switched off, or the free version
refusing outside connections. The doctor separates them and prints the one fix
that applies. Run it before anything else; it changes nothing.

**The free version of Resolve only scripts from inside the app**
(`Workspace > Console`, set to Py3, paste the file in). External scripting is a
Studio feature. Every script here handles both.

### 2. Read the actual project

```bash
python scripts/inspect_project.py --project JJ --out jj_project.json
```

Writes clip names, track layout, node counts, existing LUTs and — importantly —
the colour management mode. Never write a look against remembered clip names;
the timeline gets re-cut and the names move.

Check `colorScienceMode` in the output. Under RCM the timeline is not in
Rec.709 and a Rec.709 LUT will look wrong in a normal node.

### 3. Write the look

A look file is plain numbers (`looks/clinic_clean.json` is the starting point):

```json
{
  "name": "clinic_clean",
  "temp": -3, "tint": 1,
  "exposure": 0.1,
  "contrast": 1.06, "pivot": 0.435,
  "saturation": 1.04,
  "skin_protect": 0.8,
  "lift": [0.0, 0.0, 0.004],
  "gamma": [1.0, 1.0, 1.0],
  "gain": [1.0, 1.0, 0.995]
}
```

`skin_protect` is the one worth explaining: raising saturation on a clinic shot
turns faces orange long before the room looks better. At `0.8`, skin hues keep
almost their original saturation while everything else moves.

Three presets ship here:

| look | for |
|---|---|
| `clinic_clean` | before/after and anything showing a result. Neutral on purpose |
| `clinic_warm` | talking-head and B-roll, where flattering is the job |
| `premium_grey` | openers and logo cards. Too flat for skin |
| `golden_hour` | backlit sunset: cream sky, warm bloom, haze in the blacks |

Build it:

```bash
python scripts/make_lut.py looks/clinic_clean.json --install
```

`--install` writes into Resolve's LUT folder (needs an Administrator terminal on
Windows). Without it the `.cube` lands next to the look file, and
`apply_grade.py` takes the absolute path just as happily.

### 4. Build the node graph

The API cannot add nodes — no `AddNode`, in any version. It can fill in nodes
that already exist, and `CopyGrades` carries a whole graph onto other clips,
**node structure included**. So the graph is built by hand exactly once:

1. On the Color page, pick one clip as the reference.
2. Press `Alt+S` until it has as many nodes as the graph needs.
3. Run the script. It loads the LUT, sets every CDL, labels every node, bypasses
   the ones meant to stay empty, then copies the finished graph to the rest.

`looks/golden_hour_nodes.json` is a working six-node graph:

| node | does | who sets it |
|---|---|---|
| `01 BALANCE` | neutral handle for pulling a drifted clip back | human, per clip |
| `02 EXPOSURE` | level correction before the look | script |
| `03 LOOK` | the `.cube` — the whole look lives here | script |
| `04 SKIN` | takes back a little of the saturation the LUT added | script |
| `05 SKY` | **empty and bypassed on purpose** | human, needs a window |
| `06 TRIM` | last word before output, shot-to-shot matching | human |

Node 5 is the honest part: windows, qualifiers and curves cannot be scripted at
all. Leaving a labelled, disabled node in the right place in the chain means the
human has somewhere obvious to work instead of inserting a node into a graph
they did not build.

Once the graph is right, save it — a graph that exists only inside a project is
one accidental delete away from gone, and cannot be reused next month:

```bash
python scripts/export_grade.py --project jj --clip 1 --out D:/grades
```

That writes a `.drx`, which `ApplyGradeFromDRX` pushes onto clips with no manual
step at all — nodes included. The next job skips step 2 entirely:

```json
{"select": {"all": true}, "drx": "D:/grades/golden_hour.drx", "drx_mode": 0}
```

**`match` refuses to copy over clips that already carry a graph**, because
`CopyGrades` replaces the target outright and somebody's hand-built nodes are
worth more than this script's convenience. Narrow the targets, or pass `--force`
when replacing really is the intent — after exporting what is there.

### 5. Say which clips get what

`looks/grade.example.json` is the shape. Rules combine with AND:

```json
{
  "grades": [
    {"select": {"all": true}, "lut": "clinic_clean.cube", "lut_node": 1, "mark": "Orange"},
    {"select": {"tracks": [1], "name_contains": "DSC"},
     "cdl": {"node": 1, "slope": [1.02, 1.02, 1.02], "offset": [0.004, 0.004, 0.004],
             "power": [1, 1, 1], "saturation": 1.0}}
  ],
  "match": [{"source": {"names": ["BEFORE.JPG"]}, "targets": {"names": ["AFTER.JPG"]}}]
}
```

Selectors: `all`, `tracks`, `names`, `name_contains`, `indexes`, `range`.

Three phases run in order, and the order is the point: **`grades`, then `match`,
then `trims`.** A copied graph overwrites whatever was on the target clip, so
per-clip corrections belong in `trims` — put them in `grades` and the copy wipes
them.

`match` is the before/after tool: it copies one clip's entire graph onto the
others, so the pair cannot drift apart. **Use it on every before/after pair.**
Two shots graded separately, however carefully, differ — and the difference
reads to a viewer as a result the treatment did not produce. That is the one
correctness rule in clinic colour work.

`mark` sets the timeline clip colour, so it is visible at a glance which clips
the script owns and which a human still has to grade.

### 6. Dry run, then apply

```bash
python scripts/apply_grade.py grade.json --project JJ --dry-run
python scripts/apply_grade.py grade.json --project JJ
```

`--list` prints the timeline's clips and node counts without touching anything.

It all lands in Resolve's undo stack — Ctrl+Z on the Color page steps a scripted
grade back — but on a long timeline the dry run is still cheaper than the undo.

## When a grade will not apply

- **`SetLUT failed`** — Resolve cannot find the `.cube`. Bare filenames resolve
  against its LUT folder only; use `make_lut.py --install`, or pass an absolute path.
- **"has N nodes, but the grade wants node 3"** — the API cannot add nodes. Build
  the graph once on the Color page, or apply a PowerGrade that has it, then re-run.
- **The look is right but everything is wrong on screen** — check colour
  management (step 2). A Rec.709 LUT inside an RCM timeline is the usual cause.
- **"target clip(s) already carry a node graph"** — the guard above. Export them
  first with `export_grade.py`, then `--force` if the replacement is wanted.
- **An OFX node will not budge** — Chromatic Adaptation, Face Refinement and the
  rest take no parameters from the API at any node index. They stay manual.
