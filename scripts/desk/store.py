"""Review rounds on disk: each round a folder in `.review/` with Claude's `checklist.md`, the
answers in `state.json` (written only here), a readable `answers.md` rewritten on every change
(what Claude reads), and `files/`. Plus `events.jsonl`, what happened, for `wait` and the
session-start hook.
"""
import html
import json
import re
import threading
import time
import zlib
from pathlib import Path

from . import markdown
from .project import read_json, write_json

VERDICTS = ("works", "partly", "change", "blocked", "skipped")
SEVERITIES = ("cosmetic", "annoying", "broken")
KINDS = ("note", "question", "idea", "reply", "comment")
IDEA_STATES = ("new", "planned", "done", "declined")
SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
MESSAGE_ID = re.compile(r"^[a-z][a-z0-9]{0,31}$")
MAX_TEXT = 50_000
LABELS = {
    "works": "Works", "partly": "Partly works", "change": "Needs change",
    "blocked": "Can't test", "skipped": "Skipped", "": "Not tried",
}

LOCK = threading.RLock()


def now():
    return time.strftime("%Y-%m-%d %H:%M")


class Rounds:
    """The rounds of one project's `.review/` folder."""

    def __init__(self, folder):
        self.folder = Path(folder)

    # -- rounds ------------------------------------------------------------------------------

    def slugs(self):
        """Every round: a folder with a `checklist.md`, newest first."""
        found = [p.parent for p in self.folder.glob("*/checklist.md") if SLUG.match(p.parent.name)]
        return [p.name for p in sorted(found, key=lambda p: self.created(p.name), reverse=True)]

    def path(self, slug, name=""):
        if not SLUG.match(slug or ""):
            raise ValueError(f"no round {slug!r}")
        return self.folder / slug / name if name else self.folder / slug

    def created(self, slug):
        state = read_json(self.path(slug, "state.json"), {}) or {}
        if state.get("created"):
            return state["created"]
        checklist = self.path(slug, "checklist.md")
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(checklist.stat().st_mtime)) if checklist.exists() else ""

    def doc(self, slug):
        """The round's checklist, read."""
        checklist = self.path(slug, "checklist.md")
        if not checklist.exists():
            raise ValueError(f"no round {slug!r}")
        doc = markdown.parse(checklist.read_text(encoding="utf-8"), slug, files=markdown.Files(f"/files/{slug}", self.path(slug)))
        extras = (read_json(self.path(slug, "state.json"), {}) or {}).get("extras", [])
        if extras:
            # what you wrote under "Anything else?" when you handed back: items of their own now
            doc["sections"].append({"id": "else", "kind": "else", "title": "Anything else", "html": "Anything else", "blocks": [
                {"type": "item", "id": e["id"], "number": f"A{k}", "md": e["text"], "extra": True, "done": False,
                 "html": html.escape(e["text"]).replace("\n", "<br>"), "fields": [], "children": []}
                for k, e in enumerate(extras, 1)]})
        return doc

    def state(self, slug, doc=None):
        """The round's answers, fitted to its checklist as it is now: answers follow their item
        (by its name or number, or by its text when Claude reworded the numbering away)."""
        doc = doc or self.doc(slug)
        saved = read_json(self.path(slug, "state.json"), {}) or {}
        old = saved.get("items", {})
        by_text = {a.get("text"): a for a in old.values() if a.get("text")}
        listed = markdown.all_items(doc)
        texts = {it["md"] for it in listed}
        items = {}
        for it in listed:
            a = old.get(it["id"])
            if a and a.get("text") and a["text"] != it["md"]:
                if it["md"] in by_text:
                    a = by_text[it["md"]]   # this item's answer, saved under its old number
                elif a["text"] in texts:
                    a = None                # that answer went with its item to a new number
                # otherwise Claude reworded the item in place: its answer stays
            elif not a:
                a = by_text.get(it["md"])
            items[it["id"]] = blank(it, a)
        return {
            "version": 1,
            "created": saved.get("created") or self.created(slug),
            "round": saved.get("round", 1),
            "items": items,
            "overall": {"note": "", "files": [], "messages": [], **saved.get("overall", {})},
            "extras": saved.get("extras", []),
            "sent": saved.get("sent"),
            "message": saved.get("message") or "",
            "changed": saved.get("changed"),
        }

    def save(self, slug, state, doc=None):
        """Keeps `state` and rewrites `answers.md` from it."""
        doc = doc or self.doc(slug)
        state["changed"] = now()
        write_json(self.path(slug, "state.json"), state)
        self.path(slug, "answers.md").write_text(answers_md(slug, doc, state), encoding="utf-8")

    def summary(self, slug, seen=None):
        """What the sidebar shows of a round (with `seen`, the keys of Claude's messages a page
        has shown: how many it hasn't)."""
        doc = self.doc(slug)
        state = self.state(slug, doc)
        out = {
            "slug": slug, "title": doc["title"], "about": doc["about"], "created": state["created"],
            "round": state["round"], "sent": state["sent"], "counts": counts(state),
        }
        if seen is not None:
            out["unseen"] = len(claude_keys(state) - seen)
        return out

    # -- changes (each under the lock, each saved) -------------------------------------------

    def edit(self, slug, change):
        """Runs `change(doc, state)` on the round and saves it. Returns what `change` returns."""
        with LOCK:
            doc = self.doc(slug)
            state = self.state(slug, doc)
            result = change(doc, state)
            self.save(slug, state, self.doc(slug))      # the doc may have gained an item
            return result

    def set_item(self, slug, item_id, fields):
        """The user's verdict, severity or note on an item (whichever `fields` has)."""

        def change(doc, state):
            a = item(state, item_id)
            before = a["verdict"]
            if "verdict" in fields:
                if fields["verdict"] not in (*VERDICTS, ""):
                    raise ValueError(f"a verdict is one of {', '.join(VERDICTS)} or none")
                a["verdict"] = fields["verdict"]
                if a["verdict"] != "change":
                    a["severity"] = ""
            if "severity" in fields:
                if fields["severity"] not in (*SEVERITIES, ""):
                    raise ValueError(f"a severity is one of {', '.join(SEVERITIES)} or none")
                a["severity"] = fields["severity"]
            mark(a, before)
            if "note" in fields:
                a["note"] = text(fields["note"])
            answered(a)
            return a

        return self.edit(slug, change)

    def set_overall(self, slug, note):
        return self.edit(slug, lambda doc, state: state["overall"].update(note=text(note)) or state["overall"])

    def message(self, slug, item_id, kind, body, sender="you", reply_to=None, message_id=None):
        """A message in an item's thread (`overall` for the round's own): your question, idea or
        comment, or Claude's reply. The page names its messages itself (`message_id`), so saving
        one again only changes its text."""
        if kind not in KINDS:
            raise ValueError(f"a message is a {', '.join(KINDS)}")
        if message_id is not None and not MESSAGE_ID.match(str(message_id)):
            raise ValueError("a message id is a few letters and digits")

        def change(doc, state):
            thread = messages(state, item_id)
            m = next((m for m in thread if m["id"] == message_id), None) if message_id else None
            if m:
                if m["from"] != sender:
                    raise ValueError("that message isn't yours to change")
                m.update(text=text(body), kind=kind, edited=now())
                return m
            m = {"id": message_id or next_id(thread, "c" if sender == "claude" else "m"), "from": sender,
                 "kind": kind, "text": text(body), "at": now()}
            if reply_to:
                m["to"] = reply_to
            if kind == "idea":
                m["status"] = "new"
            thread.append(m)
            return m

        return self.edit(slug, change)

    def delete_message(self, slug, item_id, message_id, sender="you"):
        """Takes one of your messages back (gone already is fine)."""

        def change(doc, state):
            thread = messages(state, item_id)
            for m in list(thread):
                if m["id"] == message_id:
                    if m["from"] != sender:
                        raise ValueError("that message isn't yours to remove")
                    thread.remove(m)
            return None

        return self.edit(slug, change)

    def idea_status(self, slug, item_id, message_id, status):
        """Claude's word on an idea: planned, done, declined (or new again)."""
        if status not in IDEA_STATES:
            raise ValueError(f"an idea's status is one of {', '.join(IDEA_STATES)}")

        def change(doc, state):
            m = next((m for m in messages(state, item_id) if m["id"] == message_id), None)
            if not m or m["kind"] != "idea":
                raise ValueError(f"no idea {message_id} on {item_id}")
            m["status"] = status
            return m

        return self.edit(slug, change)

    def add_file(self, slug, item_id, name, kind, label=""):
        """An attachment (already in the round's `files/`) on an item or the round."""

        def change(doc, state):
            files = files_of(state, item_id)
            entry = {"name": name, "kind": kind, "at": now()}
            if label:
                entry["label"] = text(label)[:300]
            files.append(entry)
            if item_id != "overall":
                answered(item(state, item_id))
            return entry

        return self.edit(slug, change)

    def remove_file(self, slug, item_id, name):
        """Takes an attachment off its item; returns whether it was there."""

        def change(doc, state):
            files = files_of(state, item_id)
            before = len(files)
            files[:] = [f for f in files if f["name"] != name]
            if item_id != "overall":
                answered(item(state, item_id))
            return len(files) != before

        return self.edit(slug, change)

    def send(self, slug, message=""):
        """The round handed back to Claude, with the words the user typed on the button (if any)."""
        message = text(message).strip()[:2000]

        def change(doc, state):
            state.update(sent=now(), message=message)
            archive_overall(state)
            return state["sent"]

        return self.edit(slug, change)

    def settle(self):
        """Rounds handed back before "Anything else?" turned into items: what is still in the box,
        untouched since the hand-back, becomes an item now."""
        for slug in self.slugs():
            try:
                def change(doc, state):
                    if state["sent"] and state.get("changed") and state["changed"] <= state["sent"]:
                        archive_overall(state)

                self.edit(slug, change)
            except (OSError, ValueError):
                continue

    def retest(self, slug, item_ids, note="", notes=None):
        """Items back for another look: what they had goes into their history, a new round starts
        for them, Claude's note says what changed (`notes` gives an item a note of its own)."""
        notes = notes or {}
        if not isinstance(notes, dict) or not all(isinstance(v, str) for v in notes.values()):
            raise ValueError("notes: an item's name, then its note")
        if not item_ids:
            raise ValueError("which items?")

        def change(doc, state):
            for item_id in item_ids:
                item(state, item_id)  # all of them exist, before anything changes
            archive_overall(state) if state["sent"] else None
            state["round"] += 1
            for item_id in item_ids:
                a = item(state, item_id)
                a["history"].append({
                    "round": state["round"] - 1, "verdict": a["verdict"], "severity": a["severity"],
                    "note": a["note"], "files": a["files"], "retest": a["retest"], "at": now(),
                    "answered": a.get("answered"),
                })
                a.update(verdict="", severity="", note="", files=[], answered=None)
                a["retest"] = {"round": state["round"], "note": text(notes.get(item_id, note)), "at": now()}
            state["sent"] = None
            state["message"] = ""
            return state["round"]

        return self.edit(slug, change)


