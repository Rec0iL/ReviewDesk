"""`review-desk`: the command Claude (and you) run. It works on the project around the current
folder (the git repository, or the folder itself), or the one `--project` names.

    start [--no-open]      the page in the background (opened once in your browser)
    stop | open            stop it | show it in the browser
    status [--hook]        rounds, answers waiting, where you are (--hook: one line, only when
                           answers wait, for a session-start hook)
    wait [--timeout S]     returns when you hand a round back (run it in the background); prints
                           the answers
    answers ROUND          a round's answers as they are now
    reply ROUND ITEM TEXT [--to MESSAGE]
                           Claude's reply in an item's thread (ITEM `overall` for the round's own)
    retest ROUND ITEM... [--note TEXT]
                           items back for another look, with what changed
    idea ROUND ITEM MESSAGE STATUS
                           an idea planned, done, declined (or new)
    ask [FILE|-] [--wait]  question cards on the page (JSON like the chat's question tool:
                           {"title", "questions": [{"question", "header", "multiSelect",
                           "options": [{"label", "description"}]}]}); the answers come
                           through `wait` (or right away with --wait)
    config [--title T] [--accent #rrggbb]
    selftest               checks that the desk works on this computer
    serve                  the server itself (what start runs in the background)
"""
import argparse
import http.client
import json
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from . import project as proj
from .store import Events, Rounds

SCRIPT = Path(__file__).resolve().parent.parent / "review_desk.py"


# -- talking to a running desk --------------------------------------------------------------------

def call(runtime, method, path, body=None, timeout=10):
    """A request to the running desk: its JSON answer, or an OSError when it doesn't answer."""
    conn = http.client.HTTPConnection("127.0.0.1", runtime["port"], timeout=timeout)
    try:
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Host": f"127.0.0.1:{runtime['port']}", "X-Desk-Token": runtime.get("token", "")}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        conn.request(method, path, payload, headers)
        r = conn.getresponse()
        data = r.read()
        answer = json.loads(data or b"{}") if r.getheader("Content-Type", "").startswith("application/json") else {}
        if r.status != 200:
            raise RuntimeError(answer.get("error") or f"{r.status} {r.reason}")
        return answer
    finally:
        conn.close()


def running(root):
    """The running desk's runtime info, if it is this project's and answers."""
    rt = proj.runtime(root)
    if not rt:
        return None
    try:
        ping = call(rt, "GET", "/api/ping", timeout=3)
    except (OSError, RuntimeError, ValueError):
        return None
    return rt | {"pages": ping.get("pages", 0)} if ping.get("project") == str(root) else None


def pages(root):
    """How many pages are connected to the desk (0 when it doesn't answer)."""
    return (running(root) or {}).get("pages", 0)


