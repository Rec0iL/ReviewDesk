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

# Desks the tests start never show desktop notifications.
os.environ["REVIEW_DESK_NO_NOTIFY"] = "1"

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))

from desk import markdown, project, store  # noqa: E402
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
    def test_exclude_once(self):
        git_repo(self.root)
        project.ensure(self.root)
        project.ensure(self.root)
        exclude = (self.root / ".git" / "info" / "exclude").read_text()
        self.assertEqual(exclude.count("/.review/"), 1)
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
        while self.desk.waits == 0 and time.time() < deadline:
            time.sleep(0.05)
        self.assertTrue(self.desk.listening())
        self.assertTrue(self.request("GET", "/api/state")[1]["listening"])
        status, sent = self.request("POST", "/api/send", {"round": "sample"})
        self.assertEqual(status, 200)
        self.assertTrue(sent["listening"])
        thread.join(5)
        status, answer = result["answer"]
        self.assertEqual([(e["type"], e["round"]) for e in answer["events"]], [("send", "sample")])
        self.assertEqual(self.request("GET", "/api/wait?timeout=0.2")[1]["events"], [])  # once only
        rounds = self.request("GET", "/api/state")[1]["rounds"]
        self.assertTrue(rounds[0]["read"])
        self.assertIsNotNone(rounds[0]["sent"])

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
            call(rt, "POST", "/api/send", {"round": "sample"})
            out, err = waiter.communicate(timeout=15)
            self.assertEqual(waiter.returncode, 0, err)
            self.assertIn("Handed back at", out)
            self.assertIn("**Works** · 1.1 {#open} · Open the window.", out)
            self.assertIn("  > Fine here.", out)
            self.assertIn("review-desk wait", out)
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
