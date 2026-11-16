"""Every running desk, seen from each one: the page shows them all in one tab.

Each desk keeps its own port, folder and phone secret. While it runs it leaves a note in a shared
list (`~/.local/state/review-desk/desks/`, or `$REVIEW_DESK_HOME/desks/`): the project's path and
its process. The other desks read that list, ask each desk in it what waits there (`/api/peer`,
a long request that returns as soon as something changes), and tell their own pages: the Desks
list in the sidebar and, for a desk with no tab of its own, its chime and notifications.

A desk's token is in its project's `.runtime.json`, never in the list. Asking a desk doesn't keep
it alive: it still stops by itself after a day with no page of its own and no command.
"""
import http.client
import json
import os
import threading
import time
import zlib
from pathlib import Path

from . import project as proj

POLL = 20          # seconds one `/api/peer` request waits for something to change
SCAN = 1.0         # seconds between looks at the list


def home():
    base = os.environ.get("REVIEW_DESK_HOME")
    if base:
        return Path(base)
    state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state) / "review-desk"


def note_path(root):
    return home() / "desks" / f"{zlib.crc32(str(Path(root).resolve()).encode('utf-8')):08x}.json"


def register(root, pid=None):
    """This desk is running: its note in the list."""
    path = note_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    proj.write_json(path, {"project": str(Path(root).resolve()), "pid": pid or os.getpid()})


def unregister(root, pid=None):
    path = note_path(root)
    if (proj.read_json(path, {}) or {}).get("pid") == (pid or os.getpid()):
        path.unlink(missing_ok=True)


def listing():
    """The desks running now: {project path: its runtime (port, token, url, pid)}. Notes of desks
    that are gone are cleared away."""
    out = {}
    folder = home() / "desks"
    try:
        notes = list(folder.glob("*.json"))
    except OSError:
        return out
    for path in notes:
        note = proj.read_json(path)
        if not isinstance(note, dict) or not note.get("project"):
            continue
        rt = proj.runtime(note["project"])
        if not rt or rt.get("pid") != note.get("pid"):
            try:
                os.kill(int(note.get("pid", 0)), 0)
            except (OSError, ValueError, TypeError):
                path.unlink(missing_ok=True)      # its process is gone
            continue
        out[note["project"]] = rt
    return out


def ask(rt, since, watching, timeout=None):
    """One `/api/peer` request to another desk: what waits there, and its notifications since
    `since` (-1: none, only how it is now)."""
    timeout = POLL if timeout is None else timeout
    conn = http.client.HTTPConnection("127.0.0.1", rt["port"], timeout=timeout + 10)
    try:
        conn.request("GET", f"/api/peer?since={since}&timeout={timeout}&watching={int(watching)}",
                     headers={"Host": f"127.0.0.1:{rt['port']}", "X-Desk-Token": rt.get("token", "")})
        r = conn.getresponse()
        data = r.read()
        if r.status != 200:
            raise OSError(f"{r.status} {r.reason}")
        return json.loads(data)
    finally:
        conn.close()


class Peers:
    """The other running desks, as this desk sees them, kept up to date in the background."""

    def __init__(self, desk):
        self.desk = desk
        self.known = {}        # project path: its last /api/peer answer
        self.threads = {}      # project path: the thread asking it
        self.lock = threading.Lock()
        self.scanned = False
        self.ever = set()      # desks seen since this one started (a restart isn't "new")

    def all(self):
        with self.lock:
            return dict(self.known)

    def run(self, stop):
        while not stop.is_set():
            here = str(self.desk.root)
            for path, rt in listing().items():
                if path == here:
                    continue
                with self.lock:
                    busy = path in self.threads and self.threads[path].is_alive()
                    if not busy:
                        new = self.scanned and path not in self.ever
                        self.ever.add(path)
                        t = threading.Thread(target=self.follow, args=(path, rt, stop, new), daemon=True)
                        self.threads[path] = t
                        t.start()
            self.scanned = True
            stop.wait(SCAN)

    def lead(self, mine=None):
        """Only one tab tells you about a desk without a tab of its own: the desk with the
        lowest port among those with a page."""
        ports = [p["port"] for p in self.all().values() if p.get("pages")]
        if self.desk.local_pages():
            ports.append(self.desk.port)
        return bool(ports) and min(ports) == self.desk.port

    def follow(self, path, rt, stop, announce):
        """Asks one desk again and again; ends when it doesn't answer (stopped)."""
        since, misses = -1, 0
        while not stop.is_set():
            try:
                fresh = proj.runtime(path)
                if fresh and fresh.get("pid") == rt.get("pid"):
                    rt = fresh
                got = ask(rt, since, watching=self.desk.local_pages() > 0)
                misses = 0
            except (OSError, ValueError, http.client.HTTPException):
                misses += 1
                if misses >= 2 or not proj.runtime(path):
                    break
                stop.wait(1)
                continue
            notices = got.pop("notices", [])
            serial = got.pop("serial", since)
            with self.lock:
                before = self.known.get(path)
                self.known[path] = got
            if before != got:
                self.desk.broadcast(type="desks")
            if announce and since == -1 and not got.get("pages") and self.lead():
                self.desk.broadcast(type="peer", what="desk", project=got["project"], url=got["url"],
                                    title=got["title"], notify={"title": "", "body": got["title"]})
            if since != -1 and not got.get("pages") and self.lead():
                for n in notices:
                    self.desk.broadcast(type="peer", project=got["project"], url=got["url"], title=got["title"], **n)
            since = serial
        with self.lock:
            gone = self.known.pop(path, None)
            self.threads.pop(path, None)
        if gone:
            self.desk.broadcast(type="desks")
