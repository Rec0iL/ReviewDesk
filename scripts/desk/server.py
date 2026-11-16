"""The desk's page and its server: one per project, in the background, on 127.0.0.1 only.

- `GET /` is the page; `/desk.css`, `/desk.js`, `/i18n.js` and the fonts come with it.
- `GET /api/state` lists the rounds, `GET /api/round/<slug>` gives one with its answers,
  `GET /api/events` streams what changes (server-sent events), `GET /files/<slug>/...` serves a
  round's pictures and files.
- `POST /api/...` changes answers; every call needs the page's token (`X-Desk-Token`, or `t=` for
  the event stream), and every request a Host of this address, so no other web page can read or
  write.
- A watcher looks at `.review/` every second and tells the page when Claude changed a checklist.
"""
import collections
import html
import json
import mimetypes
import os
import queue
import re
import secrets
import select
import shutil
import socket
import subprocess
import threading
import time
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import attach, markdown, peers, phone, qr
from . import project as proj
from .runs import Runs
from .store import LOCK, Board, Events, Questions, Rounds, Seen, ideas, messages, owner_name

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent.parent / "assets"
STATIC = {
    "/desk.css": ("page/desk.css", "text/css; charset=utf-8"),
    "/desk.js": ("page/desk.js", "text/javascript; charset=utf-8"),
    "/i18n.js": ("page/i18n.js", "text/javascript; charset=utf-8"),
    "/extras.js": ("page/extras.js", "text/javascript; charset=utf-8"),
    "/board.js": ("page/board.js", "text/javascript; charset=utf-8"),
    "/desks.js": ("page/desks.js", "text/javascript; charset=utf-8"),
    "/fonts/plex-sans.ttf": ("fonts/IBMPlexSans-Variable.ttf", "font/ttf"),
    "/fonts/plex-mono.ttf": ("fonts/IBMPlexMono-Regular.ttf", "font/ttf"),
}
MAX_BODY = 4 * 1024 * 1024
IDLE = 24 * 3600
WAIT = 25          # seconds one `wait` request waits before the command asks again
LISTENING = 6      # seconds after a `wait` request that Claude still counts as listening


