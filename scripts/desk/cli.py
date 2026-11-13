"""`review-desk`: the command Claude (and you) run. It works on the project around the current
folder (the git repository, or the folder itself), or the one `--project` names.

    start [--no-open]      the page in the background (opened once in your browser)
    stop | open            stop it | show it in the browser
    status [--hook]        rounds, answers waiting, where you are (--hook: one line, only when
                           answers wait, for a session-start hook)
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
    elif args.command == "config":
        config(root, args.title, args.accent)
    elif args.command == "serve":
        from .server import serve
        serve(root, args.port)
