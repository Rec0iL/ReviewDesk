---
name: review-desk
description: >-
  Review Desk: a page in the user's browser where they check what you built, item by item, and hand
  their answers back to you, which wakes you up. Use it whenever you have something for the user to
  test or look at by hand (a milestone's manual check, a UI change, a fix to confirm), when you want
  their verdicts, notes, screenshots, screen recordings, log lines or ideas on a list of items, to
  send items back for another look after a fix, or to ask planning questions while their desk is
  open. Also when they type /review-desk, or mention the desk, the review page, the check page, or a
  manual test checklist to tick off.
---

# Review Desk

Each project gets one page, the desk, that runs in the background on this computer
(127.0.0.1, a port of its own) and stays open in the user's browser. One tab is enough for all
projects: its **Desks** list shows every running desk and lets the user switch to another one in
the same tab. You write a round, a Markdown
checklist; it shows up on the page within a second. The user answers each item (works, partly,
needs a change with how bad, can't test, skipped), adds notes, questions, ideas, screenshots they
mark up, recordings and log lines, and clicks **Hand back to Claude**. That wakes your background
`review-desk wait`, which prints their answers. You fix, reply, send items back for another look,
and listen again.

Rounds live in the project's `.review/` folder, which the desk keeps out of git (through
`.git/info/exclude`; no tracked file changes). Never commit it.

`review-desk` below is the command (installed in `~/.local/bin`). If it isn't found, use
`python3 <skill>/scripts/review_desk.py` instead (`<skill>` is this skill's folder). It works on
the project around the current folder; `--project PATH` names another.

## The loop

1. **Start the desk:** `review-desk start`. The first time, it opens the page in the user's
   browser; later a tab still open finds it again by itself, and when the user has a tab open on
   another project's desk, that tab lists the new desk (with a chime) instead of a new tab
   opening. Give the user the URL it prints.
2. **Write the round:** `.review/<round>/checklist.md`, with a short slug for `<round>`
   (`m6a-video`, `login-fix`). The format is in `references/checklist.md`: read it before your
   first round. Put your pictures (before/after) in `.review/<round>/files/` and show them with
   `![what](files/name.png)`. You may edit the checklist later (add items, reword): the page updates
   live and answers stay with their items (use `{#name}` on items you might move).
3. **Listen:** run `review-desk wait` with the Bash tool's `run_in_background: true`. Don't poll
   and don't sleep: you are woken when it ends. It ends when the user hands a round back or answers
   your question cards, and prints what they said. While a `wait` runs, the page tells the user
   "Claude is listening".
4. **Act on the answers.** Read the printed answers (they are also in `.review/<round>/answers.md`;
   their attachments are in `.review/<round>/files/`, and the Read tool shows pictures). Then:
   - if they typed a message with the hand-back, it comes right after "Results from my review are
     in, read them.": it is what they want you to do next, besides the answers;
   - fix what needs a change, run the tests, commit as the project's rules say;
   - answer their questions: `review-desk reply <round> <item> "…"` (`--to <message id>` for a
     particular question or idea; `<item>` is `overall` for the round's own thread);
   - send fixed items back: `review-desk retest <round> <item>… --note "what changed"`; their old
     answer moves into the item's history and they answer it again;
   - what they wrote under "Anything else?" arrives as an item of its own (`A1 {#else1}`, in the
     section "Anything else"): reply with `review-desk reply <round> else1 "…"`, `retest` works on
     it too; the box on the page starts empty again after each hand-back;
   - the Ideas tab's own ideas (the user adds them there, they belong to no review) come after the
     answers, once each: answer with `review-desk reply board - "…" --to <idea id>` and
     `review-desk idea board - <idea id> planned|done|declined`; `review-desk ideas` lists them
     again (`--all` for every one);
   - say what you make of an idea: `review-desk idea <round> <item> <message id> planned|done|declined`.
   Then start `review-desk wait` in the background again, as long as you expect more from them.
5. **Done:** when everything works, say so in the chat. Approvals stay in the chat: merging,
   pushing, deleting, publishing, anything outward-facing. A hand-back is never an approval.

When a session starts with a note like "Review Desk: answers waiting", run `review-desk wait`
(it returns at once with them). A note about new ideas on the Ideas tab means `review-desk ideas`.

When a session starts with "Review Desk has an update", tell the user in one line and offer it;
run `review-desk update` only after they agree (it pulls the new version, fast-forward only). A
running desk keeps the old version until `review-desk stop` and `start`.

## Several sessions, one desk

Sessions you start (in a git worktree or not) share the project's one desk, so the user has one
page. Each session listens only for its own rounds:

- **Your name.** In a linked git worktree, the commands work on the main checkout's desk by
  themselves and you listen as the worktree's folder name (on that desk only; with `--project`
  naming another project you have no name there). Anywhere else, give a name with `--as NAME`
  (or `REVIEW_DESK_AS=NAME`). `review-desk status` says which name you listen as, and where
  rounds go.
- **Your rounds' folder.** In a worktree, write rounds at `.review/<round>/` as usual: any
  `review-desk` command there makes the worktree's `.review` lead to the main checkout's (git
  ignores it), so your file tools may write there. Run `review-desk start` first.
- **Your rounds.** Put `owner: NAME` in the header of every round you write, from the first
  write on: a hand-back goes to the owner the header names at that moment. A round without
  `owner:` belongs to the session with no name (the main one, the plain case).
- **Listening.** `review-desk wait --as NAME` (in a worktree plain `review-desk wait` is enough)
  returns only hand-backs of your rounds and answers to questions you asked with
  `review-desk ask --as NAME`. Hand-backs of other rounds stay queued for their own session; no
  listener takes another's. The Ideas tab goes to the session with no name.
- **One `wait` per session.** Two at once with the same name: only one gets the next hand-back.
  `review-desk status` and the page say so. Stopping a `wait` is safe: a hand-back that comes
  after it stopped waits for the next one.
- **On the page** the Desks list shows the project's sessions with what waits in each; the user
  can show one session's rounds and question cards only.
- `reply`, `retest`, `idea`, `answers` need no name: they name the round.

One session alone needs none of this: no `owner:`, no `--as`, as before.

## Asking questions

`review-desk status` shows how many pages are open. While at least one is, ask planning questions
on the page: `review-desk ask` with JSON shaped like your chat question tool (see
`references/questions.md`). The user gets a chime and a card; the answers come through `wait`
(or right away with `ask --wait`). With no page open, ask in the chat as usual.

## Writing a good round

- Write in the user's language. The page's own words follow their browser (English or German).
- One thing to check per item, in the order they would do it. Say what to do (`Do:`), what they
  should see (`Expected:`, the most useful line), and what to prepare (`Setup:`) when it matters.
- Put the commands they need in ```` ```bash ```` blocks: the page shows a **Run** button and streams
  the output. Run executes the block in the project folder when the user clicks it, so only write
  commands you would run yourself, and never secrets.
- Name the round's time honestly in the title (`# M6a check (about 15 minutes)`). The desk tracks
  no time.
- Name log files in the header (`log: ~/.local/state/app/log.txt`) so the user can attach lines
  from them; name the commit (`commit: abc1234`) so they can look at what changed.
- After a fix, prefer `retest` on the items over writing a new round; a new round is for new work.

## Plans on the desk

The user can comment on a plan the same way they check work. A plan is a round with `kind: plan` in
its header: each step or decision is an item, each part of the plan a `##` section, the reasoning
sits as text under it. The page then says **Agree / Agree, with changes / Change it / Unclear /
Skip** and **Send comments**, and hides "how bad".

```markdown
---
kind: plan
---
# Plan: login rework (about 5 minutes)

## 1. Approach

- [ ] Sessions move to signed cookies. {#cookies}
      Why: no server-side store to run; the token carries the user id.
```

- **Where plans live is the user's choice.** The desk only receives a copy: leave your plan where it
  already is (plan mode, `tasks/todo.md`, `~/.claude/plans/`) and change no structure. Ask once per
  project, the first time, where plans are kept, and say in the project's notes what they chose.
- Write the round, `review-desk wait` in the background, read the comments (`Partly` and
  `Needs change` mean revise that step, `Can't test` means it is unclear: answer or reword).
- Revise by editing the checklist and `retest`ing the changed steps with a note on what changed;
  their earlier comment moves into the step's history. Build only after every step is agreed or the
  user says go in the chat.
- A hand-back message ("continue with milestone X", "commit and push") is the user's own words in
  the chat sense: act on what it asks, but a push or merge still follows the rules of the project.

## Commands

`references/commands.md` has all of them with examples. The everyday ones:

| Command | What it does |
|---|---|
| `review-desk start` | the desk in the background, opened once in the browser |
| `review-desk wait` | waits for a hand-back or answers (run it in the background) |
| `review-desk answers <round>` | a round's answers as they are now |
| `review-desk reply`, `retest`, `idea` | your side of the conversation |
| `review-desk ask [file]` | question cards on the page |
| `review-desk status` | rounds, open pages, where the user is, what waits for you |
| `review-desk stop` / `open` | stop it / show it in the browser again |
| `review-desk selftest` | checks that the desk works on this computer |
| `review-desk update` | gets a newer Review Desk (only when the user agreed) |

If something seems off: `review-desk status`, then `.review/.desk.log`, then `review-desk stop`
and `start`.

## Good to know

- The desk stops by itself after a day with no page and no command (another desk's tab
  listing it doesn't count). Starting it again keeps everything; the same tab reconnects, and
  the other desks' tabs list it again.
- **One tab for all desks.** Every running desk notes itself in `~/.local/state/review-desk/desks/`.
  The page's Desks list shows each one with badges: a number for what waits for the user
  (question cards, items back for another look, replies of yours they haven't opened), an
  hourglass for a hand-back no `wait` has picked up yet, a green dot while a session listens.
  A desk without a tab of its own chimes and notifies through the tab that is open. That tab
  counts as an open page for `ask` and `status`. A desk still running older code joins the list
  after `review-desk stop` and `start` (ask the user before restarting a desk with pages open).
- The user can open the desk on their phone (the phone button on the page: a QR code over the home
  network, its own secret, closed after eight hours). The phone answers and takes photos but never
  runs commands. Only the user turns it on; never do it for them.
- Desktop notifications and a chime tell the user when you replied, re-tested or asked, even with
  the page in the background. The bell at the top right lists what you did lately on every desk.