class Desk:
    """One project's desk: its rounds, its events, the pages connected to it."""

    def __init__(self, root, quiet=False):
        self.root = Path(root)
        self.folder = proj.ensure(self.root)
        self.rounds = Rounds(self.folder)
        self.rounds.settle()
        self.events = Events(self.folder)
        self.questions = Questions(self.folder)
        self.board = Board(self.folder)
        self.seen = Seen(self.folder)
        self.seen.start(self.rounds)
        self.token = proj.token(self.root)
        self.clients = []
        self.clients_lock = threading.Lock()
        self.presence = {}
        self.pages = {}            # each open page: is it visible, may it show notifications
        self.waits = {}            # `wait` requests running now, by owner ("" = no owner)
        self.last_wait = {}        # when each owner's last `wait` request ended
        self.url = ""
        self.port = 0
        self.phone = None          # the phone's listener while it is on
        self.phone_clients = []
        self.last_seen = time.time()
        # REVIEW_DESK_NO_NOTIFY=1 keeps the desktop quiet (the tests set it).
        self.notifier = None if quiet or os.environ.get("REVIEW_DESK_NO_NOTIFY") else shutil.which("notify-send")
        self.runs = Runs(self.root, self.rounds, self.broadcast)
        # what the other desks see of this one: a number that goes up with every change, the
        # notifications that came with them, and since when a tab on another desk shows it
        self.serial = 0
        self.serial_changed = threading.Condition()
        self.notices = collections.deque(maxlen=50)
        self.watched_until = 0.0
        self.cached = (-1, None)
        self.peers = peers.Peers(self)
        # what Claude did, for the bell's list (`.notices.json`, the last 100)
        self.history_path = self.folder / ".notices.json"
        self.history = collections.deque(proj.read_json(self.history_path, []) or [], maxlen=100)
        self.say = (lambda _: None) if quiet else (lambda text: print(text, flush=True))

    # -- live updates ------------------------------------------------------------------------

    def broadcast(self, **event):
        with self.clients_lock:
            for q in list(self.clients):
                if q in self.phone_clients and event.get("type") in ("desks", "peer"):
                    continue    # the phone reaches no other desk
                q.put(event)
        if event.get("type") not in ("run", "desks", "peer"):
            self.bump(event)

    def bump(self, event=None):
        """Something the other desks may show changed (with a notification, when `event` has
        one): their requests waiting on `/api/peer` return."""
        note = (event or {}).get("notify")
        with self.serial_changed:
            self.serial += 1
            if note:
                entry = {"kind": event.get("type"), "what": event.get("what"), "slug": event.get("slug"),
                         "item": event.get("item"), "notify": note}
                self.notices.append((self.serial, entry))
                self.history.append(entry | {"at": time.time()})
                try:
                    proj.write_json(self.history_path, list(self.history))
                except OSError:
                    pass
            self.serial_changed.notify_all()

    def own_history(self):
        """What Claude did on this desk, newest first, each with the desk it happened on."""
        settings = proj.settings(self.root)
        me = {"project": str(self.root), "title": settings["title"], "accent": settings["accent"], "url": self.url}
        return [e | me for e in reversed(self.history)]

    def all_history(self, limit=60):
        """The bell's list: this desk's and every other running desk's, newest first."""
        out = self.own_history()
        for path in self.peers.all():
            rt = proj.runtime(path)
            if not rt:
                continue
            try:
                out += peers.history(rt)
            except (OSError, ValueError):
                continue
        return sorted(out, key=lambda e: e.get("at", 0), reverse=True)[:limit]

    def connected(self):
        with self.clients_lock:
            return len(self.clients)

    def local_pages(self):
        """This computer's pages connected to the desk (not the phone's)."""
        with self.clients_lock:
            return len(self.clients) - len(self.phone_clients)

    def watched(self):
        """Is a tab on another desk showing this one (its Desks list, its chime)?"""
        return time.time() < self.watched_until

    # -- what the other desks see ------------------------------------------------------------

    def sessions(self, state=None):
        """Each session on this desk (by owner, "" for the main one) and what waits there: for
        you (question cards, items back for another look, Claude's replies you haven't opened),
        for Claude (hand-backs and answers its `wait` hasn't taken), and whether it listens."""
        state = state or self.state()
        out = {}
        get = lambda o: out.setdefault(o, {"questions": 0, "retests": 0, "replies": 0, "claude": 0, "listening": False})
        for r in state["rounds"]:
            x = get(r.get("owner", ""))
            x["retests"] += (r.get("counts") or {}).get("retest", 0)
            x["replies"] += r.get("unseen", 0)
        for q in self.questions.pending():
            get(q.get("owner", ""))["questions"] += 1
        for e in self.events.waiting_any():
            get(e.get("owner", ""))["claude"] += 1
        for o in self.listeners():
            get(o)["listening"] = True
        return out

    def summary(self):
        """This desk as the Desks list shows it (kept until something changes)."""
        serial = self.serial
        if self.cached[0] == serial:
            return self.cached[1]
        settings = proj.settings(self.root)
        data = {"project": str(self.root), "title": settings["title"], "accent": settings["accent"],
                "url": self.url, "port": self.port, "pages": self.local_pages(), "sessions": self.sessions()}
        self.cached = (serial, data)
        return data

    def peer(self, since, timeout, watching):
        """What another desk asks: how this one is, as soon as something changed after
        `since` (-1: right away), with the notifications since then."""
        if watching:
            self.watched_until = max(self.watched_until, time.time() + timeout + 15)
        deadline = time.time() + timeout
        with self.serial_changed:
            while since >= 0 and self.serial <= since and time.time() < deadline:
                self.serial_changed.wait(max(0.0, deadline - time.time()))
            serial = self.serial
            notices = [n for k, n in self.notices if since >= 0 and k > since]
        return self.summary() | {"serial": serial, "notices": notices}

    def desks(self):
        """Every running desk this one knows, itself first."""
        others = sorted(self.peers.all().values(), key=lambda d: d.get("title", "").lower())
        return [self.summary() | {"here": True}] + others

    # -- the phone ------------------------------------------------------------------------------

    def phone_on(self):
        """Opens the desk to a phone on the home network: a second listener with a new secret."""
        if self.phone:
            return self.phone_status()
        ip = phone.lan_address()
        if not ip or not phone.home_network(ip):
            raise ValueError("this computer doesn't seem to be on a home network, so a phone can't reach it")
        ref = []
        handler = handler_for(self, ref, on_phone=True)
        for port in (self.port, 0):
            try:
                server = ThreadingHTTPServer((ip, port), handler)
                break
            except OSError:
                continue
        else:
            raise ValueError(f"no free port on {ip}")
        server.daemon_threads = True
        ref.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        token = secrets.token_urlsafe(18)
        until = time.time() + phone.HOURS * 3600
        self.phone = {"server": server, "ip": ip, "port": server.server_port, "token": token, "until": until,
                      "url": f"http://{ip}:{server.server_port}/?p={token}"}
        timer = threading.Timer(phone.HOURS * 3600, self.phone_off)
        timer.daemon = True
        timer.start()
        self.phone["timer"] = timer
        self.broadcast(type="phone", on=True)
        return self.phone_status()

    def phone_off(self):
        """Closes the phone's way in, and the line of any phone page still open."""
        p, self.phone = self.phone, None
        if not p:
            return {"on": False}
        p["timer"].cancel()
        with self.clients_lock:
            for q in self.phone_clients:
                q.put(None)

        def close():
            p["server"].shutdown()
            p["server"].server_close()

        threading.Thread(target=close, daemon=True).start()
        self.broadcast(type="phone", on=False)
        return {"on": False}

    def phone_status(self):
        p = self.phone
        if not p:
            return {"on": False}
        if "firewall" not in p:
            p["firewall"] = phone.firewall(p["port"], p["ip"])  # a few seconds: asked once per opening
        return {"on": True, "url": p["url"], "ip": p["ip"], "port": p["port"], "qr": qr.svg(p["url"]),
                "until": time.strftime("%H:%M", time.localtime(p["until"])), "firewall": p["firewall"]}

    def listeners(self):
        """Who is listening (a `wait` running, or one a moment ago), by owner, with how many
        `wait`s each has running now (more than one: only one of them gets the next hand-back)."""
        now_ = time.time()
        owners = {o for o, n in self.waits.items() if n > 0} | {o for o, t in self.last_wait.items() if now_ - t < LISTENING}
        return {o: max(self.waits.get(o, 0), 1) for o in sorted(owners)}

    def listening(self, owner=None):
        """Is Claude waiting for a hand-back: anyone (owner None), or that owner's listener?"""
        who = self.listeners()
        return bool(who) if owner is None else owner in who

    def owner_of(self, slug):
        """Whose listener a round's hand-backs go to (its checklist's `owner:`; "" for none)."""
        try:
            return owner_name(self.rounds.doc(slug)["meta"].get("owner", ""))
        except (OSError, ValueError):
            return ""

    def claude_did(self, slug, what, item=None, title="", body="", kind="round"):
        """Tells the pages what Claude just did, with a notification they show (chime, toast, or
        a desktop notification while hidden). With no page able to show it, the desktop shows it."""
        note = {"title": title, "body": body}
        self.broadcast(type=kind, slug=slug, by="claude", what=what, item=item, notify=note)
        pages = [p for p in self.pages.values() if time.time() - p.get("at", 0) < 120]
        if self.notifier and not self.watched() and not any(p.get("visible") or p.get("notify") for p in pages):
            threading.Thread(target=self.desktop_notification, args=(title, body), daemon=True).start()

    def desktop_notification(self, title, body):
        try:
            out = subprocess.run([self.notifier, "-a", "Review Desk", "-i", "dialog-information",
                                  "-A", "open=Open", title, body], capture_output=True, text=True, timeout=3600)
            if out.stdout.strip() == "open" and self.url:
                webbrowser.open(self.url)
        except (OSError, subprocess.SubprocessError):
            pass

    def snapshot(self):
        """What the watcher compares: each checklist's and the settings' modification time."""
        seen = {}
        for path in self.folder.glob("*/checklist.md"):
            try:
                # the checklist, and the pictures and videos it shows (Claude may replace one)
                pictures = []
                for src in re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", path.read_text(encoding="utf-8")):
                    try:
                        pictures.append((path.parent / src.removeprefix("./")).stat().st_mtime_ns)
                    except OSError:
                        pictures.append(0)
                seen[path.parent.name] = (path.stat().st_mtime_ns, tuple(pictures))
            except OSError:
                pass
        try:
            seen[".desk"] = (self.folder / "desk.json").stat().st_mtime_ns
        except OSError:
            pass
        return seen

    def watch(self, stop):
        before = self.snapshot()
        listening = self.listeners()
        while not stop.wait(1.0):
            if self.listeners() != listening:
                listening = self.listeners()
                self.broadcast(type="listening", on=bool(listening), listeners=listening)
            after = self.snapshot()
            if after == before:
                continue
            for slug in set(before) | set(after):
                if slug == ".desk":
                    if before.get(slug) != after.get(slug):
                        self.broadcast(type="settings")
                elif before.get(slug) != after.get(slug):
                    new = slug not in before
                    if new and slug in after:
                        self.events.add("round", round=slug)
                        try:
                            title = self.rounds.doc(slug)["title"]
                        except (OSError, ValueError):
                            title = slug
                        self.claude_did(slug, "new", title="Something new to check", body=title)
                    else:
                        self.broadcast(type="round", slug=slug, by="claude", what="edit")
            self.broadcast(type="rounds")
            before = after

    # -- what the API answers ----------------------------------------------------------------

    def state(self):
        last_send = {e.get("round"): e for e in self.events.all() if e["type"] == "send"}
        seen = self.seen.all()
        rounds = []
        for slug in self.rounds.slugs():
            try:
                summary = self.rounds.summary(slug, seen.get(slug, set()))
                summary["owner"] = self.owner_of(slug)
                e = last_send.get(slug)
                summary["read"] = bool(e) and self.events.handled(e.get("owner", "")) >= e["seq"]
                rounds.append(summary)
            except (OSError, ValueError) as e:
                rounds.append({"slug": slug, "title": slug, "error": str(e)})
        return {"project": proj.settings(self.root) | {"path": str(self.root)}, "rounds": rounds,
                "listening": self.listening(), "listeners": self.listeners(), "version": asset_version()}

    def last_sends(self):
        """When each round was last handed back."""
        return {e["round"]: e["at"] for e in self.events.all() if e["type"] == "send" and e.get("round")}

    def wait(self, timeout, owner="", gone=lambda: False):
        """What this owner's listener hasn't had yet (hand-backs, answers), as soon as there is
        some; marked as had when it goes out, so it goes out once, and only to its owner.
        `gone()` says the one asking stopped listening (its `wait` ended): it then gets nothing,
        and stops counting as listening at once."""
        owner = owner_name(owner)
        waiting, left_us = [], False
        with LOCK:
            self.waits[owner] = self.waits.get(owner, 0) + 1
        try:
            deadline = time.time() + timeout
            with self.events.changed:
                while True:
                    if gone():
                        left_us = True
                        waiting = []
                        break
                    waiting = self.events.waiting(owner=owner)
                    if waiting:
                        self.events.mark(max(e["seq"] for e in waiting), owner)
                        break
                    left = deadline - time.time()
                    if left <= 0:
                        break
                    self.events.changed.wait(min(left, 1.0))   # and every second: still there?
        finally:
            with LOCK:
                self.waits[owner] -= 1
                if not left_us:
                    self.last_wait[owner] = time.time()
        if waiting:
            self.broadcast(type="handled", rounds=sorted({e.get("round") for e in waiting if e.get("round")}))
        return waiting