def blank(it, saved=None):
    """An item's answers: what was saved for it, filled out; nothing saved means not tried (or
    works, when the checklist already ticks it)."""
    a = {
        "text": it["md"], "verdict": "works" if it["done"] else "", "severity": "", "note": "",
        "messages": [], "files": [], "retest": None, "history": [], "extra": bool(it.get("extra")),
        "answered": None,
    }
    if saved:
        a.update({k: saved[k] for k in a if k in saved and k != "text"})
    return a


def mark(a, before):
    """A verdict you pick shows in the item's conversation as a line of its own ("You picked:
    Partly"), at the time you picked it. Changing your mind right away (nothing said since)
    changes that line instead of adding one; taking a first verdict back right away removes it.
    A severity belongs to the latest line."""
    thread = a["messages"]
    last = thread[-1] if thread else None
    fresh = bool(last) and last.get("kind") == "mark" and not (a["retest"] and a["retest"]["at"] >= last["at"])
    if a["verdict"] == before:
        lines = [m for m in thread if m.get("kind") == "mark"]
        if lines and lines[-1].get("severity", "") != a["severity"]:
            lines[-1]["severity"] = a["severity"]
        return
    if fresh and not a["verdict"] and not last.get("prev"):
        thread.remove(last)
    elif fresh:
        last.update(verdict=a["verdict"], severity=a["severity"], at=now())
    else:
        line = {"id": next_id(thread, "v"), "from": "you", "kind": "mark", "text": "",
                "verdict": a["verdict"], "severity": a["severity"], "at": now()}
        if before:
            line["prev"] = before    # what it was before this line (none: a first verdict)
        thread.append(line)


