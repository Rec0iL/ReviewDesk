"""Review Desk's tests: the checklist parser, the answers on disk, the server's guards and live
updates, and the command. Standard library only:

    python3 -m unittest discover -s tests
"""
import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

# Desks the tests start never show desktop notifications, and list themselves in a folder of
# the tests' own (not the one your desks share).
os.environ["REVIEW_DESK_NO_NOTIFY"] = "1"
_DESKS = tempfile.TemporaryDirectory()
os.environ["REVIEW_DESK_HOME"] = _DESKS.name

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))

from desk import markdown, project, store  # noqa: E402
from desk.store import Board  # noqa: E402
from desk.server import make_server  # noqa: E402

FIXTURES = HERE / "fixtures"
SAMPLE = """---
commit: abc1234
---
# Sample check (about 5 minutes)

Start it like this:

```bash
echo hello
```

## 1. The first part

- [ ] Open the window. {#open}
      Setup: a project with one surface
      Expected: the window shows, **no** errors.
- [ ] Look at ![the picture](files/before.png) and [the doc](docs/a.md).
  - [ ] A step inside it.
- [x] Already fine.

## 2. The second part

- [ ] Something else, with `code`.
"""


def proj_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def git_repo(folder):
    subprocess.run(["git", "init", "-q", str(folder)], check=True)
    return folder


def write_round(root, slug, text=SAMPLE):
    folder = project.ensure(root) / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "checklist.md").write_text(text, encoding="utf-8")
    return folder


class Temp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self):
        self._tmp.cleanup()


# -- the parser ----------------------------------------------------------------------------------

class ParserTest(unittest.TestCase):
    def test_sample(self):
        doc = markdown.parse(SAMPLE, "sample", files="/files/sample")
        self.assertEqual(doc["title"], "Sample check")
        self.assertEqual(doc["about"], "5 minutes")
        self.assertEqual(doc["meta"], {"commit": "abc1234"})
        self.assertEqual([s["title"] for s in doc["sections"]], ["", "1. The first part", "2. The second part"])
        items = markdown.all_items(doc)
        self.assertEqual([i["id"] for i in items], ["open", "1.2", "1.2.1", "1.3", "2.1"])
        self.assertEqual([i["number"] for i in items], ["1.1", "1.2", "1.2.1", "1.3", "2.1"])
        first = items[0]
        self.assertEqual(first["md"], "Open the window.")
        self.assertEqual([f["label"] for f in first["fields"]], ["setup", "expected"])
        self.assertIn("<strong>no</strong>", first["fields"][1]["html"])
        self.assertTrue(items[3]["done"])
        self.assertIn('src="/files/sample/files/before.png"', items[1]["html"])
        self.assertIn('data-path="docs/a.md"', items[1]["html"])
        self.assertEqual(doc["codes"], {"c1": {"lang": "bash", "text": "echo hello"}})
        self.assertTrue(doc["sections"][0]["blocks"][1]["runnable"])

    def test_the_documented_example(self):
        """The example in references/checklist.md reads the way that file says."""
        text = (ROOT / "references" / "checklist.md").read_text(encoding="utf-8")
        example = text.split("````markdown\n", 1)[1].split("\n````", 1)[0]
        doc = markdown.parse(example, "m6a", files="/files/m6a")
        self.assertEqual((doc["title"], doc["about"]), ("M6a: video with sound", "15 minutes"))
        self.assertEqual(doc["meta"]["log"], "~/.local/state/lightgrove/log.txt, target/debug.log")
        items = markdown.all_items(doc)
        self.assertEqual([(i["id"], i["number"]) for i in items],
                         [("pause", "1.1"), ("1.2", "1.2"), ("1.3", "1.3"), ("1.3.1", "1.3.1"), ("1.3.2", "1.3.2"),
                          ("2.1", "2.1"), ("2.2", "2.2")])
        self.assertEqual([f["label"] for f in items[0]["fields"]], ["setup", "do", "expected"])
        self.assertIn('data-path="crates/media/src/transport.rs:120"', items[1]["fields"][0]["html"])
        self.assertTrue(items[-1]["done"])
        self.assertTrue(doc["sections"][0]["blocks"][1]["runnable"])

    def test_videos_play(self):
        html = markdown.parse("## A\n\n- [ ] Watch ![the cut](files/cut.mp4)\n", "v", files="/files/v")
        self.assertIn('<video class="pic" src="/files/v/files/cut.mp4" title="the cut" controls', markdown.all_items(html)[0]["html"])

    def test_names_stay_unique(self):
        doc = markdown.parse("## A\n\n- [ ] one {#x}\n- [ ] two {#x}\n", "n")
        self.assertEqual([i["id"] for i in markdown.all_items(doc)], ["x", "1.2"])

    def test_html_is_escaped(self):
        doc = markdown.parse("## A\n\n- [ ] <script>alert(1)</script> and `<b>`\n", "n")
        html = markdown.all_items(doc)[0]["html"]
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("<code>&lt;b&gt;</code>", html)

    def test_fixtures(self):
        for name, count in (("m5-manual.md", 19), ("p0-manual-checks.md", 19)):
            doc = markdown.parse((FIXTURES / name).read_text(encoding="utf-8"), name)
            items = markdown.all_items(doc)
            self.assertEqual(len(items), count, name)
            self.assertEqual(len({i["id"] for i in items}), count, name)
            self.assertTrue(all(i["md"] for i in items), name)


# -- the project's folder ------------------------------------------------------------------------

class ProjectTest(Temp):
    def test_a_worktree_shares_the_main_checkouts_desk(self):
        main = git_repo(self.root / "main")
        run = lambda *a: subprocess.run(["git", "-C", str(main), *a], check=True, capture_output=True)
        run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "start")
        run("worktree", "add", "-q", str(self.root / "side-task"))
        here = os.getcwd()
        try:
            os.chdir(self.root / "side-task")
            self.assertEqual(project.find_root(), main.resolve())                  # the main checkout's desk
            self.assertEqual(project.default_owner(main.resolve()), "side-task")   # listening as itself
            self.assertEqual(project.find_root(self.root / "side-task"), (self.root / "side-task").resolve())  # said so: its own
            os.chdir(main)
            self.assertEqual((project.find_root(), project.default_owner(main.resolve())), (main.resolve(), ""))
        finally:
            os.chdir(here)

    def test_a_worktrees_name_counts_only_on_its_own_projects_desk(self):
        main = git_repo(self.root / "main")
        run = lambda *a: subprocess.run(["git", "-C", str(main), *a], check=True, capture_output=True)
        run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "start")
        run("worktree", "add", "-q", str(self.root / "side-task"))
        other = self.root / "other"
        other.mkdir()
        project.ensure(other)
        here, kept = os.getcwd(), os.environ.pop("REVIEW_DESK_AS", None)
        try:
            os.chdir(self.root / "side-task")
            self.assertEqual(project.default_owner(main.resolve()), "side-task")   # its own project's desk
            self.assertEqual(project.default_owner(other), "")                     # `--project` names another
            os.environ["REVIEW_DESK_AS"] = ""                                      # said so: the plain case
            self.assertEqual(project.default_owner(main.resolve()), "")
            # the command, from inside the worktree, on another project's desk
            del os.environ["REVIEW_DESK_AS"]
            out = subprocess.run([sys.executable, str(ROOT / "scripts" / "review_desk.py"), "--project", str(other), "status"],
                                 capture_output=True, text=True, timeout=30)
            self.assertIn("listens for rounds with no `owner:`", out.stdout + out.stderr)
            self.assertIn(f"rounds go in {other / '.review'}/<round>/checklist.md", out.stdout)
        finally:
            os.chdir(here)
            os.environ.pop("REVIEW_DESK_AS", None)
            if kept is not None:
                os.environ["REVIEW_DESK_AS"] = kept

    def test_a_worktrees_review_folder_is_the_main_checkouts(self):
        # Claude's file tools in a worktree session may write only inside the worktree: its
        # `.review/` leads to the main checkout's, where the desk looks, and git leaves it alone.
        main = git_repo(self.root / "main")
        run = lambda *a: subprocess.run(["git", "-C", str(main), *a], check=True, capture_output=True)
        run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "start")
        run("worktree", "add", "-q", str(self.root / "side-task"))
        side = self.root / "side-task"
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "review_desk.py"), "status"], cwd=side,
                             capture_output=True, text=True, timeout=30, env={k: v for k, v in os.environ.items() if k != "REVIEW_DESK_AS"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue((side / ".review").is_symlink())
        self.assertEqual((side / ".review").resolve(), (main / ".review").resolve())
        write_round(side, "from-side")
        self.assertTrue((main / ".review" / "from-side" / "checklist.md").is_file())
        for repo in (side, main):
            status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True)
            self.assertEqual(status.stdout.strip(), "", repo)
        # a `.review/` the worktree already has of its own stays as it is
        other = self.root / "other-task"
        run("worktree", "add", "-q", str(other))
        (other / ".review").mkdir()
        subprocess.run([sys.executable, str(ROOT / "scripts" / "review_desk.py"), "status"], cwd=other,
                       capture_output=True, text=True, timeout=30)
        self.assertFalse((other / ".review").is_symlink())

    def test_exclude_once(self):
        git_repo(self.root)
        project.ensure(self.root)
        project.ensure(self.root)
        exclude = (self.root / ".git" / "info" / "exclude").read_text()
        self.assertEqual(exclude.splitlines().count("/.review"), 1)
        (self.root / ".review" / "x.md").write_text("x")
        status = subprocess.run(["git", "-C", str(self.root), "status", "--porcelain"], capture_output=True, text=True)
        self.assertEqual(status.stdout.strip(), "")

    def test_outside_git(self):
        self.assertEqual(project.find_root(self.root), self.root)
        self.assertTrue(project.ensure(self.root).is_dir())

    def test_port_is_stable(self):
        a, b = project.stable_port(self.root), project.stable_port(self.root)
        self.assertEqual(a, b)
        self.assertTrue(project.FIRST_PORT <= a < project.FIRST_PORT + project.PORTS)

    def test_settings(self):
        project.ensure(self.root)
        self.assertEqual(project.settings(self.root)["title"], self.root.name)
        project.save_settings(self.root, title="Grove", accent="#123abc")
        self.assertEqual(project.settings(self.root), {"title": "Grove", "accent": "#123abc"})
        project.save_settings(self.root, accent="red; background: url(x)")
        self.assertEqual(project.settings(self.root)["accent"], project.DEFAULT_ACCENT)

    def test_token_is_kept(self):
        project.ensure(self.root)
        first = project.token(self.root)
        self.assertGreaterEqual(len(first), 32)
        self.assertEqual(project.token(self.root), first)
        self.assertEqual((self.root / ".review" / ".secret").stat().st_mode & 0o777, 0o600)


