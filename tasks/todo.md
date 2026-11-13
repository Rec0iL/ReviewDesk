# Review Desk: tasks

Plan: `~/.claude/plans/review-desk.md` (approved 2026-11-13). One commit per phase.

- [x] 1. Desk and page: repo, the command (`start`/`stop`/`status`/`open`), the stable port,
      `.review/` and the git exclude; the parser, live updates; the sidebar with rounds and
      progress, items with verdict and note, saving as you type; English and German, Grove with
      the accent, "pick up where you left"
- [x] 2. The conversation: Send to Claude, `wait`, `answers.md`, `status --hook`; questions and
      ideas on items, severity; threads (`reply`), re-test rounds with history (`retest`);
      notifications and the chime, "where you are"
- [x] 3. Attachments and actions: screenshots with the markup editor, screen recordings, log lines,
      any file; Run buttons with live output and Stop; links to files and the commit, Claude's
      pictures in items
- [x] 4. Ideas board, question cards (`ask`), summary to copy
- [ ] 5. Phone: a second listener on the home network with its own secret, the QR code, the
      firewall check; no Run there
- [ ] 6. The skill: `SKILL.md`, references, the self-test, the install script (link and hook),
      README

## Review

**Phase 1** (2026-11-13): 23 tests pass on Python 3.10 and 3.14. Checked in the browser pane on a
scratch project: two rounds in the sidebar with progress rings; verdicts, severity and notes save
as you type (`answers.md` follows); Claude adding an item shows live, with focus and caret kept
and answers moved with their items; a second page's answer shows live; with the desk stopped,
answers wait on the page and go through when it is back (the tab reconnects by itself, the secret
is kept in `.review/.secret`); English and German; dark and light; phone width without sideways
scrolling.

**Phase 2** (2026-11-13): 29 tests on both Pythons. Checked live: a background
`review-desk wait` woke on "Hand back to Claude" and printed the answers with the thread (reply,
idea) and the re-test; the page showed "Claude is listening", then "Claude has read it"; Claude's
reply arrived live with a toast; replies, questions and ideas save as you type. Re-test notes live
in the banner and move into the history with the next round (not copied into the thread). The
desktop notification (notify-send, with Open) fires only when no page can show it; tested with a
stand-in so nothing popped up.

**Phase 3** (2026-11-13): 34 tests on both Pythons. Checked live: Run streams a checklist's
command into the page, survives a reload, Stop ends the whole process group (tested), Attach lines
picks a range into a log attachment; the markup editor draws arrows, boxes and blur (a secret
became unreadable) and attaches with a label; a dropped file attaches to its item; the viewer
shows `notes/how.md:3` on its line and the commit with its diff; `answers.md` links every file.
Uploads are named after their item, served as plain text in a sandbox when they are text, with
ranges for recordings. Code blocks got a header row (language, Run, Copy); the accent has a darker
text shade in the light theme. Not testable here: taking a screenshot and recording the screen
need someone to pick a window in the browser's share dialog: part of the user's check.

**Phase 4** (2026-11-13): 38 tests on both Pythons. Checked live: the Ideas board lists every idea
with its status and Claude's reply, filters by status and jumps to the item; `review-desk ask`
put two questions on the page (pill, sidebar entry, toast); answering them woke a background
`wait`, which printed the choices and the note; the summary to copy lists what needs a change, what
partly works, what works, questions and ideas (in the pane, without clipboard access, it opens in
the viewer instead). Tests no longer show desktop notifications (`REVIEW_DESK_NO_NOTIFY`); one
test before that fix may have shown one on the user's desktop.