def answered(a):
    """When you first answered an item in this round (verdict, note or a file), so the page can
    place your answer in the item's conversation; gone again once all of it is."""
    if a["verdict"] or a["note"].strip() or a["files"]:
        a["answered"] = a.get("answered") or now()
    else:
        a["answered"] = None


def archive_overall(state):
    """What you wrote under "Anything else?" (note, files, questions, ideas) moves into an item of
    its own, so it can be answered and talked about like the others; the box starts empty."""
    o = state["overall"]
    if not (o["note"].strip() or o["files"] or o["messages"]):
        return
    extras = state.setdefault("extras", [])
    used = {e["id"] for e in extras}
    n = len(extras) + 1
    while f"else{n}" in used:
        n += 1
    entry = {"id": f"else{n}", "round": state["round"], "at": now(),
             "text": o["note"].strip() or "(files and messages only)"}
    extras.append(entry)
    state["items"][entry["id"]] = {
        "text": entry["text"], "verdict": "", "severity": "", "note": "", "messages": o["messages"],
        "files": o["files"], "retest": None, "history": [], "extra": True, "answered": None,
    }
    state["overall"] = {**o, "note": "", "files": [], "messages": []}


OWNER = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def owner_name(value):
    """A listener's name (letters, digits, `.`, `_`, `-`), or "" for none."""
    value = str(value or "").strip()
    if value and not OWNER.match(value):
        raise ValueError("an owner is a short name: letters, digits, . _ -")
    return value


