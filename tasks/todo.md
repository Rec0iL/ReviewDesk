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
- [x] 5. Phone: a second listener on the home network with its own secret, the QR code, the
      firewall check; no Run there
- [x] 6. The skill: `SKILL.md`, references, the self-test, the install script (link and hook),
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

**Phase 5** (2026-11-13): 41 tests on both Pythons (the phone's server tests now run once, from a
shared base). The QR encoder (byte mode, level M, versions 1–10) reads back with OpenCV at every
version. Checked live: "Let my phone in" opened a second listener on 192.168.1.20 with its own
secret and showed the QR code; the phone's page (opened at phone size) was live, had no Run and no
phone switch, and offered only picture/log/file; turning it off closed the listener (only
127.0.0.1 left). Tests cover the guards: no way in without the code or under another host name,
the desk's own secret doesn't work there, files need the phone's cookie, no Run, no switch, no
quit. The firewall is only asked (FedoraWorkstation lets 1025–65535 through), once per opening.
Also: the start of a Run is reported before its output can arrive (a race in a test).

**Phase 6** (2026-11-13): 42 tests on both Pythons (one checks that the example in
`references/checklist.md` reads the way the file says). `SKILL.md` gives Claude the loop (start,
write a round, `wait` in the background, act, re-arm), when to ask on the page, how to write a good
round; `references/` has the format, the commands and the question cards. `review-desk selftest`
passes on both Pythons. `tools/install.py` links the skill and the command and, only with
`--hook`, adds the session-start hook (tried in a throwaway home: added once, other settings kept,
backed up, removed cleanly).

**The user's check, round 1** (2026-11-13, handed back 14:16): 11 work, 3 partly, 2 need a change.
Fixed:
- the screenshot (the frame now comes from ImageCapture, or a video on the page, each with a time
  limit; the share ends before the editor opens);
- "Lines from a log or a Run" offers the round's Run outputs first, and lines can be dragged over;
- dropping files is caught anywhere on the page, with a confirmation;
- on phones "Take a photo" opens the camera (a picker for several files hid it; checked on a Pixel
  over adb: Google Camera opened), and photos stay JPEG at 2560 px at most;
- the phone icon is green while the phone may get in;
- "20 minutes" follows the page's language;
- the tally is clickable and cycles through each kind;
- on narrow screens the whole page scrolls;
- `retest --each` gives every item its own note;
- the page offers a reload when Review Desk itself was updated.
A live camera preview on the phone needs https (browsers only give the camera stream to secure
pages); declined for now.

**Plans and hand-back message** (2026-11-14): `kind: plan` rounds (plan words, no severity, copy of
the plan only: plans stay where the user keeps them), a message field on the hand-back button
(shown first by `wait`, kept in `answers.md`), a collapsible sidebar (button, Ctrl+B). 51 tests;
checked in the browser pane (hover field, sidebar, plan wording in German).

## One tab for every desk (2026-11-16)

Plan on the desk as `one-tab-plan` (a copy; this is the list). Part 1, sub-session bugs, fixed
first: `3ab875a` (a worktree's name only on its own desk; a stopped `wait` takes nothing),
`8e5128d` (a worktree's `.review` leads to the main checkout's).

- [x] Registry of running desks (`~/.local/state/review-desk/desks/`), written at start, removed
      at stop; stale entries ignored
- [x] `/api/peer` on each desk: title, accent, url, sessions with badges (for you: questions,
      retests, unseen replies; for Claude: hand-backs not picked up; listening), long-polled by
      the other desks; peers don't keep a desk alive
- [x] Seen marks for Claude's replies (`.review/.seen.json`, baseline at first start)
- [x] The page: Desks list with projects and sessions, session filter, peer chimes and
      notifications (not twice), "New desk" instead of a new tab
- [x] `start` opens no tab when another desk's tab watches; `status`/`ask` count that tab
- [x] Phone: no Desks list, no peer events
- [ ] Tests, `SKILL.md`, `references/commands.md`, a check round with screenshots
