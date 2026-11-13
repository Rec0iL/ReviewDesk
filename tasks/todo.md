# Review Desk: tasks

Plan: `~/.claude/plans/review-desk.md` (approved 2026-11-13). One commit per phase.

- [x] 1. Desk and page: repo, the command (`start`/`stop`/`status`/`open`), the stable port,
      `.review/` and the git exclude; the parser, live updates; the sidebar with rounds and
      progress, items with verdict and note, saving as you type; English and German, Grove with
      the accent, "pick up where you left"
- [ ] 2. The conversation: Send to Claude, `wait`, `answers.md`, `status --hook`; questions and
      ideas on items, severity; threads (`reply`), re-test rounds with history (`retest`);
      notifications and the chime, "where you are"
- [ ] 3. Attachments and actions: screenshots with the markup editor, screen recordings, log lines,
      any file; Run buttons with live output and Stop; links to files and the commit, Claude's
      pictures in items
- [ ] 4. Ideas board, question cards (`ask`), summary to copy
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
