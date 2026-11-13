# Review Desk

A skill for Claude Code: a page in your browser where you check what Claude built, item by item,
and hand your answers back, which wakes Claude up to go on.

- **One desk per project**, running in the background on your own computer (127.0.0.1). Claude
  starts it, it opens once in your browser, and every review round it writes appears there by
  itself, in a sidebar.
- **Per item:**
  - a verdict: works, partly, needs a change (cosmetic, annoying, broken), can't test, skipped;
  - a note, and questions and ideas, each in its own box;
  - screenshots you mark up (arrow, box, blur), screen recordings, lines from a log or from a
    command's output, any file;
  - answers save as you type.
- **Hand back to Claude:** a background `review-desk wait` in Claude's session returns with your
  answers. Claude replies in the item's thread, sends fixed items back for another look (your
  earlier answers stay in their history), and marks your ideas as planned, done or not now.
- **Ideas board, question cards, summary:**
  - every idea of every round in one place;
  - Claude's planning questions as cards while the page is open;
  - a short summary to copy.
- **Run buttons** for the commands a checklist names (on this computer only, after your click),
  with live output and Stop. Linked files and the commit open in a viewer.
- **On your phone** if you want: a QR code over your home network with its own secret, closed
  after eight hours. The phone answers and takes photos, but never runs commands.
- **The look:** English and German, light and dark, a desktop notification and a soft chime when
  Claude replied or asked.

Rounds live in the project's `.review/` folder, kept out of git through `.git/info/exclude`.
Nothing leaves your computer; the page loads nothing from the internet. Python 3.10 or newer, no
packages.

## Install

```bash
python3 tools/install.py
```

This links this folder as the skill (`~/.claude/skills/review-desk`) and puts a `review-desk`
command in `~/.local/bin`. With `--hook`, it also adds a small session-start hook to
`~/.claude/settings.json`: a new session then hears about answers that wait (it prints nothing
otherwise). `--remove` takes it all out again. Check it with:

```bash
review-desk selftest
```

## Use

Ask Claude for a manual check, or type `/review-desk`. Claude writes the round, starts the desk and
listens. You answer on the page and click **Hand back to Claude**. `SKILL.md` is what Claude reads;
`references/` has the checklist format, the commands and the question cards.

## Develop

```bash
python3 -m unittest discover -s tests
```

The page is plain HTML, CSS and JavaScript in `assets/page/` (no build step), the desk is Python
in `scripts/desk/`. IBM Plex fonts are included under the SIL Open Font License
(`assets/fonts/OFL.txt`).