# -- answers on disk -----------------------------------------------------------------------------

class PageWordsTest(unittest.TestCase):
    def test_answer_and_hand_back_speaks_both_languages(self):
        import re
        words = (ROOT / "assets" / "page" / "i18n.js").read_text(encoding="utf-8")
        en, de = words.split("\n  de: {", 1)
        keys = lambda part: set(re.findall(r'"([a-z][\w.]*)":', part))
        for key in ("hand.answer", "plan.hand.answer", "hand.answer.tip", "ask.next", "ask.hand", "plan.ask.hand"):
            self.assertIn(key, keys(en), key)
            self.assertIn(key, keys(de), key)
        self.assertIn('"hand.answer": "Answer and hand back"', en)
        self.assertIn('"hand.answer": "Beantworten und zurückgeben"', de)
        self.assertEqual(keys(en) - keys(de), set())


class StoreTest(Temp):
    def setUp(self):
        super().setUp()
        write_round(self.root, "sample")
        self.rounds = store.Rounds(self.root / ".review")

    def test_fresh_state(self):
        state = self.rounds.state("sample")
        self.assertEqual(len(state["items"]), 5)
        self.assertEqual(state["items"]["1.3"]["verdict"], "works")  # ticked in the checklist
        self.assertEqual(store.counts(state)["open"], 4)

    def test_answers(self):
        self.rounds.set_item("sample", "open", {"verdict": "change", "severity": "broken", "note": "It crashed."})
        a = self.rounds.state("sample")["items"]["open"]
        self.assertEqual((a["verdict"], a["severity"], a["note"]), ("change", "broken", "It crashed."))
        self.rounds.set_item("sample", "open", {"verdict": "partly"})
        self.assertEqual(self.rounds.state("sample")["items"]["open"]["severity"], "")
        answers = (self.root / ".review" / "sample" / "answers.md").read_text()
        self.assertIn("**Partly works** · 1.1 {#open} · Open the window.", answers)
        self.assertIn("  > It crashed.", answers)

    def test_refusals(self):
        with self.assertRaises(ValueError):
            self.rounds.set_item("sample", "open", {"verdict": "great"})
        with self.assertRaises(ValueError):
            self.rounds.set_item("sample", "nope", {"verdict": "works"})
        with self.assertRaises(ValueError):
            self.rounds.set_item("sample", "open", {"note": "x" * (store.MAX_TEXT + 1)})
        with self.assertRaises(ValueError):
            self.rounds.doc("../etc")

    def test_answers_follow_reworded_numbers(self):
        self.rounds.set_item("sample", "2.1", {"verdict": "works", "note": "fine"})
        moved = SAMPLE.replace("## 2. The second part\n\n", "## 2. The second part\n\n- [ ] A new first step.\n")
        write_round(self.root, "sample", moved)
        state = self.rounds.state("sample")
        self.assertEqual(state["items"]["2.2"]["note"], "fine")
        self.assertEqual(state["items"]["2.1"]["verdict"], "")

    def test_counted_items_are_the_checklists_items(self):
        """What the page counts (the answers) is what it draws (the checklist): the same items in
        the same order, also after a re-test and after Claude rewrote the checklist."""
        def same():
            doc = self.rounds.doc("sample")
            state = self.rounds.state("sample", doc)
            listed = [it["id"] for it in markdown.all_items(doc)]
            self.assertEqual(list(state["items"]), listed)
            c = self.rounds.summary("sample")["counts"]
            self.assertEqual(c["total"], len(listed))
            self.assertEqual(c["open"], sum(not a["verdict"] for a in state["items"].values()))
            return state, c

        state, _ = same()
        for item_id in list(state["items"])[:3]:
            self.rounds.set_item("sample", item_id, {"verdict": "works"})
        self.rounds.retest("sample", [list(state["items"])[0]], "Again.")
        _, before = same()
        moved = SAMPLE.replace("## 2. The second part\n\n", "## 2. The second part\n\n- [ ] A new first step.\n")
        write_round(self.root, "sample", moved)
        _, after = same()
        self.assertEqual((after["total"], after["open"]), (before["total"] + 1, before["open"] + 1))

    def test_hand_back_message_is_kept_and_cleared_by_retest(self):
        self.rounds.set_item("sample", "open", {"verdict": "change"})
        self.rounds.send("sample", "  continue with the plan  ")
        state = self.rounds.state("sample")
        self.assertEqual(state["message"], "continue with the plan")
        self.assertIn("Message with the hand-back: continue with the plan", store.answers_md("sample", self.rounds.doc("sample"), state))
        self.rounds.retest("sample", ["open"], "Fixed.")
        self.assertEqual(self.rounds.state("sample")["message"], "")
        self.rounds.send("sample")
        self.assertNotIn("Message with the hand-back", store.answers_md("sample", self.rounds.doc("sample"), self.rounds.state("sample")))

    def test_plan_round_is_marked_in_header_and_answers(self):
        write_round(self.root, "plan", "---\nkind: plan\n---\n# A plan\n\n## 1. Steps\n\n- [ ] First step {#one}\n")
        doc = self.rounds.doc("plan")
        self.assertEqual(doc["meta"]["kind"], "plan")
        self.assertIn("This is a review of a plan", store.answers_md("plan", doc, self.rounds.state("plan", doc)))
        self.assertNotIn("This is a review of a plan", store.answers_md("sample", self.rounds.doc("sample"), self.rounds.state("sample")))

    def test_board_ideas_belong_to_no_review_and_are_shown_once(self):
        board = Board(project.ensure(self.root))
        first = board.add("  a dark mode for the phone  ")
        self.assertEqual((first["text"], first["status"]), ("a dark mode for the phone", "new"))
        with self.assertRaises(ValueError):
            board.add("   ")
        listed = [i for i in store.ideas(self.rounds, board) if i.get("board")]
        self.assertEqual([(i["id"], i["round"], i["seen"]) for i in listed], [(first["id"], "", False)])
        self.assertEqual([m["id"] for m in board.unseen()], [first["id"]])
        board.mark_seen({first["id"]})
        self.assertEqual(board.unseen(), [])
        board.add("a dark mode, also for the desk", first["id"])      # reworded: Claude reads it again
        self.assertEqual(len(board.unseen()), 1)
        board.status(first["id"], "planned")
        board.reply(first["id"], "Next milestone.")
        got = [i for i in store.ideas(self.rounds, board) if i.get("board")][0]
        self.assertEqual((got["status"], [r["text"] for r in got["replies"]]), ("planned", ["Next milestone."]))
        with self.assertRaises(ValueError):
            board.status("nope", "done")
        board.remove(first["id"])
        self.assertEqual(board.all(), [])

    def test_answering_claude_on_an_idea_reaches_claude_with_the_next_hand_back(self):
        from desk.cli import board_text
        board = Board(project.ensure(self.root))
        mine = board.add("An idea of mine.")
        board.mark_seen({mine["id"]})
        board.reply(mine["id"], "Claude says hello.")
        board.reply(mine["id"], "My answer.", sender="you")
        self.assertEqual([m["id"] for m in board.unseen()], [mine["id"]])        # unseen again
        shown = [i for i in store.ideas(self.rounds, board) if i.get("board")][0]
        self.assertEqual([(r["from"], r["text"]) for r in shown["replies"]], [("claude", "Claude says hello."), ("you", "My answer.")])
        text = board_text(board, mark=True)
        self.assertIn("You: My answer.", text)
        self.assertEqual(board_text(board, mark=True), "")
        # an idea that lives in a review: the answer goes into its thread and to Claude
        self.rounds.message("sample", "open", "idea", "Cache it.", message_id="mi1")
        self.rounds.message("sample", "open", "reply", "Planned.", sender="claude", reply_to="mi1")
        self.rounds.message("sample", "open", "comment", "Thanks, when?", reply_to="mi1", message_id="mr1")
        board.followup("sample", "Sample check", "open", "mi1", "Cache it.", "Thanks, when?")
        got = [i for i in store.ideas(self.rounds, board) if i["id"] == "mi1"][0]
        self.assertEqual([(r["from"], r["text"]) for r in got["replies"]], [("claude", "Planned."), ("you", "Thanks, when?")])
        text = board_text(board, mark=True)
        self.assertIn("the user answers on idea mi1 (sample, item open", text)
        self.assertEqual(board_text(board, mark=True), "")

    def test_a_replaced_picture_gets_a_new_address(self):
        folder = write_round(self.root, "pic", "# P\n\n## 1. A\n\n- [ ] Look ![the bar](files/bar.png) {#look}\n")
        (folder / "files").mkdir(exist_ok=True)
        (folder / "files" / "bar.png").write_bytes(b"one")
        first = self.rounds.doc("pic")["sections"][0]["blocks"][0]["html"]
        self.assertRegex(first, r'src="/files/pic/files/bar\.png\?v=\d+"')
        os.utime(folder / "files" / "bar.png", ns=(1, 1))       # Claude saves a new picture under the same name
        second = self.rounds.doc("pic")["sections"][0]["blocks"][0]["html"]
        self.assertNotEqual(first, second)

    def test_anything_else_becomes_an_item_at_hand_back(self):
        self.rounds.set_overall("sample", "A general impression.")
        self.rounds.add_file("sample", "overall", "shot.png", "screenshot")
        self.rounds.message("sample", "overall", "question", "Is this normal?", message_id="mq9")
        before = store.counts(self.rounds.state("sample"))
        self.rounds.send("sample")
        state = self.rounds.state("sample")
        self.assertEqual((state["overall"]["note"], state["overall"]["files"], state["overall"]["messages"]), ("", [], []))
        doc = self.rounds.doc("sample")
        extra = [x for x in doc["sections"] if x.get("kind") == "else"][0]["blocks"][0]
        self.assertEqual((extra["id"], extra["number"], extra["md"]), ("else1", "A1", "A general impression."))
        a = state["items"]["else1"]
        self.assertEqual((a["files"][0]["name"], a["messages"][0]["text"], a["extra"]), ("shot.png", "Is this normal?", True))
        self.assertEqual(store.counts(state)["open"], before["open"])             # nothing to answer there
        self.assertEqual(store.counts(state)["total"], before["total"])
        md = store.answers_md("sample", doc, state)
        self.assertIn("**Anything else** · A1 {#else1} · A general impression.", md)
        self.assertIn("Is this normal?", md)
        self.rounds.message("sample", "else1", "comment", "More on this.", message_id="mc9")      # a thread like any item's
        self.rounds.set_item("sample", "else1", {"verdict": "works"})
        self.assertEqual(store.counts(self.rounds.state("sample"))["works"], before["works"] + 1)
        # written again after the hand-back, then a re-test: that becomes the next item
        self.rounds.set_overall("sample", "Another thought.")
        self.rounds.retest("sample", ["open"], "Fixed.")
        self.assertEqual(self.rounds.state("sample")["overall"]["note"], "")
        self.assertEqual([e["id"] for e in self.rounds.state("sample")["extras"]], ["else1", "else2"])

    def test_settle_moves_old_leftovers_into_items(self):
        self.rounds.set_overall("sample", "Left in the box.")
        path = self.rounds.path("sample", "state.json")
        raw = json.loads(path.read_text())
        raw.update(sent="2026-01-01 10:00", changed="2026-01-01 10:00")
        path.write_text(json.dumps(raw))
        self.rounds.settle()
        state = self.rounds.state("sample")
        self.assertEqual((state["overall"]["note"], state["items"]["else1"]["text"]), ("", "Left in the box."))
        self.rounds.set_overall("sample", "Typed after the hand-back.")            # changed is later than sent: stays
        self.rounds.settle()
        self.assertEqual(self.rounds.state("sample")["overall"]["note"], "Typed after the hand-back.")

    def test_retest_keeps_history(self):
        self.rounds.set_item("sample", "open", {"verdict": "change", "severity": "annoying", "note": "slow"})
        self.rounds.send("sample")
        self.assertEqual(self.rounds.retest("sample", ["open"], "Faster now."), 2)
        state = self.rounds.state("sample")
        a = state["items"]["open"]
        self.assertEqual((a["verdict"], a["note"]), ("", ""))
        self.assertEqual(a["history"][0]["note"], "slow")
        self.assertEqual(a["retest"]["round"], 2)
        self.assertEqual(a["messages"], [])
        self.assertIsNone(state["sent"])
        self.assertEqual(store.counts(state)["retest"], 1)
        self.rounds.set_item("sample", "open", {"verdict": "works"})
        self.rounds.retest("sample", ["open"], "Faster still.")
        a = self.rounds.state("sample")["items"]["open"]
        self.assertEqual(a["history"][1]["retest"]["note"], "Faster now.")
        self.assertEqual(a["retest"]["note"], "Faster still.")

    def test_messages(self):
        self.rounds.message("sample", "open", "question", "Why?", message_id="mabc")
        self.rounds.message("sample", "open", "question", "Why so slow?", message_id="mabc")
        self.rounds.message("sample", "open", "idea", "Cache it.", message_id="mdef")
        reply = self.rounds.message("sample", "open", "reply", "It decodes twice.", sender="claude", reply_to="mabc")
        thread = self.rounds.state("sample")["items"]["open"]["messages"]
        self.assertEqual([(m["id"], m["text"]) for m in thread],
                         [("mabc", "Why so slow?"), ("mdef", "Cache it."), (reply["id"], "It decodes twice.")])
        self.assertEqual(reply["id"], "c1")
        self.assertEqual(thread[1]["status"], "new")
        with self.assertRaises(ValueError):  # Claude's words are Claude's
            self.rounds.message("sample", "open", "comment", "edited", message_id="c1")
        with self.assertRaises(ValueError):
            self.rounds.message("sample", "open", "question", "x", message_id="../bad")
        self.rounds.idea_status("sample", "open", "mdef", "planned")
        with self.assertRaises(ValueError):
            self.rounds.idea_status("sample", "open", "mabc", "planned")
        self.rounds.message("sample", "overall", "question", "", message_id="mempty")
        answers = (self.root / ".review" / "sample" / "answers.md").read_text()
        self.assertIn("  - You, question mabc: Why so slow?", answers)
        self.assertIn("  - You, idea mdef [planned]: Cache it.", answers)
        self.assertIn("  - Claude, reply c1 (to mabc): It decodes twice.", answers)
        self.assertNotIn("mempty", answers)
        self.rounds.delete_message("sample", "open", "mabc")
        self.rounds.delete_message("sample", "open", "mabc")  # gone already is fine
        with self.assertRaises(ValueError):
            self.rounds.delete_message("sample", "open", "c1")
        self.assertEqual(len(self.rounds.state("sample")["items"]["open"]["messages"]), 2)

    def test_questions(self):
        qs = store.Questions(self.root / ".review")
        asked = qs.add({"title": "Loops", "questions": [
            {"question": "Which modes?", "header": "Modes", "multiSelect": True,
             "options": [{"label": "Loop"}, "Once", {"label": "Ping-pong", "description": "back and forth"}]},
            {"question": "Default?", "options": ["Loop", "Once"]}]})
        self.assertEqual(asked["id"], "q1")
        self.assertEqual(asked["questions"][0]["options"][1], {"label": "Once", "description": ""})
        for bad in ({}, {"questions": []}, {"questions": [{"question": "x", "options": ["only one"]}]},
                    {"questions": [{"question": "x", "options": ["a", "a"]}]},
                    {"questions": [{"question": " ", "options": ["a", "b"]}]}):
            with self.assertRaises(ValueError):
                qs.add(bad)
        with self.assertRaises(ValueError):  # one choice where only one fits
            qs.answer("q1", [{"chosen": ["Loop"]}, {"chosen": ["Loop", "Once"]}])
        with self.assertRaises(ValueError):
            qs.answer("q1", [{"chosen": ["Loop"]}])
        done = qs.answer("q1", [{"chosen": ["Loop", "Ping-pong", "Nonsense"], "note": "both"}, {"other": "ask me"}])
        self.assertEqual(done["answers"][0]["chosen"], ["Loop", "Ping-pong"])
        self.assertEqual(done["answers"][1]["other"], "ask me")
        self.assertEqual(qs.pending(), [])
        with self.assertRaises(ValueError):
            qs.answer("q1", [{}, {}])

    def test_ideas_board(self):
        self.rounds.message("sample", "open", "idea", "Cache it.", message_id="mi1")
        self.rounds.message("sample", "overall", "idea", "A dark theme.", message_id="mi2")
        self.rounds.message("sample", "open", "idea", "", message_id="mi3")
        self.rounds.message("sample", "open", "reply", "Good one, planned for M7.", sender="claude", reply_to="mi1")
        self.rounds.idea_status("sample", "open", "mi1", "planned")
        board = store.ideas(self.rounds)
        self.assertEqual([(i["item"], i["text"], i["status"]) for i in board],
                         [("open", "Cache it.", "planned"), ("overall", "A dark theme.", "new")])
        self.assertEqual(board[0]["replies"][0]["text"], "Good one, planned for M7.")
        self.assertEqual((board[0]["number"], board[0]["round_title"]), ("1.1", "Sample check"))

    def test_retest_with_a_note_each(self):
        self.assertEqual(self.rounds.retest("sample", ["open", "2.1"], "Both fixed.", {"open": "The jump is gone."}), 2)
        items = self.rounds.state("sample")["items"]
        self.assertEqual((items["open"]["retest"]["note"], items["2.1"]["retest"]["note"]), ("The jump is gone.", "Both fixed."))
        with self.assertRaises(ValueError):  # nothing changes when one item is wrong
            self.rounds.retest("sample", ["open", "nope"], "x")
        self.assertEqual(self.rounds.state("sample")["round"], 2)
        with self.assertRaises(ValueError):
            self.rounds.retest("sample", [], "x")

    def test_events(self):
        events = store.Events(self.root / ".review")
        events.add("round", round="sample")
        sent = events.add("send", round="sample")
        self.assertEqual([e["type"] for e in events.waiting()], ["send"])
        events.mark(sent["seq"])
        self.assertEqual(events.waiting(), [])
        events.add("answer", question="q1")
        self.assertEqual(len(events.waiting()), 1)