def start(root, open_browser=True, quiet=False):
    """The desk running for `root`: the one already running, or a new one in the background.
    A new one opens in the browser unless a tab already open there comes back to it."""
    proj.ensure(root)
    rt = running(root)
    fresh = rt is None
    if fresh:
        log = open(proj.review_dir(root) / ".desk.log", "a", encoding="utf-8")
        subprocess.Popen([sys.executable, str(SCRIPT), "--project", str(root), "serve"], cwd=root,
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        deadline = time.time() + 8
        while time.time() < deadline and not (rt := running(root)):
            time.sleep(0.15)
        if not rt:
            sys.exit(f"the desk didn't start; see {proj.review_dir(root) / '.desk.log'}")
    if open_browser and fresh:
        # A tab still open from before finds the desk again by itself within a few seconds.
        deadline = time.time() + 3.5
        while time.time() < deadline and pages(root) == 0:
            time.sleep(0.25)
        if pages(root) == 0:
            webbrowser.open(rt["url"])
    if not quiet:
        print(f"Review Desk for {root.name}: {rt['url']}" + ("" if fresh else " (already running)"))
    return rt


def stop(root):
    rt = running(root)
    if not rt:
        print("not running")
        return
    call(rt, "POST", "/api/quit", {})
    print("stopped")


def status(root, hook=False):
    folder = proj.review_dir(root)
    if not folder.is_dir():
        if not hook:
            print(f"no desk in {root} yet (review-desk start makes one)")
        return
    events = Events(folder)
    waiting = events.waiting()
    if hook:
        # One line for a new session, only when something waits.
        if waiting:
            what = ", ".join(sorted({e.get("round") or e.get("question", "?") for e in waiting}))
            print(f"Review Desk: answers waiting in {root.name} ({what}). "
                  f"Run `review-desk wait` (it returns at once) and read them.")
        return
    rt = running(root)
    print(f"{proj.settings(root)['title']} · " + (f"running on {rt['url']}, {rt['pages']} page(s) open" if rt else "not running"))
    rounds = Rounds(folder)
    for slug in rounds.slugs():
        try:
            s = rounds.summary(slug)
        except (OSError, ValueError) as e:
            print(f"  {slug}: {e}")
            continue
        c = s["counts"]
        sent = f"handed back {s['sent']}" if s["sent"] else "not handed back"
        print(f"  {slug}: {s['title']} · round {s['round']} · {sent} · {c['works']} work, {c['partly']} partly, "
              f"{c['change']} need a change, {c['blocked']} can't test, {c['skipped']} skipped, {c['open']} open")
    if rt:
        try:
            presence = call(rt, "GET", "/api/state").get("presence")
        except (OSError, RuntimeError, ValueError):
            presence = None
        if presence:
            print(f"  you are on {presence.get('round')} · {presence.get('item') or 'the round'} (since {presence.get('at')})")
    for e in waiting:
        print(f"  waiting for Claude: {e['type']} {e.get('round') or e.get('question', '')} at {e['at']}")


def show_events(root, events):
    """What `wait` prints: each hand-back with its answers, each answered question."""
    folder = proj.review_dir(root)
    rounds = Rounds(folder)
    shown = set()
    for e in events:
        if e["type"] == "send" and e.get("round") not in shown:
            slug = e["round"]
            shown.add(slug)
            print(f"Handed back at {e['at']}: {slug}. The answers ({folder / slug / 'answers.md'}):\n")
            try:
                print(answers_text(rounds, slug))
            except (OSError, ValueError) as err:
                print(f"(couldn't read them: {err})")
            print()
        elif e["type"] == "answer":
            print(f"Answered at {e['at']}: {e.get('title') or e.get('question', '?')} ({e.get('question')})")
            for a in e.get("answers", []):
                picked = ", ".join(a.get("chosen") or []) or "(none of the options)"
                print(f"- {a['question']}\n  → {picked}")
                if a.get("other", "").strip():
                    print(f"  → in their own words: {a['other'].strip()}")
                if a.get("note", "").strip():
                    print(f"  note: {a['note'].strip()}")
            print()
    print("Run `review-desk wait` again in the background to hear the next hand-back.")


def answers_text(rounds, slug):
    """A round's answers.md, written fresh from its state."""
    from .store import answers_md
    doc = rounds.doc(slug)
    return answers_md(slug, doc, rounds.state(slug, doc))


def wait(root, timeout=None):
    """Waits for a hand-back. The desk starts if it isn't running (without opening a page)."""
    rt = start(root, open_browser=False, quiet=True)
    deadline = None if timeout is None else time.time() + timeout
    misses = 0
    while deadline is None or time.time() < deadline:
        step = 25 if deadline is None else max(0.0, min(25, deadline - time.time()))
        try:
            events = call(rt, "GET", f"/api/wait?timeout={step:.1f}", timeout=step + 15)["events"]
            misses = 0
        except (OSError, RuntimeError, ValueError):
            # The desk went away: maybe restarted on purpose. Look a little longer, then stop.
            misses += 1
            if misses > 12:
                print("The desk stopped, so nothing can be handed back. `review-desk start` starts it again.")
                return
            time.sleep(5)
            rt = running(root) or rt
            continue
        if events:
            show_events(root, events)
            return
    print("Nothing handed back yet. Run `review-desk wait` again to keep listening.")


def claude(root, body):
    """One of Claude's actions: through the desk when it runs (the page updates and tells you),
    straight into the files otherwise."""
    rt = running(root)
    if rt:
        return call(rt, "POST", "/api/claude", body)
    from .server import claude_action
    return claude_action(Rounds(proj.ensure(root)), body)[0]


def ask(root, source, then_wait=False):
    """Question cards on the page. The desk starts if needed (a desktop notification brings you
    there when no page is open)."""
    raw = sys.stdin.read() if source in (None, "-") else Path(source).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except ValueError as e:
        sys.exit(f"review-desk ask: that isn't JSON ({e})")
    rt = start(root, open_browser=False, quiet=True)
    try:
        out = call(rt, "POST", "/api/claude", {**data, "action": "ask"})
    except RuntimeError as e:
        sys.exit(f"review-desk ask: {e}")
    q = out["question"]
    print(f"asked {q['id']} ({len(q['questions'])} question(s))")
    if not out.get("pages"):
        print("No page is open, so a desktop notification asks them to look. If they don't, ask in the chat.")
    if then_wait:
        wait(root)
    else:
        print("The answers come through `review-desk wait`.")


def selftest():
    """Checks, in a folder of its own, that the desk works here."""
    import shutil
    import tempfile
    import threading

    from . import qr
    from .markdown import all_items
    from .server import make_server

    good = True

    def check(name, step):
        nonlocal good
        try:
            step()
            print(f"ok    {name}")
        except Exception as e:  # anything at all is worth showing here
            good = False
            print(f"FAIL  {name}: {e}")

    def need(condition, why):
        if not condition:
            raise AssertionError(why)

    check(f"Python {sys.version.split()[0]}", lambda: need(sys.version_info >= (3, 10), "3.10 or newer, please"))
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        folder = proj.ensure(root) / "selftest"
        folder.mkdir()
        (folder / "checklist.md").write_text("# Self-test\n\n## A\n\n- [ ] One thing {#one}\n      Expected: it works.\n",
                                             encoding="utf-8")
        rounds = Rounds(proj.review_dir(root))
        check("reads a checklist", lambda: need([i["id"] for i in all_items(rounds.doc("selftest"))] == ["one"], "item one"))
        server = make_server(root, port=0, quiet=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        rt = {"port": server.server_port, "token": server.desk.token}
        try:
            check("serves the page on 127.0.0.1", lambda: need(call(rt, "GET", "/api/state")["rounds"], "a round"))
            check("saves an answer", lambda: (call(rt, "POST", "/api/item", {"round": "selftest", "item": "one", "verdict": "works"}),
                                             need("**Works**" in (folder / "answers.md").read_text(), "answers.md")))
        finally:
            server.shutdown()
            server.server_close()
    check("draws QR codes", lambda: need(qr.svg("http://192.168.1.2:41000/?p=x").startswith("<svg"), "an SVG"))
    print(f"info  git: {'yes' if shutil.which('git') else 'no (reviews work, outside git)'}")
    print(f"info  desktop notifications: {'notify-send' if shutil.which('notify-send') else 'none (the page still chimes)'}")
    print("All good." if good else "Something is wrong; see above.")
    sys.exit(0 if good else 1)


def config(root, title=None, accent=None):
    proj.ensure(root)
    if accent and not (accent.startswith("#") and len(accent) in (4, 7)):
        sys.exit("an accent is a colour like #55d6ad")
    print(json.dumps(proj.save_settings(root, title=title, accent=accent)))


def main(argv=None):
    # `--project` works before the command and after it.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", default=argparse.SUPPRESS,
                        help="the project folder (the git repository around here otherwise)")
    parser = argparse.ArgumentParser(prog="review-desk", description=__doc__, parents=[common],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("start", parents=[common])
    p.add_argument("--no-open", action="store_true")
    sub.add_parser("stop", parents=[common])
    sub.add_parser("open", parents=[common])
    p = sub.add_parser("status", parents=[common])
    p.add_argument("--hook", action="store_true")
    p = sub.add_parser("wait", parents=[common])
    p.add_argument("--timeout", type=float, help="give up after this many seconds (default: never)")
    p = sub.add_parser("answers", parents=[common])
    p.add_argument("round")
    p = sub.add_parser("reply", parents=[common])
    p.add_argument("round")
    p.add_argument("item")
    p.add_argument("text", help="the reply (- reads it from stdin)")
    p.add_argument("--to", help="the message it answers")
    p = sub.add_parser("retest", parents=[common])
    p.add_argument("round")
    p.add_argument("items", nargs="+")
    p.add_argument("--note", default="", help="what changed (- reads it from stdin)")
    p = sub.add_parser("idea", parents=[common])
    p.add_argument("round")
    p.add_argument("item")
    p.add_argument("message")
    p.add_argument("status", choices=("new", "planned", "done", "declined"))
    p = sub.add_parser("ask", parents=[common])
    p.add_argument("file", nargs="?", help="the questions as JSON (- or nothing: stdin)")
    p.add_argument("--wait", action="store_true", help="then wait for the answers")
    p = sub.add_parser("config", parents=[common])
    p.add_argument("--title")
    p.add_argument("--accent")
    sub.add_parser("selftest", parents=[common])
    p = sub.add_parser("serve", parents=[common])
    p.add_argument("--port", type=int)
    args = parser.parse_args(argv)
    if args.command == "selftest":
        return selftest()
    root = proj.find_root(getattr(args, "project", None))

    if args.command == "start":
        start(root, open_browser=not args.no_open)
    elif args.command == "stop":
        stop(root)
    elif args.command == "open":
        rt = start(root, open_browser=False, quiet=True)
        webbrowser.open(rt["url"])
        print(rt["url"])
    elif args.command == "status":
        status(root, hook=args.hook)
    elif args.command == "wait":
        wait(root, args.timeout)
    elif args.command == "answers":
        print(answers_text(Rounds(proj.review_dir(root)), args.round))
    elif args.command in ("reply", "retest", "idea"):
        try:
            if args.command == "reply":
                text = sys.stdin.read() if args.text == "-" else args.text
                out = claude(root, {"action": "reply", "round": args.round, "item": args.item, "text": text, "to": args.to})
                print(f"replied ({out['message']['id']})")
            elif args.command == "retest":
                note = sys.stdin.read() if args.note == "-" else args.note
                out = claude(root, {"action": "retest", "round": args.round, "items": args.items, "text": note})
                print(f"{len(args.items)} item(s) back for another look, round {out['round']}")
            else:
                claude(root, {"action": "idea", "round": args.round, "item": args.item, "id": args.message,
                              "status": args.status})
                print(f"idea {args.message}: {args.status}")
        except (RuntimeError, ValueError, KeyError) as e:
            sys.exit(f"review-desk {args.command}: {e}")
    elif args.command == "ask":
        ask(root, args.file, args.wait)
    elif args.command == "config":
        config(root, args.title, args.accent)
    elif args.command == "serve":
        from .server import serve
        serve(root, args.port)