def item(state, item_id):
    if item_id not in state["items"]:
        raise ValueError(f"no item {item_id!r} in this round")
    return state["items"][item_id]


def files_of(state, item_id):
    return state["overall"]["files"] if item_id == "overall" else item(state, item_id)["files"]


def messages(state, item_id):
    return state["overall"]["messages"] if item_id == "overall" else item(state, item_id)["messages"]


def next_id(thread, prefix):
    taken = [int(m["id"][len(prefix):]) for m in thread if m.get("id", "").startswith(prefix) and m["id"][len(prefix):].isdigit()]
    return f"{prefix}{max(taken, default=0) + 1}"


def text(value):
    if not isinstance(value, str) or len(value) > MAX_TEXT:
        raise ValueError("text, at most 50 000 characters")
    return value


def counts(state):
    c = {v: 0 for v in VERDICTS} | {"open": 0, "retest": 0, "broken": 0, "total": 0}
    for a in state["items"].values():
        if a.get("extra") and not a["verdict"]:
            continue      # a note you handed back under "Anything else": nothing to answer
        c[a["verdict"] or "open"] += 1
        c["retest"] += bool(a["retest"] and not a["verdict"])
        c["broken"] += a["severity"] == "broken"
        c["total"] += 1
    return c


def claude_keys(state):
    """Claude's messages in a round, each by a key that stays when its thread moves (what you
    wrote under "Anything else?" becomes an item of its own at a hand-back)."""
    threads = [a["messages"] for a in state["items"].values()] + [state["overall"]["messages"]]
    return {format(zlib.crc32(f"{m['id']}|{m.get('at')}|{m.get('text')}".encode("utf-8")), "08x")
            for thread in threads for m in thread if m.get("from") == "claude"}


class Seen:
    """Which of Claude's replies a page has shown you (`.seen.json`): the rest are new, and the
    Desks list counts them. The first time, everything there already counts as seen."""

    def __init__(self, folder):
        self.path = Path(folder) / ".seen.json"

    def start(self, rounds):
        if self.path.exists():
            return
        data = {}
        for slug in rounds.slugs():
            try:
                data[slug] = sorted(claude_keys(rounds.state(slug)))
            except (OSError, ValueError):
                continue
        write_json(self.path, {"rounds": data})

    def all(self):
        return {k: set(v) for k, v in ((read_json(self.path, {}) or {}).get("rounds") or {}).items()}

    def mark(self, rounds, slug):
        """The page shows you the round now: every reply in it counts as seen."""
        keys = claude_keys(rounds.state(slug))
        with LOCK:
            data = read_json(self.path, {}) or {}
            kept = data.setdefault("rounds", {})
            if set(kept.get(slug, [])) >= keys:
                return False
            kept[slug] = sorted(keys | set(kept.get(slug, [])))
            write_json(self.path, data)
        return True