def handler_for(desk, server_ref, on_phone=False):
    """The request handler for the desk's own listener (127.0.0.1), or, `on_phone`, for the
    phone's (the home-network address, its own secret, no commands)."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        # -- replies -------------------------------------------------------------------------

        def reply(self, status, body, kind, extra=()):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            # Other pages may not even show what this one serves.
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in extra:
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, status, data):
            self.reply(status, json.dumps(data, ensure_ascii=False), "application/json; charset=utf-8")

        def fail(self, status, message):
            self.send_json(status, {"error": message})

        # -- guards --------------------------------------------------------------------------

        def ours(self):
            port = server_ref[0].server_port
            host = self.headers.get("Host", "")
            if on_phone:
                return bool(desk.phone) and host == f"{desk.phone['ip']}:{port}"
            return host in (f"127.0.0.1:{port}", f"localhost:{port}")

        def local(self):
            """A request from this computer (the phone's page may not run commands)."""
            return not on_phone and self.client_address[0] in ("127.0.0.1", "::1")

        def secret(self):
            if on_phone:
                return desk.phone["token"] if desk.phone else None
            return desk.token

        def token_ok(self, query):
            wanted = self.secret()
            if not wanted:
                return False
            given = self.headers.get("X-Desk-Token") or query.get("t", [""])[0]
            if not given and on_phone:
                cookie = SimpleCookie(self.headers.get("Cookie", ""))
                given = cookie["desk"].value if "desk" in cookie else ""
            return secrets.compare_digest(given, wanted)

        def hung_up(self):
            """The one asking closed its end (a `wait` that was stopped): nothing to read, and
            reading says so. Nothing else comes on a `wait` request's line."""
            try:
                if not select.select([self.connection], [], [], 0)[0]:
                    return False
                return self.connection.recv(1, socket.MSG_PEEK) == b""
            except (OSError, ValueError):
                return True

        def body(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ValueError("too much")
            data = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(data, dict):
                raise ValueError("a JSON object")
            return data

        # -- GET -----------------------------------------------------------------------------

        def do_GET(self):
            if not self.path.startswith(("/api/peer?", "/api/history?own=1")):
                desk.last_seen = time.time()     # another desk asking keeps none alive
            if not self.ours():
                return self.reply(403, "not here", "text/plain")
            url = urlparse(self.path)
            path, query = url.path, parse_qs(url.query)
            if path == "/":
                if not on_phone:
                    return self.reply(200, page(desk), "text/html; charset=utf-8")
                # The phone gets in with the secret from the QR code, kept as a cookie for its
                # pictures and files.
                if query.get("p", [""])[0] and secrets.compare_digest(query["p"][0], self.secret() or "") \
                        or self.token_ok({}):
                    cookie = f"desk={self.secret()}; HttpOnly; SameSite=Strict; Path=/; Max-Age={phone.HOURS * 3600}"
                    return self.reply(200, page(desk, on_phone=True), "text/html; charset=utf-8", [("Set-Cookie", cookie)])
                return self.reply(403, "Scan the QR code on the desk again.", "text/plain; charset=utf-8")
            if path in STATIC:
                name, kind = STATIC[path]
                return self.reply(200, (ASSETS / name).read_bytes(), kind)
            if path == "/api/ping" and not on_phone:
                return self.send_json(200, {"project": str(desk.root), "pid": os.getpid(), "pages": desk.connected(),
                                            "watched": desk.watched()})
            if path.startswith("/files/") and (not on_phone or self.token_ok(query)):
                return self.file(unquote(path.removeprefix("/files/")))
            if not self.token_ok(query):
                return self.fail(403, "not allowed")
            try:
                if path == "/api/state":
                    return self.send_json(200, desk.state() | {"presence": desk.presence})
                if path.startswith("/api/round/"):
                    slug = path.removeprefix("/api/round/")
                    doc = desk.rounds.doc(slug)
                    return self.send_json(200, {"doc": doc, "state": present(desk.rounds.state(slug, doc))})
                if path == "/api/events":
                    return self.stream(query.get("c", [""])[0][:16])
                if path == "/api/phone":
                    if on_phone:
                        return self.fail(403, "not from the phone")
                    return self.send_json(200, desk.phone_status())
                if path == "/api/ideas":
                    return self.send_json(200, {"ideas": ideas(desk.rounds, desk.board, desk.last_sends())})
                if path == "/api/questions":
                    return self.send_json(200, {"questions": desk.questions.pending()})
                if path == "/api/runs":
                    return self.send_json(200, {"runs": desk.runs.of(query.get("round", [""])[0])})
                if path == "/api/log":
                    slug = query.get("round", [""])[0]
                    sources = attach.log_sources(desk.root, desk.rounds.doc(slug))
                    out = []
                    for src in sources:
                        try:
                            out.append({"name": src["name"], "lines": attach.tail(src["path"])})
                        except OSError as e:
                            out.append({"name": src["name"], "error": e.strerror or str(e), "lines": []})
                    return self.send_json(200, {"logs": out})
                if path == "/api/source":
                    return self.send_json(200, attach.source(desk.root, query.get("path", [""])[0]))
                if path == "/api/commit":
                    return self.send_json(200, attach.commit(desk.root, query.get("ref", [""])[0]))
                if path == "/api/peer" and not on_phone:
                    since = int(query.get("since", ["-1"])[0])
                    timeout = min(max(float(query.get("timeout", [peers.POLL])[0]), 0), 60)
                    return self.send_json(200, desk.peer(since, timeout, query.get("watching", ["0"])[0] == "1"))
                if path == "/api/history":
                    own = on_phone or query.get("own", [""])[0] == "1"
                    return self.send_json(200, {"history": desk.own_history() if own else desk.all_history()})
                if path == "/api/desks" and not on_phone:
                    return self.send_json(200, {"desks": desk.desks()})
                if path == "/api/wait":
                    timeout = min(max(float(query.get("timeout", [WAIT])[0]), 0), 120)
                    events = desk.wait(timeout, query.get("as", [""])[0], self.hung_up)
                    if not events and self.hung_up():
                        self.close_connection = True   # nobody left to tell
                        return
                    return self.send_json(200, {"events": events})
            except (OSError, ValueError) as e:
                return self.fail(400, str(e))
            self.reply(404, "nothing here", "text/plain")

        def file(self, rel):
            """A file of a round: anything inside its folder (its pictures, its files)."""
            slug, _, inner = rel.partition("/")
            try:
                base = desk.rounds.path(slug).resolve()
            except ValueError:
                return self.reply(404, "nothing here", "text/plain")
            target = (base / inner).resolve()
            if not inner or base not in target.parents or not target.is_file():
                return self.reply(404, "nothing here", "text/plain")
            kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if kind.startswith("text/") or kind in ("application/json", "application/javascript"):
                # Shown as plain text, never as a page or a script of this origin.
                kind = "text/plain; charset=utf-8"
            self.send_file(target, kind)

        def send_file(self, target, kind):
            """A file in pieces, with ranges (so recordings can be scrubbed)."""
            size = target.stat().st_size
            start, end, status = 0, size - 1, 200
            wanted = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
            if wanted and size:
                first, last = wanted.groups()
                if first:
                    start, end = int(first), min(int(last), size - 1) if last else size - 1
                elif last:
                    start = max(0, size - int(last))
                if start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 206
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(end - start + 1 if size else 0))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "sandbox")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if not size:
                return
            with open(target, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(attach.CHUNK, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)

        def stream(self, client):
            """Server-sent events: what changed, as it happens, with a comment every 15 s to keep
            the line open."""
            q = queue.Queue()
            with desk.clients_lock:
                desk.clients.append(q)
                if on_phone:
                    desk.phone_clients.append(q)
            if client:
                desk.pages.setdefault(client, {"visible": True, "notify": False, "at": time.time()})
            desk.bump()     # the other desks' lists say whether it has a tab
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                self.wfile.write(b"retry: 1500\n\n")
                self.wfile.flush()
                while True:
                    try:
                        event = q.get(timeout=15)
                        if event is None:
                            break
                        self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8"))
                    except queue.Empty:
                        self.wfile.write(b": still here\n\n")
                    self.wfile.flush()
                    desk.last_seen = time.time()
            except (OSError, ValueError):
                pass
            finally:
                with desk.clients_lock:
                    desk.clients.remove(q)
                    if q in desk.phone_clients:
                        desk.phone_clients.remove(q)
                desk.pages.pop(client, None)
                desk.bump()
                self.close_connection = True

        # -- POST ----------------------------------------------------------------------------

        def do_POST(self):
            desk.last_seen = time.time()
            url = urlparse(self.path)
            if not self.ours() or not self.token_ok(parse_qs(url.query)):
                return self.fail(403, "not allowed")
            try:
                if url.path == "/api/upload":
                    result = self.upload(parse_qs(url.query))
                else:
                    data = self.body()
                    result = self.act(url.path, data)
            except (ValueError, KeyError, TypeError) as e:
                return self.fail(400, str(e))
            except OSError as e:
                return self.fail(500, str(e))
            if result is None:
                return self.reply(404, "nothing here", "text/plain")
            self.send_json(200, result)

        def upload(self, query):
            """An attachment: the file is the body, what it is goes in the query."""
            get = lambda key, default="": query.get(key, [default])[0]
            slug, item_id, kind = get("round"), get("item"), get("kind", "file")
            if item_id != "overall":
                desk.rounds.state(slug)["items"][item_id]  # the item exists (KeyError otherwise)
            folder = desk.rounds.path(slug, "files")
            length = int(self.headers.get("Content-Length") or 0)
            name = attach.save_upload(self.rfile, length, folder, item_id, kind, get("name"))
            try:
                entry = desk.rounds.add_file(slug, item_id, name, kind, get("label"))
            except ValueError:
                (folder / name).unlink(missing_ok=True)
                raise
            desk.broadcast(type="round", slug=slug, by="you", item=item_id, client=get("client"))
            return {"file": entry}

        def act(self, path, data):
            rounds = desk.rounds
            slug = data.get("round", "")
            if path == "/api/item":
                fields = {k: data[k] for k in ("verdict", "severity", "note") if k in data}
                answer = rounds.set_item(slug, data["item"], fields)
                desk.broadcast(type="round", slug=slug, by="you", item=data["item"], client=data.get("client"))
                return {"item": answer}
            if path == "/api/overall":
                overall = rounds.set_overall(slug, data["note"])
                desk.broadcast(type="round", slug=slug, by="you", item="overall", client=data.get("client"))
                return {"overall": overall}
            if path == "/api/message":
                if data.get("delete"):
                    rounds.delete_message(slug, data["item"], data["id"])
                    message = None
                else:
                    message = rounds.message(slug, data["item"], data["kind"], data["text"],
                                             reply_to=data.get("to"), message_id=data["id"])
                desk.broadcast(type="round", slug=slug, by="you", item=data["item"], client=data.get("client"))
                return {"message": message}
            if path == "/api/board/idea":
                if data.get("delete"):
                    desk.board.remove(data["id"])
                    idea = None
                else:
                    idea = desk.board.add(data["text"], data.get("id"))
                desk.broadcast(type="ideas", client=data.get("client"))
                return {"idea": idea}
            if path == "/api/idea/reply":
                # your answer on an idea from the Ideas tab; the idea may live in a review
                if slug:
                    idea = next((m for m in messages(rounds.state(slug), data["item"]) if m["id"] == data["id"]), None)
                    if not idea:
                        raise ValueError("no such idea")
                    m = rounds.message(slug, data["item"], "comment", data["text"], reply_to=data["id"], message_id=data.get("reply_id"))
                    desk.board.followup(slug, rounds.doc(slug)["title"], data["item"], data["id"], idea["text"], data["text"], m["id"])
                    desk.broadcast(type="round", slug=slug, by="you", item=data["item"], client=data.get("client"))
                else:
                    m = desk.board.reply(data["id"], data["text"], sender="you")
                desk.broadcast(type="ideas", client=data.get("client"))
                return {"reply": m}
            if path == "/api/idea/edit":
                # your own words on an idea, until Claude has them
                if slug:
                    target = next((m for m in messages(rounds.state(slug), data["item"]) if m["id"] == data["target"]), None)
                    sent = desk.last_sends().get(slug)
                    if not target or target["from"] != "you":
                        raise ValueError("that isn't yours to change")
                    if (sent and target["at"] <= sent) or target["id"] in desk.board.followup_seen():
                        raise ValueError("Claude has read that already")
                    m = rounds.message(slug, data["item"], target["kind"], data["text"], message_id=target["id"])
                    desk.board.reword_followup(target["id"], data["text"])
                    desk.broadcast(type="round", slug=slug, by="you", item=data["item"], client=data.get("client"))
                else:
                    m = desk.board.edit(data["id"], data["text"], None if data["target"] == data["id"] else data["target"])
                desk.broadcast(type="ideas", client=data.get("client"))
                return {"message": m}
            if path == "/api/file/remove":
                if rounds.remove_file(slug, data["item"], data["name"]):
                    (rounds.path(slug, "files") / os.path.basename(data["name"])).unlink(missing_ok=True)
                desk.broadcast(type="round", slug=slug, by="you", item=data["item"], client=data.get("client"))
                return {"ok": True}
            if path == "/api/run":
                if not self.local():
                    raise ValueError("Run works on this computer's page only")
                return {"run": desk.runs.start(slug, data["code"])}
            if path == "/api/run/stop":
                return {"run": desk.runs.stop(data["id"])}
            if path == "/api/send":
                message = str(data.get("message") or "")
                rounds.doc(slug)   # the round is there before anything is kept
                owner = desk.owner_of(slug)
                # "Answer and hand back": the owner's question cards answered with it. One step
                # under the events' lock, so `wait` wakes to all of it or none.
                with desk.events.changed:
                    answered = desk.questions.answer_all(data.get("answers") or [], owner)
                    sent = rounds.send(slug, message)
                    for q in answered:
                        desk.events.add("answer", question=q["id"], title=q["title"], answers=q["answers"],
                                        owner=owner, round=slug)
                    desk.events.add("send", round=slug, owner=owner, message=rounds.state(slug)["message"],
                                    answered=[q["id"] for q in answered])
                desk.broadcast(type="round", slug=slug, by="you", client=data.get("client"))
                desk.broadcast(type="rounds")
                if answered:
                    desk.broadcast(type="questions", client=data.get("client"))
                return {"sent": sent, "listening": desk.listening(owner), "answered": [q["id"] for q in answered]}
            if path == "/api/answer":
                answered = desk.questions.answer(data["id"], data["answers"])
                desk.events.add("answer", question=answered["id"], title=answered["title"], answers=answered["answers"],
                                owner=answered.get("owner", ""))
                desk.broadcast(type="questions", client=data.get("client"))
                return {"question": answered}
            if path == "/api/seen":
                if desk.seen.mark(rounds, slug):
                    desk.broadcast(type="seen", slug=slug, client=data.get("client"))
                return {"ok": True}
            if path == "/api/presence":
                if data.get("item") is not None:
                    desk.presence = {"round": slug, "item": data.get("item"), "at": time.strftime("%H:%M:%S")}
                if data.get("client"):
                    desk.pages[str(data["client"])[:16]] = {"visible": bool(data.get("visible", True)),
                                                           "notify": bool(data.get("notify")), "at": time.time()}
                return {"ok": True}
            if path == "/api/claude" and data.get("action") == "ask":
                asked = desk.questions.add(data)
                first = asked["questions"][0]["question"]
                desk.claude_did(None, "ask", title=asked["title"] or "Claude has a question", body=first, kind="questions")
                return {"question": asked, "pages": desk.connected() or int(desk.watched())}
            if path == "/api/claude":
                result, notice = claude_action(rounds, data, desk.board)
                if notice and data.get("round") == "board":
                    desk.claude_did(None, kind="ideas", **notice)
                elif notice:
                    desk.claude_did(slug, **notice)
                else:
                    desk.broadcast(type="round", slug=slug, by="claude", what=data.get("action"), item=data.get("item"))
                return result
            if path == "/api/phone":
                if not self.local():
                    raise ValueError("the phone is turned on and off on this computer")
                return desk.phone_on() if data.get("on") else desk.phone_off()
            if path == "/api/quit":
                if not self.local():
                    raise ValueError("only this computer stops the desk")
                threading.Thread(target=server_ref[0].shutdown, daemon=True).start()
                return {"ok": True}
            return None

        def log_message(self, *_):
            pass

    return Handler


def claude_action(rounds, data, board=None):
    """What Claude does through the command: a reply in a thread, items back for another look,
    its word on an idea. Returns the result and what to tell you about it (None: nothing)."""
    slug, action = data.get("round", ""), data.get("action")
    if slug == "board":
        # the Ideas tab's own ideas: `reply board - "text" --to ID`, `idea board - ID planned`
        if board is None:
            raise ValueError("no board here")
        if action == "reply":
            if not data.get("to"):
                raise ValueError("which idea? (--to ID)")
            r = board.reply(data["to"], data["text"])
            first = (data["text"].strip().splitlines() or [""])[0][:140]
            return {"message": r}, {"what": "reply", "title": "Claude replied · Ideas", "body": first}
        if action == "idea":
            return {"message": board.status(data["id"], data["status"])}, None
        raise ValueError(f"Claude can't {action!r} on the board")
    title = rounds.doc(slug)["title"]
    if action == "reply":
        m = rounds.message(slug, data["item"], "reply", data["text"], sender="claude", reply_to=data.get("to"))
        first = (data["text"].strip().splitlines() or [""])[0][:140]
        return {"message": m}, {"what": "reply", "item": data["item"], "title": f"Claude replied · {title}", "body": first}
    if action == "retest":
        notes = data.get("notes") or {}
        items = list(data.get("items") or notes)
        n = rounds.retest(slug, items, data.get("text", ""), notes)
        count = f"{len(items)} item{'s' if len(items) != 1 else ''}"
        return {"round": n}, {"what": "retest", "item": items[0] if items else None,
                              "title": f"{count} back for another look", "body": f"{title} · round {n}"}
    if action == "idea":
        return {"message": rounds.idea_status(slug, data["item"], data["id"], data["status"])}, None
    raise ValueError(f"Claude can't {action!r} here")


def rich(text):
    """Claude's own words on the page: inline Markdown, line breaks kept."""
    return "<br>".join(markdown.inline(line) for line in text.split("\n"))


def present(state):
    """A round's answers for the page: Claude's messages and notes as HTML too."""
    threads = [a["messages"] for a in state["items"].values()] + [state["overall"]["messages"]]
    for thread in threads:
        for m in thread:
            if m["from"] == "claude":
                m["html"] = rich(m["text"])
    for a in state["items"].values():
        if a["retest"] and a["retest"].get("note"):
            a["retest"]["html"] = rich(a["retest"]["note"])
        for h in a["history"]:
            h["html"] = html.escape(h["note"]).replace("\n", "<br>")
            if (h.get("retest") or {}).get("note"):
                h["retest_html"] = rich(h["retest"]["note"])
    return state


def asset_version():
    """A fingerprint of the page's own files: it changes when Review Desk is updated."""
    return format(max(p.stat().st_mtime_ns for p in (ASSETS / "page").iterdir()), "x")


def page(desk, on_phone=False):
    """The page, with what it needs to start: its token, the project's settings, and whether it
    is this computer's page (only that one runs commands and lets the phone in)."""
    token = desk.phone["token"] if on_phone else desk.token
    boot = {"token": token, "project": proj.settings(desk.root), "local": not on_phone,
            "phone": bool(desk.phone) and not on_phone, "version": asset_version()}
    script = json.dumps(boot, ensure_ascii=False).replace("</", "<\\/")
    return (ASSETS / "page" / "index.html").read_text(encoding="utf-8").replace("/*BOOT*/null", script)


def make_server(root, port=None, quiet=False):
    """The desk's server for `root`, bound but not serving yet: on the project's own port, the
    next free one after it, or any."""
    desk = Desk(root, quiet)
    ref = []
    handler = handler_for(desk, ref)
    first = proj.stable_port(root) if port is None else port
    candidates = [first] if port is not None else [first + k for k in range(20)] + [0]
    for candidate in candidates:
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), handler)
            break
        except OSError:
            continue
    else:
        raise OSError("no free port for the desk")
    server.daemon_threads = True
    ref.append(server)
    server.desk = desk
    desk.port = server.server_port
    return server


