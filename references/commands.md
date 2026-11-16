# Commands

All commands work on the project around the current folder (the git repository, or the folder
itself); `--project PATH` names another, before or after the command.

## The desk

- `review-desk start [--no-open]`: the desk in the background. The first time it opens the page in
  the browser (unless `--no-open`); when a tab from before is still open, that tab finds the desk
  again within a few seconds and no new one opens; when a tab is open on another project's desk,
  that tab lists this one ("New desk", with a chime) and no new one opens either. Prints the URL.
  Running it again is harmless.
- `review-desk open`: shows the page in the browser (starting the desk if needed).
- `review-desk stop`: stops it (also stops anything a Run started).
- `review-desk status`: the project, whether it runs and how many pages are open (and whether a
  tab on another desk shows this one), where rounds go, each round with its numbers, who listens,
  where the user is right now, and what waits for you.
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

## One tab for every desk

Every running desk leaves a note in `~/.local/state/review-desk/desks/` (`$REVIEW_DESK_HOME/desks/`
when that is set; `$XDG_STATE_HOME` is honoured) and removes it when it stops. Each desk asks the
others what waits there and shows them in the page's **Desks** list:

- each desk with its colour and badges: a number for what waits for the user (question cards,
  items back for another look, Claude's replies they haven't opened yet), an hourglass for a
  hand-back or answer no `wait` has picked up, a green dot while a session listens;
- under the desk the page is on, its sessions (the main one, and each `owner:`): clicking one
  shows only its rounds and question cards;
- clicking another desk opens it in the same tab (its own address; Back goes back).

A desk with no tab of its own chimes and notifies through the open tab (exactly one: the desk
with the lowest port among those with a page); clicking that notification opens the desk at the
item. The bell at the top right of the page lists the last notifications of every running desk
(each desk keeps its last 100 in `.review/.notices.json`), newest first; a number on it counts the
ones since you last opened it. Asking another desk doesn't keep it alive. The phone shows no Desks
list, and its bell only its own desk's.

## Files

- `.review/<round>/checklist.md`: yours.
- `.review/<round>/answers.md`: theirs, readable, rewritten on every change.
- `.review/<round>/files/`: your pictures and their attachments (named after their item:
  `1-2-screenshot.png`, `pause-recording.webm`, `1-2-log.txt`).
- `.review/<round>/state.json`: the answers as data (the desk's; don't edit it).
- `.review/questions.json`, `events.jsonl`: question cards and what happened.
- `.review/.seen.json`: which of your replies a page has shown the user (the rest count as new).
- `.review/.notices.json`: the last 100 notifications, for the bell.
- `.review/desk.json`: the title and accent. `.review/.desk.log`: the desk's log.

## Ideas that belong to no review

The user adds them on the **Ideas** tab. They don't wake `wait`; each is printed once, after the
answers of the next hand-back (and `status --hook` mentions them at session start).

```bash
review-desk ideas                              # the ones you haven't been shown yet (marks them shown)
review-desk ideas --all                        # every one
review-desk reply board - "On the list for M7." --to b1
review-desk idea board - b1 planned            # new | planned | done | declined
```

## Several sessions on one desk

```bash
review-desk status --as fix-login         # which name you listen as, who else listens
review-desk wait --as fix-login           # only rounds with `owner: fix-login` (run in the background)
review-desk ask --as fix-login q.json     # its answers come to fix-login's wait
REVIEW_DESK_AS=fix-login review-desk wait # the same, through the environment
```

In a linked git worktree the name defaults to the worktree's folder name (on its own project's
desk only), the commands use the main checkout's desk without `--project`, and the worktree's
`.review` becomes a link to the main checkout's, so rounds written there land on the desk. A round with no `owner:` goes to the listener with no
name. Hand-backs nobody listens for stay queued until their owner's `wait` comes.
