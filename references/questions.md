# Question cards

`review-desk ask` puts a set of questions on the page, shaped like your chat question tool. Use
it while a page is open (`review-desk status` shows how many); otherwise ask in the chat.

```bash
review-desk ask - <<'EOF'
{"title": "Ping-pong at the ends",
 "questions": [
  {"question": "What should happen at each end of a ping-pong loop?", "header": "Ends",
   "options": [{"label": "Turn at once", "description": "No pause; the last frame shows once."},
               {"label": "Hold briefly", "description": "Rest on the end frame for a moment."}]},
  {"question": "Which speeds should the menu offer?", "header": "Speeds", "multiSelect": true,
   "options": ["0.5×", "1×", "2×", "4×"]}
 ]}
EOF
```

- One to six questions per set; each with two to six options (a label, or `{label, description}`);
  `header` is a short chip (up to 40 characters); `multiSelect` lets them pick several.
- Every question also gets "Something else …" for their own words, and a note field.
- The command prints the set's id (`asked q3`). The answers come through `review-desk wait`;
  `ask --wait` asks and then waits itself (run it in the background either way).
- With no page open, the desk still takes the questions and shows a desktop notification that
  brings the user to them; if they don't come, ask in the chat.

What `wait` prints:

```
Answered at 2026-11-13 13:33: Ping-pong at the ends (q1)
- What should happen at each end of a ping-pong loop?
  → Hold briefly
  note: About half a second.
- Which speeds should the menu offer?
  → 1×, 2×, 4×
```

An answer in their own words shows as `→ in their own words: …`.

## Cards and a round together

While a round of yours waits for the user (not handed back yet, or back for another look), the
cards you asked under the same name go back with it. The round's button reads **Answer and hand
back** (**Answer and send comments** on a plan round); clicking it shows your open cards one after
another (Next, then Hand back on the last) and hands back when they are done. "Later" stops it and
sends nothing; what they picked stays on the page. The "Claude asks" button still answers a card
on its own.

The desk keeps the answers and the hand-back in one step, so `wait` prints them together:

```
Results from my review are in, read them.

Handed back at 2026-11-16 21:01: login-fix. The answers (…/answers.md):

… the round's answers …

Your answers to my questions, given with this hand-back:

Remember me (q1)
- How long should "Remember me" keep you signed in?
  → A week
  note: Two weeks would be fine too.
```

Which cards count: those asked with the round's owner name (`ask --as NAME` for a round with
`owner: NAME` in its header, plain `ask` for a round without one). Cards of another session stay
for that session's own round.