def quoted(body, pad="  "):
    return [f"{pad}> {line}" if line.strip() else f"{pad}>" for line in body.strip().splitlines()]


def thread_md(thread, pad):
    """An item's messages as lines of `answers.md` (empty ones left out)."""
    out = []
    for m in thread:
        if not m["text"].strip():
            continue
        who = "Claude" if m["from"] == "claude" else "You"
        status = f" [{m.get('status', 'new')}]" if m["kind"] == "idea" else ""
        to = f" (to {m['to']})" if m.get("to") else ""
        out.append(f"{pad}- {who}, {m['kind']} {m['id']}{status}{to}: " + m["text"].strip().replace("\n", " ⏎ "))
    return out


def answers_md(slug, doc, state):
    """The round's answers as Claude reads them: each item with its verdict, note, files, thread,
    re-test and history; items not tried listed short."""
    c = counts(state)
    tally = (f"{c['works']} work · {c['partly']} partly · {c['change']} need a change ({c['broken']} broken) · "
             f"{c['blocked']} can't test · {c['skipped']} skipped · {c['open']} not tried")
    out = [f"# {doc['title']}: answers", "",
           f"Round {state['round']} · {'handed back ' + state['sent'] if state['sent'] else 'not handed back yet'} · {tally}", "",
           f"Files are in `{slug}/files/`, next to this file.", ""]
    if doc.get("meta", {}).get("kind") == "plan":
        out[2:2] = ["", "This is a review of a plan: Works = agreed, Partly = agreed with changes, "
                        "Needs change = change it, Can't test = unclear, Skipped = skip it."]
    if state.get("message") and state.get("sent"):
        out[4:4] = [f"Message with the hand-back: {state['message']}", ""]
    for section in doc["sections"]:
        listed = list(markdown.items(section["blocks"]))
        if not listed:
            continue
        out += [f"## {section['title'] or 'Before you start'}", ""]
        for it in listed:
            a = state["items"][it["id"]]
            verdict = LABELS[a["verdict"]] + (f" ({a['severity']})" if a["severity"] else "")
            if a.get("extra") and not a["verdict"]:
                verdict = "Anything else"
            label = it["number"] if it["id"] == it["number"] else f"{it['number']} {{#{it['id']}}}"
            out.append(f"- **{verdict}** · {label} · {it['md']}")
            if a["retest"]:
                out.append(f"  - Re-test (round {a['retest']['round']})" + (": " + a["retest"]["note"] if a["retest"]["note"] else ""))
            if a["note"].strip():
                out += quoted(a["note"])
            for f in a["files"]:
                out.append(f"  - {f['kind'].capitalize()}: [{f['name']}](files/{f['name']})" + (f" {f['label']}" if f.get("label") else ""))
            out += thread_md(a["messages"], "  ")
            for h in a["history"]:
                out.append(f"  - Round {h['round']}: {LABELS[h['verdict']]}" + (f" ({h['severity']})" if h["severity"] else "")
                           + (": " + h["note"].strip().replace("\n", " ⏎ ") if h["note"].strip() else ""))
                if (h.get("retest") or {}).get("note"):
                    out.append(f"    - (it came back for round {h['round']} with: {h['retest']['note'].strip()})")
        out.append("")
    o = state["overall"]
    if o["note"].strip() or o["files"] or o["messages"]:
        out += ["## Overall", ""] + quoted(o["note"], "")
        for f in o["files"]:
            out.append(f"- {f['kind'].capitalize()}: [{f['name']}](files/{f['name']})")
        out += thread_md(o["messages"], "")
        out.append("")
    return "\n".join(out)


# -- Claude's questions ------------------------------------------------------------------------

