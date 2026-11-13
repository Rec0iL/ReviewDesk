"""Run buttons: a code block of a checklist, run in the project's folder after you click Run on
the page. Only what the checklist says is run, never what a request sends; output streams to the
page as it comes; Stop ends the command and everything it started.
"""
import collections
import os
import signal
import subprocess
import threading
import time

from . import markdown

KEEP = 5000        # output lines kept per run
EVERY = 0.15       # seconds between output batches to the page


class Runs:
    def __init__(self, root, rounds, broadcast):
        self.root = root
        self.rounds = rounds
        self.broadcast = broadcast
        self.runs = {}
        self.lock = threading.Lock()
        self.count = 0

    def start(self, slug, code_id):
        """Runs code block `code_id` of round `slug` (the one already running, if it is)."""
        doc = self.rounds.doc(slug)
        code = doc["codes"].get(code_id)
        if not code:
            raise ValueError(f"no code block {code_id!r} in {slug}")
        if code["lang"].lower() not in markdown.RUNNABLE:
            raise ValueError("only bash and sh blocks run")
        with self.lock:
            for run in self.runs.values():
                if run["round"] == slug and run["code"] == code_id and run["status"] == "running":
                    return self.public(run)
            self.count += 1
            env = dict(os.environ, TERM="dumb", NO_COLOR="1", PYTHONUNBUFFERED="1")
            proc = subprocess.Popen(["bash", "-c", code["text"]], cwd=self.root, env=env, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
                                    text=True, errors="replace", bufsize=1)
            run = {"id": f"r{self.count}", "round": slug, "code": code_id, "status": "running", "exit": None,
                   "started": time.strftime("%H:%M:%S"), "lines": collections.deque(maxlen=KEEP),
                   "pending": [], "proc": proc}
            self.runs[run["id"]] = run
            started = self.public(run)  # what started, before it can finish
        self.broadcast(type="run", id=run["id"], round=slug, code=code_id, status="running", started=run["started"])
        threading.Thread(target=self.read, args=(run,), daemon=True).start()
        threading.Thread(target=self.pump, args=(run,), daemon=True).start()
        return started

    def read(self, run):
        for line in run["proc"].stdout:
            line = line.rstrip("\n")
            with self.lock:
                run["lines"].append(line)
                run["pending"].append(line)
        run["proc"].stdout.close()
        code = run["proc"].wait()
        with self.lock:
            run["exit"] = code
            run["status"] = "stopped" if run.get("stopping") else "done"

    def pump(self, run):
        """Hands the page new output a few times a second, and the end."""
        while True:
            time.sleep(EVERY)
            with self.lock:
                lines, run["pending"] = run["pending"], []
                finished = run["status"] != "running"
            if lines:
                self.broadcast(type="run", id=run["id"], round=run["round"], code=run["code"], lines=lines)
            if finished:
                self.broadcast(type="run", id=run["id"], round=run["round"], code=run["code"],
                               status=run["status"], exit=run["exit"])
                return

    def stop(self, run_id):
        run = self.runs.get(run_id)
        if not run:
            raise ValueError(f"no run {run_id!r}")
        if run["status"] == "running":
            run["stopping"] = True
            kill(run["proc"])
        return self.public(run)

    def stop_all(self):
        for run in list(self.runs.values()):
            if run["status"] == "running":
                run["stopping"] = True
                kill(run["proc"], wait=0.5)

    def of(self, slug):
        """The runs of a round, newest of each code block, for a page that (re)opens it."""
        with self.lock:
            latest = {}
            for run in self.runs.values():
                if run["round"] == slug:
                    latest[run["code"]] = run
            return [self.public(run, lines=True) for run in latest.values()]

    @staticmethod
    def public(run, lines=False):
        out = {k: run[k] for k in ("id", "round", "code", "status", "exit", "started")}
        if lines:
            out["lines"] = list(run["lines"])
        return out


def kill(proc, wait=3.0):
    """Ends a command and what it started: politely, then for sure."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return

    def finish():
        try:
            proc.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    threading.Thread(target=finish, daemon=True).start()