# -- the server ----------------------------------------------------------------------------------

class ServerBase(Temp):
    """A desk on a free port, with a sample round, for the tests below."""

    def setUp(self):
        super().setUp()
        write_round(self.root, "sample")
        (self.root / ".review" / "sample" / "files").mkdir()
        (self.root / ".review" / "sample" / "files" / "before.png").write_bytes(b"\x89PNG fake")
        (self.root / "secret.txt").write_text("not for the page")
        self.server = make_server(self.root, port=0, quiet=True)
        self.port = self.server.server_port
        self.desk = self.server.desk
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def request(self, method, path, body=None, token=True, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Host": host or f"127.0.0.1:{self.port}"}
        if token:
            headers["X-Desk-Token"] = self.desk.token
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        conn.request(method, path, data, headers)
        r = conn.getresponse()
        payload = r.read()
        conn.close()
        try:
            return r.status, json.loads(payload)
        except ValueError:
            return r.status, payload

    def listen(self):
        """The page's event stream, read in the background."""
        import queue as q
        got = q.Queue()
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", f"/api/events?t={self.desk.token}&c=page1", headers={"Host": f"127.0.0.1:{self.port}"})
        r = conn.getresponse()

        def read():
            try:
                for line in r.fp:
                    if line.startswith(b"data: "):
                        got.put(json.loads(line[6:]))
            except (OSError, ValueError):
                pass

        threading.Thread(target=read, daemon=True).start()
        deadline = time.time() + 3
        while self.desk.connected() == 0 and time.time() < deadline:
            time.sleep(0.05)
        self.addCleanup(conn.close)
        return got

    def upload(self, item, kind, data, name, label=""):
        from urllib.parse import urlencode
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        q = urlencode({"round": "sample", "item": item, "kind": kind, "name": name, "label": label})
        conn.request("POST", f"/api/upload?{q}", data, {"Host": f"127.0.0.1:{self.port}", "X-Desk-Token": self.desk.token})
        r = conn.getresponse()
        out = (r.status, json.loads(r.read()))
        conn.close()
        return out


class ServerTest(ServerBase):
    def test_page_carries_its_token(self):
        status, page = self.request("GET", "/", token=False)
        self.assertEqual(status, 200)
        self.assertIn(self.desk.token.encode(), page)
        self.assertNotIn(b"/*BOOT*/null", page)

    def test_guards(self):
        self.assertEqual(self.request("GET", "/", host="evil.example:80")[0], 403)
        self.assertEqual(self.request("GET", "/api/state", token=False)[0], 403)
        self.assertEqual(self.request("POST", "/api/item", {"round": "sample", "item": "open", "verdict": "works"},
                                      token=False)[0], 403)
        self.assertEqual(self.request("POST", "/api/item", {"round": "sample", "item": "open", "verdict": "works"},
                                      host=f"evil.example:{self.port}")[0], 403)
        self.assertEqual(self.request("GET", "/files/sample/../../secret.txt", token=False)[0], 404)
        self.assertEqual(self.request("GET", "/files/sample/%2e%2e/%2e%2e/secret.txt", token=False)[0], 404)
        self.assertEqual(self.request("GET", "/files/sample/state.json/../../../secret.txt", token=False)[0], 404)

    def test_files(self):
        status, data = self.request("GET", "/files/sample/files/before.png", token=False)
        self.assertEqual((status, data), (200, b"\x89PNG fake"))

    def test_state_and_answers(self):
        status, state = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(state["project"]["title"], self.root.name)
        self.assertRegex(state["version"], r"^[0-9a-f]+$")
        self.assertEqual([r["slug"] for r in state["rounds"]], ["sample"])
        status, _ = self.request("POST", "/api/item", {"round": "sample", "item": "open", "verdict": "works", "note": "ok"})
        self.assertEqual(status, 200)
        status, round_ = self.request("GET", "/api/round/sample")
        self.assertEqual(round_["state"]["items"]["open"]["note"], "ok")
        self.assertEqual(round_["doc"]["title"], "Sample check")
        status, _ = self.request("POST", "/api/item", {"round": "sample", "item": "open", "verdict": "wow"})
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/overall", {"round": "sample", "note": "All good."})
        self.assertEqual(status, 200)
        self.assertIn("All good.", (self.root / ".review" / "sample" / "answers.md").read_text())

    def test_live_updates(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", f"/api/events?t={self.desk.token}", headers={"Host": f"127.0.0.1:{self.port}"})
        r = conn.getresponse()
        self.assertEqual(r.status, 200)
        self.assertEqual(r.fp.readline(), b"retry: 1500\n")
        r.fp.readline()
        deadline = time.time() + 3
        while self.desk.connected() == 0 and time.time() < deadline:
            time.sleep(0.05)
        self.request("POST", "/api/item", {"round": "sample", "item": "open", "verdict": "works", "client": "abc"})
        line = r.fp.readline()
        event = json.loads(line.removeprefix(b"data: "))
        self.assertEqual((event["type"], event["by"], event["item"], event["client"]), ("round", "you", "open", "abc"))
        conn.close()

    def test_hand_back_wakes_wait(self):
        result = {}

        def waiter():
            result["answer"] = self.request("GET", "/api/wait?timeout=10")

        thread = threading.Thread(target=waiter)
        thread.start()
        deadline = time.time() + 5
        while not self.desk.waits.get("") and time.time() < deadline:
            time.sleep(0.05)
        self.assertTrue(self.desk.listening())
        self.assertTrue(self.request("GET", "/api/state")[1]["listening"])
        status, sent = self.request("POST", "/api/send", {"round": "sample", "message": "commit and push"})
        self.assertEqual(status, 200)
        self.assertTrue(sent["listening"])
        thread.join(5)
        status, answer = result["answer"]
        self.assertEqual([(e["type"], e["round"]) for e in answer["events"]], [("send", "sample")])
        self.assertEqual(answer["events"][0]["message"], "commit and push")
        self.assertEqual(self.request("GET", "/api/wait?timeout=0.2")[1]["events"], [])  # once only
        rounds = self.request("GET", "/api/state")[1]["rounds"]
        self.assertTrue(rounds[0]["read"])
        self.assertIsNotNone(rounds[0]["sent"])

    def test_a_wait_whose_caller_went_away_takes_nothing(self):
        # A session stops its `wait` (the process ends): the request it left open must neither
        # count as listening nor swallow the next hand-back.
        import socket
        s = socket.create_connection(("127.0.0.1", self.port))
        s.sendall((f"GET /api/wait?timeout=20 HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                   f"X-Desk-Token: {self.desk.token}\r\n\r\n").encode())
        deadline = time.time() + 5
        while not self.desk.waits.get("") and time.time() < deadline:
            time.sleep(0.05)
        self.assertTrue(self.desk.listening())
        s.close()
        time.sleep(0.3)
        self.request("POST", "/api/send", {"round": "sample"})
        events = self.request("GET", "/api/wait?timeout=1")[1]["events"]
        self.assertEqual([e["round"] for e in events], ["sample"])         # still there for the next `wait`
        deadline = time.time() + 3 + 6      # its own 1 s check, then LISTENING for the `wait` just made
        while self.desk.listening() and time.time() < deadline:
            time.sleep(0.1)
        self.assertFalse(self.desk.listening())

    def test_messages_and_claude(self):
        events = self.listen()
        status, out = self.request("POST", "/api/message", {"round": "sample", "item": "open", "id": "mq1",
                                                            "kind": "question", "text": "Why?", "client": "page1"})
        self.assertEqual((status, out["message"]["id"]), (200, "mq1"))
        status, out = self.request("POST", "/api/claude", {"action": "reply", "round": "sample", "item": "open",
                                                           "text": "Because `x`.", "to": "mq1"})
        self.assertEqual(status, 200)
        seen = []
        deadline = time.time() + 3
        while time.time() < deadline and not any(e.get("what") == "reply" for e in seen):
            try:
                seen.append(events.get(timeout=0.5))
            except Exception:
                pass
        reply = next(e for e in seen if e.get("what") == "reply")
        self.assertEqual((reply["by"], reply["item"], reply["notify"]["body"]), ("claude", "open", "Because `x`."))
        state = self.request("GET", "/api/round/sample")[1]["state"]
        said = state["items"]["open"]["messages"][-1]
        self.assertEqual(said["html"], "Because <code>x</code>.")
        status, out = self.request("POST", "/api/claude", {"action": "retest", "round": "sample", "items": ["open"],
                                                           "text": "Fixed the **jump**."})
        self.assertEqual((status, out["round"]), (200, 2))
        state = self.request("GET", "/api/round/sample")[1]["state"]
        self.assertEqual(state["items"]["open"]["retest"]["html"], "Fixed the <strong>jump</strong>.")
        self.assertEqual(self.request("POST", "/api/claude", {"action": "dance", "round": "sample"})[0], 400)
        status, _ = self.request("POST", "/api/message", {"round": "sample", "item": "open", "id": "mq1", "delete": True})
        self.assertEqual(status, 200)

    def test_idea_reply_endpoint(self):
        self.desk.rounds.message("sample", "open", "idea", "Cache it.", message_id="mi1")
        status, out = self.request("POST", "/api/idea/reply", {"round": "sample", "item": "open", "id": "mi1", "text": "Why not now?", "reply_id": "mr1"})
        self.assertEqual(status, 200)
        self.assertEqual([f["text"] for f in self.desk.board.unseen_followups()], ["Why not now?"])
        self.assertEqual(self.request("POST", "/api/idea/reply", {"round": "sample", "item": "open", "id": "nope", "text": "x", "reply_id": "mr2"})[0], 400)
        self.request("POST", "/api/board/idea", {"id": "mb9", "text": "Mine."})
        self.assertEqual(self.request("POST", "/api/idea/reply", {"round": "", "id": "mb9", "text": "More."})[0], 200)
        got = [i for i in self.request("GET", "/api/ideas")[1]["ideas"] if i["id"] == "mb9"][0]
        self.assertEqual([r["from"] for r in got["replies"]], ["you"])

    def test_your_words_on_an_idea_can_change_until_claude_has_them(self):
        post = lambda **kw: self.request("POST", "/api/idea/edit", kw)
        ideas = lambda: {i["id"]: i for i in self.request("GET", "/api/ideas")[1]["ideas"]}
        # the board: the idea, then a reply of yours
        self.request("POST", "/api/board/idea", {"id": "mb1", "text": "First words."})
        self.assertTrue(ideas()["mb1"]["editable"])
        self.assertEqual(post(round="", item="", id="mb1", target="mb1", text="Better words.")[0], 200)
        self.desk.board.reply("mb1", "Hello.")
        self.request("POST", "/api/idea/reply", {"round": "", "id": "mb1", "text": "Mine."})
        reply = ideas()["mb1"]["replies"][1]
        self.assertEqual((reply["text"], reply["editable"]), ("Mine.", True))
        self.assertFalse(ideas()["mb1"]["replies"][0]["editable"])            # Claude's isn't yours
        self.assertEqual(post(round="", item="", id="mb1", target=reply["id"], text="Mine, reworded.")[0], 200)
        self.desk.board.mark_seen({"mb1"})                                      # Claude was shown it
        self.assertFalse(ideas()["mb1"]["editable"])
        self.assertEqual(post(round="", item="", id="mb1", target="mb1", text="Too late.")[0], 400)
        self.assertEqual(post(round="", item="", id="mb1", target=reply["id"], text="Too late.")[0], 400)
        # an idea in a review: yours until the round is handed back
        self.desk.rounds.message("sample", "open", "idea", "Cache it.", message_id="mi1")
        self.assertTrue(ideas()["mi1"]["editable"])
        self.assertEqual(post(round="sample", item="open", id="mi1", target="mi1", text="Cache it well.")[0], 200)
        self.assertEqual(self.desk.rounds.state("sample")["items"]["open"]["messages"][0]["text"], "Cache it well.")
        self.desk.events.add("send", round="sample")
        self.assertFalse(ideas()["mi1"]["editable"])
        self.assertEqual(post(round="sample", item="open", id="mi1", target="mi1", text="Too late.")[0], 400)

    def test_desktop_notification_only_without_a_page(self):
        log = self.root / "notified.txt"
        fake = self.root / "notify-send"
        fake.write_text(f"#!/bin/sh\nprintf '%s|' \"$@\" >> {log}\necho\n")
        fake.chmod(0o755)
        self.desk.notifier = str(fake)
        self.desk.pages = {"p1": {"visible": True, "notify": False, "at": time.time()}}
        self.desk.claude_did("sample", "reply", title="Claude replied", body="Seen")
        self.desk.pages = {"p1": {"visible": False, "notify": True, "at": time.time()}}
        self.desk.claude_did("sample", "reply", title="Claude replied", body="Seen")
        time.sleep(0.5)
        self.assertFalse(log.exists(), "a page shows it itself")
        self.desk.pages = {"p1": {"visible": False, "notify": False, "at": time.time()}}
        self.desk.claude_did("sample", "reply", title="Claude replied", body="Hidden page")
        self.desk.pages = {}
        self.desk.claude_did("sample", "new", title="Something new to check", body="No page")
        deadline = time.time() + 3
        while time.time() < deadline and (not log.exists() or log.read_text().count("Review Desk") < 2):
            time.sleep(0.05)
        sent = log.read_text()
        self.assertIn("Claude replied|Hidden page|", sent)
        self.assertIn("Something new to check|No page|", sent)

    def test_attachments(self):
        status, out = self.upload("1.2", "screenshot", b"PNGDATA", "shot.png", "the bar")
        self.assertEqual((status, out["file"]["name"]), (200, "1-2-screenshot.png"))
        status, out = self.upload("1.2", "screenshot", b"PNG2", "x.png")
        self.assertEqual(out["file"]["name"], "1-2-screenshot-2.png")
        status, out = self.upload("open", "file", b"<script>alert(1)</script>", "../../evil page.html")
        self.assertEqual(out["file"]["name"], "open-evil-page.html")
        self.assertEqual(self.upload("nope", "file", b"x", "a.txt")[0], 400)
        self.assertEqual(self.upload("open", "virus", b"x", "a.txt")[0], 400)
        self.assertEqual(self.upload("open", "file", b"", "a.txt")[0], 400)
        files = sorted((self.root / ".review" / "sample" / "files").iterdir())
        self.assertNotIn("a.txt", [f.name for f in files])
        state = self.request("GET", "/api/round/sample")[1]["state"]
        self.assertEqual([f["name"] for f in state["items"]["1.2"]["files"]], ["1-2-screenshot.png", "1-2-screenshot-2.png"])
        self.assertEqual(state["items"]["1.2"]["files"][0]["label"], "the bar")
        self.assertIn("  - Screenshot: [1-2-screenshot.png](files/1-2-screenshot.png) the bar",
                      (self.root / ".review" / "sample" / "answers.md").read_text())
        # Served as plain text in a sandbox, never as a page of the desk's own origin.
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/files/sample/files/open-evil-page.html", headers={"Host": f"127.0.0.1:{self.port}"})
        r = conn.getresponse()
        r.read()
        self.assertTrue(r.getheader("Content-Type").startswith("text/plain"))
        self.assertEqual(r.getheader("Content-Security-Policy"), "sandbox")
        # Ranges, for scrubbing recordings.
        conn.request("GET", "/files/sample/files/1-2-screenshot.png",
                     headers={"Host": f"127.0.0.1:{self.port}", "Range": "bytes=2-4"})
        r = conn.getresponse()
        self.assertEqual((r.status, r.read(), r.getheader("Content-Range")), (206, b"GDA", "bytes 2-4/7"))
        conn.close()
        status, _ = self.request("POST", "/api/file/remove", {"round": "sample", "item": "1.2", "name": "1-2-screenshot-2.png"})
        self.assertEqual(status, 200)
        self.assertFalse((self.root / ".review" / "sample" / "files" / "1-2-screenshot-2.png").exists())

    def test_run(self):
        events = self.listen()
        self.assertEqual(self.request("POST", "/api/run", {"round": "sample", "code": "c9"})[0], 400)
        status, out = self.request("POST", "/api/run", {"round": "sample", "code": "c1"})
        self.assertEqual((status, out["run"]["status"]), (200, "running"))
        seen = []
        deadline = time.time() + 5
        while time.time() < deadline and not any(e.get("status") == "done" for e in seen):
            try:
                seen.append(events.get(timeout=0.5))
            except Exception:
                pass
        lines = [line for e in seen if e.get("type") == "run" for line in e.get("lines", [])]
        self.assertEqual(lines, ["hello"])
        self.assertEqual([e["exit"] for e in seen if e.get("status") == "done"], [0])
        runs = self.request("GET", "/api/runs?round=sample")[1]["runs"]
        self.assertEqual([(r["code"], r["lines"]) for r in runs], [("c1", ["hello"])])

    def test_run_stops_everything(self):
        write_round(self.root, "slow", "# Slow\n\n```bash\nsleep 30 & sleep 30; echo never\n```\n\n## A\n\n- [ ] x\n")
        status, out = self.request("POST", "/api/run", {"round": "slow", "code": "c1"})
        run = self.desk.runs.runs[out["run"]["id"]]
        time.sleep(0.3)
        self.request("POST", "/api/run/stop", {"id": out["run"]["id"]})
        deadline = time.time() + 5
        while time.time() < deadline and run["status"] == "running":
            time.sleep(0.05)
        self.assertEqual(run["status"], "stopped")
        alive = subprocess.run(["pgrep", "-g", str(run["proc"].pid)], capture_output=True, text=True).stdout.strip()
        self.assertEqual(alive, "", "the background sleep ended too")

    def test_not_runnable(self):
        write_round(self.root, "py", "# P\n\n```python\nprint(1)\n```\n\n## A\n\n- [ ] x\n")
        status, out = self.request("POST", "/api/run", {"round": "py", "code": "c1"})
        self.assertEqual((status, out["error"]), (400, "only bash and sh blocks run"))

    def test_logs_and_viewer(self):
        (self.root / "app.log").write_text("".join(f"line {n}\n" for n in range(1000)))
        write_round(self.root, "logged", "---\nlog: app.log, missing.log\n---\n# L\n\n## A\n\n- [ ] x\n")
        logs = self.request("GET", "/api/log?round=logged")[1]["logs"]
        self.assertEqual(logs[0]["name"], "app.log")
        self.assertEqual(logs[0]["lines"][-1], "line 999")
        self.assertEqual(len(logs[0]["lines"]), 400)
        self.assertIn("error", logs[1])
        self.assertEqual(self.request("GET", "/api/log?round=sample")[1]["logs"], [])
        status, out = self.request("GET", "/api/source?path=app.log")
        self.assertEqual((status, out["path"]), (200, "app.log"))
        self.assertEqual(self.request("GET", "/api/source?path=../../etc/passwd")[0], 400)
        self.assertEqual(self.request("GET", "/api/source?path=/etc/passwd")[0], 400)
        (self.root / "blob.bin").write_bytes(b"\0\1\2")
        self.assertEqual(self.request("GET", "/api/source?path=blob.bin")[0], 400)
        self.assertEqual(self.request("GET", "/api/commit?ref=HEAD;rm")[0], 400)

    def test_ask_and_answer(self):
        events = self.listen()
        status, out = self.request("POST", "/api/claude", {"action": "ask", "title": "Loops", "questions": [
            {"question": "Default?", "options": ["Loop", "Once"]}]})
        self.assertEqual((status, out["question"]["id"], out["pages"]), (200, "q1", 1))
        self.assertEqual(self.request("POST", "/api/claude", {"action": "ask", "questions": []})[0], 400)
        seen = []
        deadline = time.time() + 3
        while time.time() < deadline and not any(e.get("type") == "questions" for e in seen):
            try:
                seen.append(events.get(timeout=0.5))
            except Exception:
                pass
        ask = next(e for e in seen if e.get("type") == "questions")
        self.assertEqual((ask["what"], ask["notify"]["body"]), ("ask", "Default?"))
        self.assertEqual([q["id"] for q in self.request("GET", "/api/questions")[1]["questions"]], ["q1"])
        status, _ = self.request("POST", "/api/answer", {"id": "q1", "answers": [{"chosen": ["Once"], "note": "for now"}]})
        self.assertEqual(status, 200)
        self.assertEqual(self.request("GET", "/api/questions")[1]["questions"], [])
        got = self.request("GET", "/api/wait?timeout=1")[1]["events"]
        self.assertEqual([(e["type"], e["question"], e["answers"][0]["chosen"]) for e in got], [("answer", "q1", ["Once"])])
        ideas = self.request("GET", "/api/ideas")[1]["ideas"]
        self.assertEqual(ideas, [])
        # asked by a session listening as "side": its answers go to that session only
        self.request("POST", "/api/claude", {"action": "ask", "owner": "side", "questions": [{"question": "Which?", "options": ["A", "B"]}]})
        self.request("POST", "/api/answer", {"id": "q2", "answers": [{"chosen": ["A"]}]})
        self.assertEqual(self.request("GET", "/api/wait?timeout=0.3")[1]["events"], [])
        self.assertEqual([e["question"] for e in self.request("GET", "/api/wait?timeout=0.3&as=side")[1]["events"]], ["q2"])

    def ask(self, question, owner=""):
        return self.request("POST", "/api/claude", {"action": "ask", "owner": owner, "title": question,
                                                    "questions": [{"question": question, "options": ["Yes", "No"]}]})[1]["question"]["id"]

    def test_answer_and_hand_back_reach_wait_together(self):
        mine, other = self.ask("Ship it?"), self.ask("Rename it?", owner="side")
        got = []
        listener = threading.Thread(target=lambda: got.extend(self.desk.wait(5)))
        listener.start()
        time.sleep(0.2)
        status, out = self.request("POST", "/api/send", {"round": "sample", "message": "go on",
                                                         "answers": [{"id": mine, "answers": [{"chosen": ["Yes"], "note": "today"}]}]})
        listener.join(6)
        self.assertEqual((status, out["answered"]), (200, [mine]))
        # one wake-up, both in it: the answer first, then the hand-back that names it
        self.assertEqual([e["type"] for e in got], ["answer", "send"])
        self.assertEqual((got[0]["question"], got[0]["round"], got[0]["answers"][0]["chosen"]), (mine, "sample", ["Yes"]))
        self.assertEqual((got[1]["round"], got[1]["answered"]), ("sample", [mine]))
        self.assertEqual([q["id"] for q in self.request("GET", "/api/questions")[1]["questions"]], [other])

    def test_answer_and_hand_back_is_all_or_nothing(self):
        mine, other = self.ask("Ship it?"), self.ask("Rename it?", owner="side")
        sent_before = self.desk.rounds.state("sample")["sent"]
        bad = [
            [{"id": other, "answers": [{"chosen": ["Yes"]}]}],                 # another session's card
            [{"id": mine, "answers": [{"chosen": ["Yes"]}, {"chosen": ["No"]}]}],  # two answers for one question
            [{"id": mine, "answers": [{"chosen": ["Yes"]}]}, {"id": "q99", "answers": []}],  # one good, one unknown
        ]
        for answers in bad:
            status, out = self.request("POST", "/api/send", {"round": "sample", "answers": answers})
            self.assertEqual(status, 400, answers)
            self.assertEqual(self.desk.rounds.state("sample")["sent"], sent_before)
            self.assertEqual(sorted(q["id"] for q in self.desk.questions.pending()), sorted([mine, other]))
        self.assertIn("another session", self.request("POST", "/api/send", {"round": "sample", "answers": bad[0]})[1]["error"])
        self.assertEqual(self.request("GET", "/api/wait?timeout=0.2")[1]["events"], [])
        # a card answered in the meantime (another tab) is skipped, not an error
        self.request("POST", "/api/answer", {"id": mine, "answers": [{"chosen": ["No"]}]})
        status, out = self.request("POST", "/api/send", {"round": "sample", "answers": [{"id": mine, "answers": [{"chosen": ["Yes"]}]}]})
        self.assertEqual((status, out["answered"]), (200, []))
        self.assertEqual(self.desk.questions.get(mine)["answers"][0]["chosen"], ["No"])

    def test_wait_prints_answers_with_their_hand_back(self):
        import contextlib
        import io
        from desk import cli
        mine = self.ask("Ship it?")
        self.request("POST", "/api/send", {"round": "sample", "answers": [{"id": mine, "answers": [{"chosen": ["Yes"], "note": "today"}]}]})
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            cli.show_events(self.root, self.desk.wait(1))
        out = printed.getvalue()
        self.assertTrue(out.startswith("Results from my review are in, read them."), out[:80])
        self.assertIn("Your answers to my questions, given with this hand-back:", out)
        self.assertIn("- Ship it?\n  → Yes\n  note: today", out)
        self.assertNotIn("Answered at", out)                                   # not twice
        self.assertLess(out.index("Handed back at"), out.index("Your answers to my questions"))

    def test_watcher_sees_claude(self):
        stop = threading.Event()
        seen = []
        q = __import__("queue").Queue()
        with self.desk.clients_lock:
            self.desk.clients.append(q)
        threading.Thread(target=self.desk.watch, args=(stop,), daemon=True).start()
        time.sleep(0.2)
        write_round(self.root, "second", "# Second\n\n## A\n\n- [ ] one\n")
        deadline = time.time() + 4
        while time.time() < deadline and not any(e.get("slug") == "second" for e in seen):
            try:
                seen.append(q.get(timeout=0.5))
            except Exception:
                pass
        stop.set()
        self.assertIn({"type": "round", "slug": "second", "by": "claude", "what": "new", "item": None,
                       "notify": {"title": "Something new to check", "body": "Second"}}, seen)
        self.assertEqual([e["type"] for e in store.Events(self.root / ".review").all()], ["round"])


# -- the phone -----------------------------------------------------------------------------------

class SeenTest(Temp):
    def test_replies_from_before_count_as_seen_and_opening_a_round_clears_new_ones(self):
        write_round(self.root, "sample")
        rounds = store.Rounds(self.root / ".review")
        rounds.message("sample", "open", "reply", "Old one.", sender="claude")
        seen = store.Seen(self.root / ".review")
        seen.start(rounds)
        unseen = lambda: rounds.summary("sample", seen.all().get("sample", set()))["unseen"]
        self.assertEqual(unseen(), 0)                                   # from before: seen
        rounds.message("sample", "open", "reply", "New one.", sender="claude")
        rounds.message("sample", "overall", "reply", "On the whole round.", sender="claude")
        rounds.message("sample", "open", "question", "Mine.", message_id="m1")
        self.assertEqual(unseen(), 2)                                   # yours don't count
        self.assertTrue(seen.mark(rounds, "sample"))
        self.assertEqual(unseen(), 0)
        self.assertFalse(seen.mark(rounds, "sample"))                   # nothing new: nothing written
        rounds.set_overall("sample", "And this.")
        rounds.send("sample")                                           # the overall thread moves into else1
        self.assertIn("else1", rounds.state("sample")["items"])
        self.assertEqual(unseen(), 0)                                   # and stays seen


class PeersTest(Temp):
    """Desks in this process, each in the shared list, one watching the others."""

    def setUp(self):
        super().setUp()
        from desk import peers
        self.peers = peers
        self._poll, peers.POLL = peers.POLL, 2      # quicker to notice a desk that stopped

    def tearDown(self):
        self.peers.POLL = self._poll
        super().tearDown()

    def desk(self, name, title):
        root = self.root / name
        root.mkdir()
        write_round(root, "sample")
        project.save_settings(root, title=title)
        server = make_server(root, port=0, quiet=True)
        server.desk.url = f"http://127.0.0.1:{server.server_port}/"
        threading.Thread(target=server.serve_forever, daemon=True).start()
        project.write_json(root / ".review" / ".runtime.json", {"pid": os.getpid(), "port": server.server_port,
                                                               "token": server.desk.token, "url": server.desk.url})
        self.peers.register(root)
        server.desk.stopped = False

        def stop():
            if not server.desk.stopped:
                server.desk.stopped = True
                server.shutdown()
                server.server_close()
                self.peers.unregister(root)
                (root / ".review" / ".runtime.json").unlink(missing_ok=True)

        server.desk.stop = stop
        self.addCleanup(stop)
        return server.desk

    def watch(self, desk):
        stop = threading.Event()
        self.addCleanup(stop.set)
        threading.Thread(target=desk.peers.run, args=(stop,), daemon=True).start()
        self.assertTrue(self.until(lambda: desk.peers.scanned))

    def stream(self, desk):
        import queue as q
        got = q.Queue()
        conn = http.client.HTTPConnection("127.0.0.1", desk.port, timeout=10)
        conn.request("GET", f"/api/events?t={desk.token}&c=page1", headers={"Host": f"127.0.0.1:{desk.port}"})
        r = conn.getresponse()

        def read():
            try:
                for line in r.fp:
                    if line.startswith(b"data: "):
                        got.put(json.loads(line[6:]))
            except (OSError, ValueError):
                pass

        threading.Thread(target=read, daemon=True).start()
        self.addCleanup(conn.close)
        self.assertTrue(self.until(lambda: desk.local_pages() > 0))
        return got

    def until(self, check, seconds=5):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if check():
                return True
            time.sleep(0.05)
        return False

    def peer_event(self, got, seconds=5):
        import queue as q
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                e = got.get(timeout=max(0.01, deadline - time.time()))
            except q.Empty:
                return None
            if e["type"] == "peer":
                return e
        return None

    def reply(self, desk, text):
        from desk.server import claude_action
        _, notice = claude_action(desk.rounds, {"action": "reply", "round": "sample", "item": "open", "text": text})
        desk.claude_did("sample", **notice)

    def test_desks_see_each_other_and_one_tab_tells_you_about_both(self):
        a, b = self.desk("alpha", "Alpha"), self.desk("beta", "Beta")
        page = self.stream(a)
        self.watch(a)
        self.assertTrue(self.until(lambda: len(a.desks()) == 2))
        here, there = a.desks()
        self.assertEqual((here["title"], here.get("here"), there["title"], there["url"]), ("Alpha", True, "Beta", b.url))
        self.assertTrue(self.until(b.watched))                         # Alpha's tab shows Beta now
        # Claude replies on Beta, which has no tab of its own: Alpha's tab tells you
        self.reply(b, "Fixed.")
        e = self.peer_event(page)
        self.assertIsNotNone(e)
        self.assertEqual((e["title"], e["url"], e["what"], e["slug"], e["item"]), ("Beta", b.url, "reply", "sample", "open"))
        self.assertEqual(e["notify"]["body"], "Fixed.")
        self.assertTrue(self.until(lambda: a.desks()[1]["sessions"][""]["replies"] == 1))
        # Beta gets a tab of its own: that one tells you, Alpha's stays quiet
        self.stream(b)
        self.assertTrue(self.until(lambda: a.desks()[1]["pages"] == 1))
        self.reply(b, "Again.")
        self.assertIsNone(self.peer_event(page, 1.5))

    def test_only_one_tab_tells_you(self):
        a, b, c = self.desk("alpha", "Alpha"), self.desk("beta", "Beta"), self.desk("gamma", "Gamma")
        pages = {d: self.stream(d) for d in (a, c)}
        self.watch(a)
        self.watch(c)
        self.assertTrue(self.until(lambda: len(a.desks()) == 3 and len(c.desks()) == 3
                                   and all(x["pages"] for x in a.desks() if x["title"] == "Gamma")
                                   and all(x["pages"] for x in c.desks() if x["title"] == "Alpha")))
        self.reply(b, "Fixed.")
        lead = min((a, c), key=lambda d: d.port)
        other = c if lead is a else a
        self.assertIsNotNone(self.peer_event(pages[lead]))
        self.assertIsNone(self.peer_event(pages[other], 1.5))

    def test_the_bells_list_has_every_desks_notifications(self):
        a, b = self.desk("alpha", "Alpha"), self.desk("beta", "Beta")
        self.watch(a)
        self.assertTrue(self.until(lambda: len(a.desks()) == 2))
        self.reply(a, "Here first.")
        time.sleep(0.02)
        self.reply(b, "Then there.")
        idle_since = b.last_seen
        got = a.all_history()
        self.assertEqual([(e["title"], e["what"], e["notify"]["body"]) for e in got],
                         [("Beta", "reply", "Then there."), ("Alpha", "reply", "Here first.")])
        self.assertEqual((got[0]["url"], got[0]["slug"], got[0]["item"]), (b.url, "sample", "open"))
        self.assertEqual(b.last_seen, idle_since)                      # asking keeps nobody alive
        # kept on disk: a restarted desk still has it
        self.assertEqual(len(proj_json(b.folder / ".notices.json")), 1)

    def test_asking_another_desk_doesnt_keep_it_alive(self):
        b = self.desk("beta", "Beta")
        before = b.last_seen
        time.sleep(0.05)
        got = self.peers.ask({"port": b.port, "token": b.token}, -1, watching=True)
        self.assertEqual(got["title"], "Beta")
        self.assertEqual(b.last_seen, before)                          # no page, no command: still idle
        self.assertTrue(b.watched())
        from desk.cli import call
        self.assertTrue(call({"port": b.port, "token": b.token}, "GET", "/api/ping")["watched"])

    def test_a_new_desk_is_announced_and_a_stopped_one_leaves(self):
        a = self.desk("alpha", "Alpha")
        page = self.stream(a)
        self.watch(a)
        b = self.desk("beta", "Beta")
        e = self.peer_event(page)
        self.assertIsNotNone(e)
        self.assertEqual((e["what"], e["title"], e["url"]), ("desk", "Beta", b.url))
        b.stop()
        self.assertTrue(self.until(lambda: len(a.desks()) == 1, 10))
        self.assertEqual(self.peers.listing().keys(), {str(a.root)})

    def test_sessions_and_what_waits_in_each(self):
        a = self.desk("alpha", "Alpha")
        write_round(a.root, "side", SAMPLE.replace("commit: abc1234", "commit: abc1234\nowner: side"))
        a.rounds.retest("side", ["open"], "look again")
        a.questions.add({"title": "Q", "owner": "side", "questions": [
            {"question": "Which?", "header": "W", "options": [{"label": "a"}, {"label": "b"}]}]})
        a.events.add("send", round="sample", owner="")
        got = a.sessions()
        self.assertEqual(got["side"], {"questions": 1, "retests": 1, "replies": 0, "claude": 0, "listening": False})
        self.assertEqual(got[""], {"questions": 0, "retests": 0, "replies": 0, "claude": 1, "listening": False})

    def test_the_phone_hears_nothing_of_other_desks(self):
        import queue as q
        a = self.desk("alpha", "Alpha")
        mine, phone_page = q.Queue(), q.Queue()
        with a.clients_lock:
            a.clients.extend([mine, phone_page])
            a.phone_clients.append(phone_page)
        for kind in ("peer", "desks", "round"):
            a.broadcast(type=kind)
        self.assertEqual([mine.get_nowait()["type"] for _ in range(3)], ["peer", "desks", "round"])
        self.assertEqual(phone_page.get_nowait()["type"], "round")
        self.assertTrue(phone_page.empty())


class QrTest(unittest.TestCase):
    def test_reads_back(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("OpenCV reads the codes back; it isn't here")
        from desk import qr
        for length in (5, 40, 75, 100, 130, 170, 210):
            text = ("http://192.168.1.20:41234/?p=" + "Zq8_-Kx3" * 40)[:length]
            rows = qr.encode(text)
            n = len(rows)
            img = np.full(((n + 8) * 6, (n + 8) * 6), 255, np.uint8)
            for y, row in enumerate(rows):
                for x, dark in enumerate(row):
                    if dark:
                        img[(y + 4) * 6:(y + 5) * 6, (x + 4) * 6:(x + 5) * 6] = 0
            self.assertEqual(cv2.QRCodeDetector().detectAndDecode(img)[0], text, f"{length} characters")
        self.assertTrue(qr.svg("hi").startswith("<svg"))
        with self.assertRaises(ValueError):
            qr.encode("x" * 300)

    def test_home_network(self):
        from desk import phone
        self.assertTrue(phone.home_network("192.168.1.20"))
        self.assertTrue(phone.home_network("10.1.2.3"))
        self.assertFalse(phone.home_network("127.0.0.1"))
        self.assertFalse(phone.home_network("8.8.8.8"))
        self.assertFalse(phone.home_network("169.254.1.1"))
        self.assertFalse(phone.home_network("nonsense"))


class PhoneTest(ServerBase):
    def setUp(self):
        from desk import phone
        ip = phone.lan_address()
        if not ip or not phone.home_network(ip):
            self.skipTest("no home network here")
        super().setUp()

    def at_phone(self, method, path, body=None, host=None, cookie=None, token=None):
        p = self.desk.phone
        conn = http.client.HTTPConnection(p["ip"], p["port"], timeout=5)
        headers = {"Host": host or f"{p['ip']}:{p['port']}"}
        if cookie:
            headers["Cookie"] = cookie
        if token:
            headers["X-Desk-Token"] = token
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        conn.request(method, path, data, headers)
        r = conn.getresponse()
        out = (r.status, r.read(), r.getheader("Set-Cookie"))
        conn.close()
        return out

    def test_phone_way_in(self):
        status, on = self.request("POST", "/api/phone", {"on": True})
        self.addCleanup(self.desk.phone_off)
        self.assertEqual(status, 200)
        self.assertTrue(on["on"])
        self.assertTrue(on["qr"].startswith("<svg"))
        secret = self.desk.phone["token"]
        self.assertNotEqual(secret, self.desk.token)
        self.assertEqual(on["url"], f"http://{on['ip']}:{on['port']}/?p={secret}")
        # Without the code, or under another name, nothing.
        self.assertEqual(self.at_phone("GET", "/")[0], 403)
        self.assertEqual(self.at_phone("GET", "/?p=wrong")[0], 403)
        self.assertEqual(self.at_phone("GET", f"/?p={secret}", host="evil.example")[0], 403)
        self.assertEqual(self.at_phone("GET", "/api/state", token=self.desk.token)[0], 403)
        self.assertEqual(self.at_phone("GET", "/api/ping")[0], 403)
        # With it: the page (not this computer's), a cookie for pictures and files.
        status, page, cookie = self.at_phone("GET", f"/?p={secret}")
        self.assertEqual(status, 200)
        self.assertIn(b'"local": false', page)
        self.assertIn(secret.encode(), page)
        self.assertNotIn(self.desk.token.encode(), page)
        jar = cookie.split(";")[0]
        self.assertIn("HttpOnly", cookie)
        self.assertEqual(self.at_phone("GET", "/api/state", cookie=jar)[0], 200)
        self.assertEqual(self.at_phone("GET", "/files/sample/files/before.png", cookie=jar)[0], 200)
        self.assertEqual(self.at_phone("GET", "/files/sample/files/before.png")[0], 403)
        status, _, _ = self.at_phone("POST", "/api/item", {"round": "sample", "item": "open", "verdict": "works"}, token=secret)
        self.assertEqual(status, 200)
        # Never commands, never the switch.
        self.assertEqual(self.at_phone("POST", "/api/run", {"round": "sample", "code": "c1"}, token=secret)[0], 400)
        self.assertEqual(self.at_phone("POST", "/api/phone", {"on": False}, token=secret)[0], 400)
        self.assertEqual(self.at_phone("POST", "/api/quit", {}, token=secret)[0], 400)
        self.assertEqual(self.at_phone("GET", "/api/phone", token=secret)[0], 403)
        # Off: the door is shut.
        status, off = self.request("POST", "/api/phone", {"on": False})
        self.assertEqual((status, off), (200, {"on": False}))
        time.sleep(0.8)
        with self.assertRaises(OSError):
            conn = http.client.HTTPConnection(on["ip"], on["port"], timeout=2)
            conn.request("GET", "/", headers={"Host": f"{on['ip']}:{on['port']}"})
            conn.getresponse()


# -- updates -----------------------------------------------------------------------------------

class UpdateTest(Temp):
    """A stand-in for GitHub (a bare repo), a clone as the installed skill, then a newer commit."""

    def setUp(self):
        super().setUp()
        from desk import updates
        self.updates = updates
        run = lambda *a, cwd=None: subprocess.run(a, cwd=cwd, check=True, capture_output=True, text=True)
        self.run = run
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        self._env = {k: os.environ.get(k) for k in [*env, "XDG_CACHE_HOME", "REVIEW_DESK_NO_UPDATE_CHECK"]}
        os.environ.update(env)
        os.environ["XDG_CACHE_HOME"] = str(self.root / "cache")
        os.environ.pop("REVIEW_DESK_NO_UPDATE_CHECK", None)
        self.hub = self.root / "hub.git"
        run("git", "init", "-q", "--bare", "-b", "main", str(self.hub))
        self.author = self.root / "author"
        run("git", "clone", "-q", str(self.hub), str(self.author))
        self.commit("first")
        self.skill = self.root / "skill"
        run("git", "clone", "-q", str(self.hub), str(self.skill))
        self._repo = updates.REPO
        updates.REPO = self.skill

    def tearDown(self):
        if self.updates.fetching:
            self.updates.fetching.wait(10)
            self.updates.fetching = None
        self.updates.REPO = self._repo
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        super().tearDown()

    def commit(self, text):
        (self.author / "file.txt").write_text(text)
        self.run("git", "add", "file.txt", cwd=self.author)
        self.run("git", "commit", "-q", "-m", text, cwd=self.author)
        self.run("git", "push", "-q", "origin", "main", cwd=self.author)

    def test_quiet_when_up_to_date(self):
        self.assertIsNone(self.updates.notice())

    def test_notice_after_the_background_fetch(self):
        self.commit("second")
        self.commit("third")
        self.assertIsNone(self.updates.notice())  # this session starts the fetch, doesn't wait for it
        deadline = time.time() + 10
        while time.time() < deadline and self.updates.behind() == 0:
            time.sleep(0.1)
        said = self.updates.notice()  # the next session
        self.assertIn("Review Desk has an update (2 new commits)", said)
        self.assertFalse(self.updates.fetch_soon(), "at most one fetch a day")
        self.assertTrue(self.updates.fetch_soon(now=time.time() + 25 * 3600))
        os.environ["REVIEW_DESK_NO_UPDATE_CHECK"] = "1"
        self.assertIsNone(self.updates.notice())

    def test_update_pulls_and_refuses_local_changes(self):
        self.commit("second")
        ok, said = self.updates.update()
        self.assertTrue(ok, said)
        self.assertIn("Review Desk updated", said)
        self.assertIn("second", said)
        self.assertEqual((self.skill / "file.txt").read_text(), "second")
        ok, said = self.updates.update()
        self.assertEqual((ok, said), (True, "Review Desk is up to date."))
        (self.skill / "file.txt").write_text("mine")
        self.commit("third")
        ok, said = self.updates.update()
        self.assertFalse(ok)
        self.assertIn("local changes", said)
        self.assertEqual((self.skill / "file.txt").read_text(), "mine")

    def test_no_upstream(self):
        lone = self.root / "lone"
        self.run("git", "init", "-q", str(lone))
        self.updates.REPO = lone
        self.assertIsNone(self.updates.notice())
        self.assertFalse(self.updates.fetch_soon())
        self.assertFalse(self.updates.update()[0])


# -- the command ---------------------------------------------------------------------------------

class CommandTest(Temp):
    def run_desk(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "review_desk.py"), "--project", str(self.root), *args],
                              capture_output=True, text=True, timeout=30)

    def test_start_status_stop(self):
        git_repo(self.root)
        write_round(self.root, "sample")
        out = self.run_desk("start", "--no-open")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Review Desk for", out.stdout)
        try:
            runtime = project.runtime(self.root)
            self.assertIsNotNone(runtime)
            self.assertEqual(runtime["port"], project.stable_port(self.root))
            again = self.run_desk("start", "--no-open")
            self.assertIn("already running", again.stdout)
            status = self.run_desk("status")
            self.assertIn("sample: Sample check · round 1", status.stdout)
            self.assertEqual(self.run_desk("status", "--hook").stdout, "")
        finally:
            self.assertIn("stopped", self.run_desk("stop").stdout)
        deadline = time.time() + 5
        while time.time() < deadline and project.runtime(self.root):
            time.sleep(0.1)
        self.assertIsNone(project.runtime(self.root))

    def test_wait_returns_on_hand_back(self):
        write_round(self.root, "sample")
        waiter = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "review_desk.py"), "--project", str(self.root),
                                   "wait", "--timeout", "20"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.time() + 10
            while time.time() < deadline and not (project.runtime(self.root) and self.listening()):
                time.sleep(0.2)
            rt = project.runtime(self.root)
            self.assertIsNotNone(rt, "wait starts the desk")
            from desk.cli import call
            call(rt, "POST", "/api/item", {"round": "sample", "item": "open", "verdict": "works", "note": "Fine here."})
            call(rt, "POST", "/api/board/idea", {"id": "mb1", "text": "Export the answers as PDF."})
            call(rt, "POST", "/api/send", {"round": "sample", "message": "commit and push"})
            out, err = waiter.communicate(timeout=15)
            self.assertEqual(waiter.returncode, 0, err)
            self.assertIn("Handed back at", out)
            self.assertTrue(out.startswith("Results from my review are in, read them.\ncommit and push\n"), out[:120])
            self.assertIn("**Works** · 1.1 {#open} · Open the window.", out)
            self.assertIn("  > Fine here.", out)
            self.assertIn("From the Ideas tab", out)
            self.assertIn("- mb1 [new]", out)
            self.assertIn("Export the answers as PDF.", out)
            self.assertIn("review-desk wait", out)
            self.assertIn("No new ideas", self.run_desk("ideas").stdout)      # shown once
            self.assertIn("mb1", self.run_desk("ideas", "--all").stdout)
            self.run_desk("reply", "board", "-", "On the list.", "--to", "mb1")
            self.run_desk("idea", "board", "-", "mb1", "planned")
            shown = [i for i in call(rt, "GET", "/api/ideas")["ideas"] if i.get("board")][0]
            self.assertEqual((shown["status"], shown["replies"][0]["text"], shown["seen"]), ("planned", "On the list.", True))
        finally:
            waiter.kill()
            self.run_desk("stop")

    def test_a_hand_back_goes_only_to_the_rounds_owner(self):
        write_round(self.root, "round-a", SAMPLE.replace("commit: abc1234", "commit: abc1234\nowner: a"))
        write_round(self.root, "round-b", SAMPLE.replace("commit: abc1234", "commit: abc1234\nowner: b"))
        self.run_desk("start", "--no-open")
        waiter = lambda *a: subprocess.Popen([sys.executable, str(ROOT / "scripts" / "review_desk.py"), "--project", str(self.root),
                                             "wait", *a], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                            env={**os.environ, "REVIEW_DESK_AS": ""})
        a, b, plain = waiter("--as", "a", "--timeout", "6"), waiter("--as", "b", "--timeout", "20"), waiter("--timeout", "6")
        try:
            from desk.cli import call
            rt = project.runtime(self.root)
            deadline = time.time() + 10
            while time.time() < deadline and len(call(rt, "GET", "/api/state")["listeners"]) < 3:
                time.sleep(0.2)
            self.assertEqual(sorted(call(rt, "GET", "/api/state")["listeners"]), ["", "a", "b"])
            call(rt, "POST", "/api/send", {"round": "round-b"})
            out_b, _ = b.communicate(timeout=15)
            self.assertIn("Handed back at", out_b)
            self.assertIn("round-b", out_b)
            self.assertIn("review-desk wait --as b", out_b)
            out_a, _ = a.communicate(timeout=15)
            out_plain, _ = plain.communicate(timeout=15)
            self.assertNotIn("Handed back", out_a)                 # A's keeps waiting (until its timeout)
            self.assertNotIn("Handed back", out_plain)             # and the plain listener never takes it
            # nobody listens as a: A's hand-back stays queued for A, untouched by the others
            call(rt, "POST", "/api/send", {"round": "round-a"})
            self.assertEqual(call(rt, "GET", "/api/wait?timeout=0.3")["events"], [])
            self.assertEqual(call(rt, "GET", "/api/wait?timeout=0.3&as=b")["events"], [])
            got = call(rt, "GET", "/api/wait?timeout=0.3&as=a")["events"]
            self.assertEqual([(e["round"], e["owner"]) for e in got], [("round-a", "a")])
        finally:
            for w in (a, b, plain):
                w.kill()
            self.run_desk("stop")

    def test_a_wait_outlives_a_restart_of_the_desk(self):
        write_round(self.root, "sample")
        self.run_desk("start", "--no-open")
        waiter = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "review_desk.py"), "--project", str(self.root),
                                   "wait", "--as", "", "--timeout", "40"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.time() + 10
            while time.time() < deadline and not self.listening():
                time.sleep(0.2)
            self.assertTrue(self.listening())
            self.run_desk("stop")
            deadline = time.time() + 5
            while time.time() < deadline and project.runtime(self.root):
                time.sleep(0.1)
            self.run_desk("start", "--no-open")
            deadline = time.time() + 15
            while time.time() < deadline and not self.listening():   # the `wait` finds the new desk
                time.sleep(0.2)
            self.assertTrue(self.listening())
            from desk.cli import call
            call(project.runtime(self.root), "POST", "/api/send", {"round": "sample"})
            out, err = waiter.communicate(timeout=15)
            self.assertIn("Handed back at", out, err)
        finally:
            waiter.kill()
            self.run_desk("stop")

    def listening(self):
        from desk.cli import call
        try:
            return call(project.runtime(self.root), "GET", "/api/state")["listening"]
        except Exception:
            return False

    def test_claude_without_a_desk(self):
        write_round(self.root, "sample")
        out = self.run_desk("reply", "sample", "open", "On it.")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("replied (c1)", out.stdout)
        out = self.run_desk("retest", "sample", "open", "1.2", "--note", "Both fixed.")
        self.assertIn("2 item(s) back for another look, round 2", out.stdout)
        answers = self.run_desk("answers", "sample").stdout
        self.assertIn("  - Re-test (round 2): Both fixed.", answers)
        self.assertIn("Claude, reply c1: On it.", answers)
        each = subprocess.run([sys.executable, str(ROOT / "scripts" / "review_desk.py"), "--project", str(self.root),
                               "retest", "sample", "--each", "-"], input=json.dumps({"open": "Faster.", "2.1": "Kept."}),
                              capture_output=True, text=True, timeout=30)
        self.assertIn("2 item(s) back for another look, round 3", each.stdout)
        self.assertIn("  - Re-test (round 3): Kept.", self.run_desk("answers", "sample").stdout)
        bad = self.run_desk("reply", "sample", "nope", "x")
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("no item 'nope'", bad.stderr)
        self.assertIsNone(project.runtime(self.root))

    def test_ask_then_answers_through_wait(self):
        write_round(self.root, "sample")
        questions = json.dumps({"title": "Speed", "questions": [
            {"question": "Highest speed?", "header": "Speed", "options": [{"label": "2x"}, {"label": "4x"}]}]})
        try:
            out = subprocess.run([sys.executable, str(ROOT / "scripts" / "review_desk.py"), "--project", str(self.root), "ask", "-"],
                                 input=questions, capture_output=True, text=True, timeout=30)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("asked q1 (1 question(s))", out.stdout)
            self.assertIn("No page is open", out.stdout)
            from desk.cli import call
            call(project.runtime(self.root), "POST", "/api/answer", {"id": "q1", "answers": [{"chosen": ["4x"], "other": "", "note": "if it stays smooth"}]})
            out = self.run_desk("wait", "--timeout", "5")
            self.assertIn("Answered at", out.stdout)
            self.assertIn("- Highest speed?\n  → 4x\n  note: if it stays smooth", out.stdout)
        finally:
            self.run_desk("stop")

    def test_hook_speaks_only_when_answers_wait(self):
        write_round(self.root, "sample")
        store.Events(self.root / ".review").add("send", round="sample")
        out = self.run_desk("status", "--hook")
        self.assertIn("answers waiting", out.stdout)
        self.assertIn("(sample)", out.stdout)


if __name__ == "__main__":
    unittest.main()
