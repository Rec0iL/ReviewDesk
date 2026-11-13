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
        self.assertEqual(doc["codes"], {"c1": "echo hello"})
        self.assertTrue(doc["sections"][0]["blocks"][1]["runnable"])

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
        self.assertEqual(a["messages"][-1]["from"], "claude")
        self.assertIsNone(state["sent"])
        self.assertEqual(store.counts(state)["retest"], 1)

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

class ServerTest(Temp):
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
        self.assertIn({"type": "round", "slug": "second", "by": "claude", "new": True}, seen)
        self.assertEqual([e["type"] for e in store.Events(self.root / ".review").all()], ["round"])


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

    def test_hook_speaks_only_when_answers_wait(self):
        write_round(self.root, "sample")
        store.Events(self.root / ".review").add("send", round="sample")
        out = self.run_desk("status", "--hook")
        self.assertIn("answers waiting", out.stdout)
        self.assertIn("(sample)", out.stdout)


if __name__ == "__main__":
    unittest.main()