class Questions:
    """Claude's planning questions, shaped like its question cards in the chat: each set has a
    title and up to six questions, each with two to six options (and room for your own)."""

    def __init__(self, folder):
        self.path = Path(folder) / "questions.json"

    def all(self):
        return read_json(self.path, []) or []

    def pending(self):
        return [q for q in self.all() if not q.get("answered")]

    def get(self, qid):
        return self._find(self.all(), qid)

    def add(self, data):
        """A new set of questions (checked first). Returns it with its id."""
        asked = checked_questions(data)
        with LOCK:
            sets = self.all()
            asked["id"] = next_id(sets, "q")
            asked["owner"] = owner_name(data.get("owner", ""))
            asked["asked"] = now()
            asked["answered"] = None
            sets.append(asked)
            write_json(self.path, sets)
        return asked

    def answer(self, qid, answers):
        """Your answers to a set: for each question the options you chose, your own words, a
        note. Returns the set with its answers."""
        with LOCK:
            sets = self.all()
            found = self._find(sets, qid)
            if found.get("answered"):
                raise ValueError("already answered")
            found.update(answers=checked_answers(found, answers), answered=now())
            write_json(self.path, sets)
            return found

    def answer_all(self, given, owner=""):
        """The answers given with a hand-back (`[{id, answers}]`), for the round owner's cards
        only. All of them are checked before any is kept: one wrong, none kept. A set answered
        in the meantime (another tab) is left as it is. Returns the sets answered now."""
        if not isinstance(given, list):
            raise ValueError("answers: a list of question sets")
        with LOCK:
            sets = self.all()
            done = []
            for g in given:
                found = self._find(sets, g.get("id") if isinstance(g, dict) else None)
                if found.get("owner", "") != owner:
                    raise ValueError(f"{found['id']} belongs to another session")
                if not found.get("answered") and all(found is not d for d, _ in done):
                    done.append((found, checked_answers(found, g.get("answers"))))
            at = now()
            for found, answers in done:
                found.update(answers=answers, answered=at)
            if done:
                write_json(self.path, sets)
            return [found for found, _ in done]

    @staticmethod
    def _find(sets, qid):
        found = next((q for q in sets if q["id"] == qid), None)
        if not found:
            raise ValueError(f"no question {qid!r}")
        return found


def checked_answers(found, answers):
    """Answers to a set as the page sends them, checked against its questions."""
    if not isinstance(answers, list) or len(answers) != len(found["questions"]):
        raise ValueError("one answer for each question")
    out = []
    for q, a in zip(found["questions"], answers):
        a = a if isinstance(a, dict) else {}
        labels = [o["label"] for o in q["options"]]
        chosen = [c for c in (a.get("chosen") or []) if c in labels]
        if not q.get("multiSelect") and len(chosen) > 1:
            raise ValueError(f"one choice for {q['question']!r}")
        out.append({"question": q["question"], "chosen": chosen,
                    "other": text(a.get("other") or "")[:5000], "note": text(a.get("note") or "")[:5000]})
    return out


def checked_questions(data):
    """A set of questions as Claude sends it, checked and trimmed to what the page shows."""
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        raise ValueError("questions: a list of questions")
    qs = data["questions"]
    if not 1 <= len(qs) <= 6:
        raise ValueError("one to six questions")
    out = []
    for q in qs:
        if not isinstance(q, dict) or not str(q.get("question", "")).strip():
            raise ValueError("each question needs its question")
        options = q.get("options") or []
        if not isinstance(options, list) or not 2 <= len(options) <= 6:
            raise ValueError(f"{q['question']!r}: two to six options")
        opts = []
        for o in options:
            o = {"label": o} if isinstance(o, str) else o
            if not isinstance(o, dict) or not str(o.get("label", "")).strip():
                raise ValueError(f"{q['question']!r}: each option needs a label")
            opts.append({"label": str(o["label"])[:200], "description": str(o.get("description", ""))[:1000]})
        if len({o["label"] for o in opts}) != len(opts):
            raise ValueError(f"{q['question']!r}: two options share a label")
        out.append({"question": str(q["question"])[:1000], "header": str(q.get("header", ""))[:40],
                    "multiSelect": bool(q.get("multiSelect")), "options": opts})
    return {"title": str(data.get("title", ""))[:200], "questions": out}


