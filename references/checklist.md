# The checklist format

A round is `.review/<round>/checklist.md`: plain Markdown with a few conventions. The page reads it
again every time you save it.

````markdown
---
commit: f97c764
log: ~/.local/state/lightgrove/log.txt, target/debug.log
---
# M6a: video with sound (about 15 minutes)

Start the editor from the project folder:

```bash
./target/release/lightgrove
```

Use the projector (DP-3) and headphones.

## 1. Transport

- [ ] Play and pause a video from the Inspector. {#pause}
      Setup: a project with one video on a surface
      Do: press Space, then Space again
      Expected: it stops on the frame it was on and plays on from there, without a jump.
- [ ] The scrub bar follows the video. Before: ![the bar](files/bar-before.png)
      Where: Inspector → Playback, see [the transport code](crates/media/src/transport.rs:120)
- [ ] Speed and direction
  - [ ] 2× speed: twice as fast, and the sound keeps its pitch.
  - [ ] Ping-pong turns at both ends without a jump.

## 2. Undo

- [ ] Ctrl+Z after a change of speed: the video keeps playing (it doesn't restart).
- [x] Saving and opening the project keeps the playback settings.
````

## The parts

- **Header** (optional), between `---` lines at the very top:
  - `title:` overrides the title from the `#` line;
  - `about:` the time it takes;
  - `commit:` a commit hash the page can show with its diff;
  - `log:` log files, comma-separated, absolute, `~/…`, or relative to the project. The user picks
    lines from them to attach.
- **Title:** `# Title (about 15 minutes)`. The part in brackets is the time; "about" or "etwa" in
  it is left out, since the page says it in its own language.
- **Intro:** anything before the first `##`: paragraphs, bullets, code blocks.
- **Sections:** `## 1. Name`. Items are numbered by section: 1.1, 1.2, 1.2.1 (nested).
- **Items:** `- [ ] text`, continued on the lines indented under it.
  - `{#name}` at the end of the first line gives the item a stable name (letters, digits, `.`, `_`,
    `-`). Without it the item's number is its name. Answers stay with their item when you reword
    or renumber it, but a name is surest.
  - `- [x]` starts the item as "works" (something you already know works and only mention).
  - Fields, each on a line of its own, indented under the item: `Setup:`, `Do:`, `Expected:`
    (highlighted), `Where:`. A field goes on over the next lines until another field starts.
  - Anything else indented under an item (paragraphs, bullets, code) shows inside it; items
    indented under an item are its sub-items, each answered on its own.
- **Inline:** `**bold**`, `*italic*`, `` `code` ``, links:
  - `[text](https://…)` opens a web page;
  - `[text](path/in/project.rs:120)` (or `#L120`) opens the file in the page's viewer on that line;
  - `![what](files/name.png)` shows a picture from the round's `files/` folder (click to enlarge).
    Pictures side by side in one line make a before/after.
    A video (`.mp4`, `.webm`, `.mov`) the same way gets a player.
- **Code blocks:** fenced with a language. `bash`, `sh`, `shell` and `console` blocks get a **Run**
  button (the page's own computer only, never the phone); all get **Copy**. A block indented under
  an item belongs to it: lines the user attaches from its output go to that item.

## What the user can answer

Per item: a verdict (works, partly, needs a change, can't test, skipped), how bad a change is
(cosmetic, annoying, broken), a note, questions and ideas (each its own message), replies to yours,
and attachments: screenshots (marked up with arrows, boxes and blur), screen recordings, lines from
the log or from a Run, any file. The round also has an "Anything else?" note and thread.

## What you get back

`review-desk wait` prints `answers.md` for each round handed back:

```markdown
# M6a: video with sound: answers

Round 1 · handed back 2026-11-13 13:17 · 4 work · 1 partly · 1 need a change (1 broken) · …

## 1. Transport

- **Needs change (broken)** · 1.1 {#pause} · Play and pause a video from the Inspector.
  > It jumps back about 3 frames on every pause.
  - Screenshot: [pause-screenshot.png](files/pause-screenshot.png) the frame counter
  - You, idea m3k2 [new]: Seek to the exact frame instead of the keyframe.
- **Not tried** · 1.2 · The scrub bar follows the video.
```

Message ids (`m3k2`, `c1`) are what `reply --to` and `idea` take.