def serve(root, port=None):
    """Runs the desk until it is told to stop (or a day goes by with no page and no command)."""
    server = make_server(root, port)
    desk = server.desk
    url = f"http://127.0.0.1:{server.server_port}/"
    desk.url = url
    runtime = desk.folder / ".runtime.json"
    proj.write_json(runtime, {"pid": os.getpid(), "port": server.server_port, "token": desk.token, "url": url,
                              "started": time.strftime("%Y-%m-%d %H:%M:%S")})
    stop = threading.Event()
    threading.Thread(target=desk.watch, args=(stop,), daemon=True).start()
    peers.register(desk.root)
    threading.Thread(target=desk.peers.run, args=(stop,), daemon=True).start()

    def idle():
        while not stop.wait(60):
            if desk.connected() == 0 and time.time() - desk.last_seen > IDLE:
                server.shutdown()

    threading.Thread(target=idle, daemon=True).start()
    desk.say(f"Review Desk for {desk.root} on {url}")
    try:
        server.serve_forever()
    finally:
        stop.set()
        desk.runs.stop_all()
        desk.phone_off()
        server.server_close()
        peers.unregister(desk.root)
        if (proj.read_json(runtime, {}) or {}).get("pid") == os.getpid():
            runtime.unlink(missing_ok=True)