class Board:
    """Ideas that belong to no review (`board.json`): the user's, added on the Ideas tab, with the
    replies of both sides. `seen` is when Claude was shown one (by `wait` or `ideas`); a new reply
    of the user's makes it unseen again. `followups` are the user's answers, from the Ideas tab, on
    ideas that live in a review: Claude gets them the same way."""

    def __init__(self, folder):
        self.path = Path(folder) / "board.json"

    def _data(self):
        data = read_json(self.path, {}) or {}
        return {"version": 1, "ideas": data.get("ideas", []), "followups": data.get("followups", [])}

    def all(self):
        return self._data()["ideas"]

    def _edit(self, change):
        with LOCK:
            data = self._data()
            result = change(data)
            write_json(self.path, data)
            return result

    def add(self, body, idea_id=None):
        """A new idea; the page names it itself (`idea_id`), so saving again only changes its text."""
        body = text(body).strip()
        if not body:
            raise ValueError("an idea needs some words")
        if idea_id is not None and not MESSAGE_ID.match(str(idea_id)):
            raise ValueError("an idea id is a few letters and digits")

        def change(data):
            items = data["ideas"]
            m = next((m for m in items if m["id"] == idea_id), None) if idea_id else None
            if m:
                m.update(text=body, edited=now())
                m.pop("seen", None)   # reworded: Claude should read it again
                return m
            m = {"id": idea_id or next_id(items, "b"), "text": body, "at": now(), "status": "new", "replies": []}
            items.append(m)
            return m

        return self._edit(change)

    def remove(self, idea_id):
        self._edit(lambda data: data["ideas"].__setitem__(slice(None), [m for m in data["ideas"] if m["id"] != idea_id]))

    def _find(self, data, idea_id):
        m = next((m for m in data["ideas"] if m["id"] == idea_id), None)
        if not m:
            raise ValueError(f"no idea {idea_id} on the board")
        return m

    def status(self, idea_id, status):
        if status not in IDEA_STATES:
            raise ValueError(f"an idea's status is one of {', '.join(IDEA_STATES)}")

        def change(data):
            m = self._find(data, idea_id)
            m["status"] = status
            return m

        return self._edit(change)

    def reply(self, idea_id, body, sender="claude"):
        """A reply on an idea, Claude's or the user's (whose makes the idea unseen again)."""
        body = text(body).strip()
        if not body:
            raise ValueError("a reply needs some words")

        def change(data):
            m = self._find(data, idea_id)
            r = {"id": next_id(m["replies"], "c"), "from": sender, "text": body, "at": now()}
            m["replies"].append(r)
            if sender != "claude":
                m.pop("seen", None)
            return r

        return self._edit(change)

    def edit(self, idea_id, body, reply_id=None):
        """Your own words on an idea (the idea, or one of your replies), until Claude has been shown them."""
        body = text(body).strip()
        if not body:
            raise ValueError("an idea needs some words")

        def change(data):
            m = self._find(data, idea_id)
            if reply_id:
                r = next((r for r in m["replies"] if r["id"] == reply_id), None)
                if not r or r.get("from") != "you":
                    raise ValueError("that reply isn't yours to change")
                if r.get("seen"):
                    raise ValueError("Claude has read that already")
                r.update(text=body, edited=now())
                return r
            if m.get("shown"):
                raise ValueError("Claude has read that already")
            m.update(text=body, edited=now())
            return m

        return self._edit(change)

    def followup_seen(self):
        """The ids of your replies (in reviews) that Claude has been shown."""
        return {f.get("reply_id") for f in self._data()["followups"] if f.get("seen")}

    def reword_followup(self, reply_id, body):
        def change(data):
            for f in data["followups"]:
                if f.get("reply_id") == reply_id and not f.get("seen"):
                    f["text"] = text(body).strip()

        self._edit(change)

    def followup(self, round_slug, round_title, item_id, idea_id, idea_text, body, reply_id=None):
        """The user's answer, from the Ideas tab, on an idea that lives in a review."""
        body = text(body).strip()
        if not body:
            raise ValueError("a reply needs some words")

        def change(data):
            f = {"id": next_id(data["followups"], "f"), "round": round_slug, "round_title": round_title, "item": item_id,
                 "idea": idea_id, "idea_text": idea_text, "text": body, "reply_id": reply_id, "at": now()}
            data["followups"].append(f)
            return f

        return self._edit(change)

    def unseen(self):
        return [m for m in self.all() if not m.get("seen")]

    def unseen_followups(self):
        return [f for f in self._data()["followups"] if not f.get("seen")]

    def mark_seen(self, ids, followups=()):
        def change(data):
            for m in data["ideas"]:
                if m["id"] in ids:
                    m["seen"] = now()
                    m.setdefault("shown", m["seen"])      # the idea's own words are Claude's now
                    for r in m["replies"]:
                        r.setdefault("seen", m["seen"])
            for f in data["followups"]:
                if f["id"] in followups:
                    f["seen"] = now()

        self._edit(change)


