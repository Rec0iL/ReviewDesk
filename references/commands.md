# Commands

All commands work on the project around the current folder (the git repository, or the folder
itself); `--project PATH` names another, before or after the command.

## The desk

- `review-desk start [--no-open]`: the desk in the background. The first time it opens the page in
  the browser (unless `--no-open`); when a tab from before is still open, that tab finds the desk
  again within a few seconds and no new one opens. Prints the URL. Running it again is harmless.
- `review-desk open`: shows the page in the browser (starting the desk if needed).
- `review-desk stop`: stops it (also stops anything a Run started).
- `review-desk status`: the project, whether it runs and how many pages are open, each round with
  its numbers, where the user is right now, and what waits for you.
- `review-desk status --hook`: a line only when answers wait, and one when an update is waiting (for the session-start hook).
- `review-desk config --title "LightGrove" --accent "#7fb3ff"`: the name and colour the page shows.
- `review-desk selftest`: checks that the desk works here (Python, parser, server, saving, QR).
- `review-desk update`: gets a newer Review Desk from the clone's upstream (fetch, then a
  fast-forward; refuses when the clone has local changes). `status` and the session-start hook say
  when one is waiting: at most once a day they start a quiet `git fetch` in the background, so they
  never wait on the network. `REVIEW_DESK_NO_UPDATE_CHECK=1` turns that off.

## Hearing back

- `review-desk wait [--timeout S]`: returns as soon as the user hands a round back or answers
  question cards, and prints the answers (each hand-back goes out once). Without `--timeout` it
  waits as long as it takes. Run it in the background and start it again after it returns. It
  starts the desk if needed (without opening a page).
- `review-desk answers <round>`: a round's answers as they are right now, handed back or not.

## Your side of the conversation

- `review-desk reply <round> <item> "text" [--to <message id>]`: your reply in an item's thread;
  `<item>` is the item's name or number, or `overall`. `-` as the text reads it from stdin (for long
  replies). Markdown works: `code`, **bold**, links.
- `review-desk retest <round> <item>... [--note "what changed"]`: items back for another look. The
  round's number goes up, each item's answer moves into its history, its note shows above it, and
  the round counts as not handed back until they hand it back again.
- `review-desk idea <round> <item> <message id> planned|done|declined|new`: your word on an idea;
  the Ideas board shows it.
- `review-desk ask [file|-] [--wait]`: question cards (see `questions.md`).

These work with the desk stopped too: they then write straight into `.review/`, and the page
shows them when it next opens.

## Files

- `.review/<round>/checklist.md`: yours.
- `.review/<round>/answers.md`: theirs, readable, rewritten on every change.
- `.review/<round>/files/`: your pictures and their attachments (named after their item:
  `1-2-screenshot.png`, `pause-recording.webm`, `1-2-log.txt`).
- `.review/<round>/state.json`: the answers as data (the desk's; don't edit it).
- `.review/questions.json`, `events.jsonl`: question cards and what happened.
- `.review/desk.json`: the title and accent. `.review/.desk.log`: the desk's log.
