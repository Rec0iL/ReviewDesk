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
    config [--title T] [--accent #rrggbb]
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
            print(f"Answered at {e['at']}: {e.get('question', '?')}")
            print(json.dumps(e.get("answers", {}), ensure_ascii=False, indent=2))
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
    p = sub.add_parser("config", parents=[common])
    p.add_argument("--title")
    p.add_argument("--accent")
    p = sub.add_parser("serve", parents=[common])
    p.add_argument("--port", type=int)
    args = parser.parse_args(argv)
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
    elif args.command == "config":
        config(root, args.title, args.accent)
    elif args.command == "serve":
        from .server import serve
        serve(root, args.port)