def ideas(rounds, board=None, sent=None):
    """Every idea: the board's first (they belong to no review), then those of every round, newest
    round first, with where it is and Claude's replies."""
    out = []
    sent = sent or {}
    read = board.followup_seen() if board else set()
    # yours until Claude has them: a review's messages until it is handed back
    mine = lambda slug, r: r["from"] == "you" and (slug not in sent or r["at"] > sent[slug]) and r["id"] not in read
    for m in sorted(board.all() if board else [], key=lambda m: m["at"], reverse=True):
        out.append({"round": "", "round_title": "", "item": "", "number": "", "item_text": "", "board": True,
                    "id": m["id"], "text": m["text"], "status": m.get("status", "new"), "at": m["at"],
                    "seen": bool(m.get("seen")), "editable": not m.get("shown"),
                    "replies": [{"id": r["id"], "from": r.get("from", "claude"), "text": r["text"], "at": r["at"],
                                 "editable": r.get("from") == "you" and not r.get("seen")} for r in m["replies"]]})
    for slug in rounds.slugs():
        try:
            doc = rounds.doc(slug)
            state = rounds.state(slug, doc)
        except (OSError, ValueError):
            continue
        places = [(it["id"], it["number"], it["md"]) for it in markdown.all_items(doc)] + [("overall", "", "")]
        for item_id, number, md in places:
            thread = messages(state, item_id)
            for m in thread:
                if m["kind"] != "idea" or not m["text"].strip():
                    continue
                chain, replies = {m["id"]}, []        # the answers on it, and answers to those
                for r in thread:
                    if r.get("to") in chain and r["kind"] != "idea":
                        chain.add(r["id"])
                        replies.append({"id": r["id"], "from": r["from"], "text": r["text"], "at": r["at"], "editable": mine(slug, r)})
                out.append({"round": slug, "round_title": doc["title"], "item": item_id, "number": number,
                            "item_text": md, "id": m["id"], "text": m["text"], "status": m.get("status", "new"),
                            "at": m["at"], "editable": mine(slug, m), "replies": replies})
    return out


# -- events ------------------------------------------------------------------------------------

class Events:
    """What happened on the desk (`events.jsonl`), numbered, and how far Claude has read
    (`.claude.json`)."""

    def __init__(self, folder):
        self.path = Path(folder) / "events.jsonl"
        self.marker = Path(folder) / ".claude.json"
        self.changed = threading.Condition(LOCK)

    def all(self):
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
        return out

    def add(self, kind, **data):
        with self.changed:
            seq = max((e["seq"] for e in self.all()), default=0) + 1
            event = {"seq": seq, "at": now(), "type": kind, **data}
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
            self.changed.notify_all()
            return event

    # Each listener has an owner: "" for the plain case (one session, rounds with no `owner:`),
    # otherwise the name a session listens as (`wait --as NAME`). A hand-back or an answer goes
    # only to its owner's listener; the others never consume it.

    def marks(self):
        return read_json(self.marker, {}) or {}

    def handled(self, owner=""):
        marks = self.marks()
        return marks.get("owners", {}).get(owner, 0) if owner else marks.get("handled", 0)

    def mark(self, seq, owner=""):
        marks = self.marks()
        if owner:
            owners = marks.setdefault("owners", {})
            owners[owner] = max(seq, owners.get(owner, 0))
        else:
            marks["handled"] = max(seq, marks.get("handled", 0))
        write_json(self.marker, marks)

    def waiting(self, kinds=("send", "answer"), owner=""):
        """What this owner's listener hasn't taken in yet: hand-backs and answered questions."""
        after = self.handled(owner)
        return [e for e in self.all() if e["seq"] > after and e["type"] in kinds and e.get("owner", "") == owner]

    def waiting_any(self, kinds=("send", "answer")):
        """What any listener hasn't taken in yet, each against its own owner's mark."""
        marks = self.marks()
        mark = lambda o: marks.get("owners", {}).get(o, 0) if o else marks.get("handled", 0)
        return [e for e in self.all() if e["type"] in kinds and e["seq"] > mark(e.get("owner", ""))]
