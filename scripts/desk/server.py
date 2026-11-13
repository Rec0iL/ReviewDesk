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
import json
import mimetypes
import os
import queue
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import project as proj
from .store import Events, Rounds

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent.parent / "assets"
STATIC = {
    "/desk.css": ("page/desk.css", "text/css; charset=utf-8"),
    "/desk.js": ("page/desk.js", "text/javascript; charset=utf-8"),
    "/i18n.js": ("page/i18n.js", "text/javascript; charset=utf-8"),
    "/fonts/plex-sans.ttf": ("fonts/IBMPlexSans-Variable.ttf", "font/ttf"),
    "/fonts/plex-mono.ttf": ("fonts/IBMPlexMono-Regular.ttf", "font/ttf"),
}
MAX_BODY = 4 * 1024 * 1024
IDLE = 24 * 3600


class Desk:
    """One project's desk: its rounds, its events, the pages connected to it."""

    def __init__(self, root, quiet=False):
        self.root = Path(root)
        self.folder = proj.ensure(self.root)
        self.rounds = Rounds(self.folder)
        self.events = Events(self.folder)
        self.token = proj.token(self.root)
        self.clients = []
        self.clients_lock = threading.Lock()
        self.presence = {}
        self.last_seen = time.time()
        self.say = (lambda _: None) if quiet else (lambda text: print(text, flush=True))

    # -- live updates ------------------------------------------------------------------------

    def broadcast(self, **event):
        with self.clients_lock:
            for q in list(self.clients):
                q.put(event)

    def connected(self):
        with self.clients_lock:
            return len(self.clients)

    def snapshot(self):
        """What the watcher compares: each checklist's and the settings' modification time."""
        seen = {}
        for path in self.folder.glob("*/checklist.md"):
            try:
                seen[path.parent.name] = path.stat().st_mtime_ns
            except OSError:
                pass
        try:
            seen[".desk"] = (self.folder / "desk.json").stat().st_mtime_ns
        except OSError:
            pass
        return seen

    def watch(self, stop):
        before = self.snapshot()
        while not stop.wait(1.0):
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
                    self.broadcast(type="round", slug=slug, by="claude", new=new)
            self.broadcast(type="rounds")
            before = after

    # -- what the API answers ----------------------------------------------------------------

    def state(self):
        rounds = []
        for slug in self.rounds.slugs():
            try:
                rounds.append(self.rounds.summary(slug))
            except (OSError, ValueError) as e:
                rounds.append({"slug": slug, "title": slug, "error": str(e)})
        return {"project": proj.settings(self.root) | {"path": str(self.root)}, "rounds": rounds}


def handler_for(desk, server_ref):
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
            return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def token_ok(self, query):
            return secrets.compare_digest(
                self.headers.get("X-Desk-Token") or query.get("t", [""])[0], desk.token)

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
            desk.last_seen = time.time()
            if not self.ours():
                return self.reply(403, "not here", "text/plain")
            url = urlparse(self.path)
            path, query = url.path, parse_qs(url.query)
            if path == "/":
                return self.reply(200, page(desk), "text/html; charset=utf-8")
            if path in STATIC:
                name, kind = STATIC[path]
                return self.reply(200, (ASSETS / name).read_bytes(), kind)
            if path == "/api/ping":
                return self.send_json(200, {"project": str(desk.root), "pid": os.getpid(), "pages": desk.connected()})
            if path.startswith("/files/"):
                return self.file(unquote(path.removeprefix("/files/")))
            if not self.token_ok(query):
                return self.fail(403, "not allowed")
            try:
                if path == "/api/state":
                    return self.send_json(200, desk.state() | {"presence": desk.presence})
                if path.startswith("/api/round/"):
                    slug = path.removeprefix("/api/round/")
                    doc = desk.rounds.doc(slug)
                    return self.send_json(200, {"doc": doc, "state": desk.rounds.state(slug, doc)})
                if path == "/api/events":
                    return self.stream()
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
            self.reply(200, target.read_bytes(), kind)

        def stream(self):
            """Server-sent events: what changed, as it happens, with a comment every 15 s to keep
            the line open."""
            q = queue.Queue()
            with desk.clients_lock:
                desk.clients.append(q)
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
                self.close_connection = True

        # -- POST ----------------------------------------------------------------------------

        def do_POST(self):
            desk.last_seen = time.time()
            url = urlparse(self.path)
            if not self.ours() or not self.token_ok(parse_qs(url.query)):
                return self.fail(403, "not allowed")
            try:
                data = self.body()
                result = self.act(url.path, data)
            except (ValueError, KeyError, TypeError) as e:
                return self.fail(400, str(e))
            except OSError as e:
                return self.fail(500, str(e))
            if result is None:
                return self.reply(404, "nothing here", "text/plain")
            self.send_json(200, result)

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
            if path == "/api/presence":
                desk.presence = {"round": slug, "item": data.get("item"), "at": time.strftime("%H:%M:%S")}
                return {"ok": True}
            if path == "/api/quit":
                threading.Thread(target=server_ref[0].shutdown, daemon=True).start()
                return {"ok": True}
            return None

        def log_message(self, *_):
            pass

    return Handler


def page(desk):
    """The page, with what it needs to start: its token and the project's settings."""
    boot = {"token": desk.token, "project": proj.settings(desk.root)}
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
    return server


def serve(root, port=None):
    """Runs the desk until it is told to stop (or a day goes by with no page and no command)."""
    server = make_server(root, port)
    desk = server.desk
    url = f"http://127.0.0.1:{server.server_port}/"
    runtime = desk.folder / ".runtime.json"
    proj.write_json(runtime, {"pid": os.getpid(), "port": server.server_port, "token": desk.token, "url": url,
                              "started": time.strftime("%Y-%m-%d %H:%M:%S")})
    stop = threading.Event()
    threading.Thread(target=desk.watch, args=(stop,), daemon=True).start()

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
        server.server_close()
        if (proj.read_json(runtime, {}) or {}).get("pid") == os.getpid():
            runtime.unlink(missing_ok=True)
