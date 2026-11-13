"""Is there a newer Review Desk? The skill is a git clone; this looks at its upstream.

- `notice()` is what the session-start hook and `review-desk status` say: one line when the clone
  is behind its upstream, nothing otherwise. It never waits on the network: at most once a day it
  starts a quiet `git fetch` in the background, and the next session sees what it brought.
- `update()` pulls the new version (fast-forward only), when the user asks for it.
- `REVIEW_DESK_NO_UPDATE_CHECK=1` turns the check off.
"""
import json
import os
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DAY = 24 * 3600
fetching = None  # the background fetch this process started, if any


def cache_file():
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "review-desk" / "update-check.json"


def git(*args, timeout=5):
    """A git command's output in the skill's folder, or None."""
    try:
        out = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def disabled():
    return bool(os.environ.get("REVIEW_DESK_NO_UPDATE_CHECK"))


def fetch_soon(now=None):
    """Starts a background `git fetch` when the last one is a day old. Returns whether it did."""
    global fetching
    now = time.time() if now is None else now
    path = cache_file()
    try:
        last = json.loads(path.read_text(encoding="utf-8")).get("checked", 0)
    except (OSError, ValueError):
        last = 0
    if now - last < DAY or not git("rev-parse", "--abbrev-ref", "@{u}"):
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"checked": now}), encoding="utf-8")
        fetching = subprocess.Popen(["git", "-C", str(REPO), "fetch", "--quiet"], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
                                    env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except OSError:
        return False
    return True


def behind():
    """How many commits the clone's upstream has that the clone doesn't (0 without an upstream)."""
    if not git("rev-parse", "--abbrev-ref", "@{u}"):
        return 0
    count = git("rev-list", "--count", "HEAD..@{u}")
    return int(count) if count and count.isdigit() else 0


def notice():
    """One line when a newer Review Desk is waiting, else None."""
    if disabled():
        return None
    fetch_soon()
    n = behind()
    if not n:
        return None
    return (f"Review Desk has an update ({n} new commit{'s' if n != 1 else ''}). "
            f"Tell the user; `review-desk update` gets it once they agree.")


def update():
    """Pulls the new version (fast-forward only). Returns (ok, what happened)."""
    if not git("rev-parse", "--abbrev-ref", "@{u}"):
        return False, f"{REPO} has no upstream to update from."
    if git("status", "--porcelain", "--untracked-files=no"):
        return False, f"{REPO} has local changes; update it by hand (git pull) after keeping or dropping them."
    before = git("rev-parse", "--short", "HEAD")
    if git("fetch", "--quiet", timeout=60) is None:
        return False, "Couldn't reach the upstream (offline?)."
    try:
        out = subprocess.run(["git", "-C", str(REPO), "merge", "--ff-only", "@{u}"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    if out.returncode != 0:
        return False, (out.stderr.strip() or "The update can't be applied as a fast-forward; update it by hand.")
    after = git("rev-parse", "--short", "HEAD")
    if before == after:
        return True, "Review Desk is up to date."
    log = git("log", "--oneline", "--no-decorate", f"{before}..{after}") or ""
    return True, (f"Review Desk updated ({before} → {after}):\n{log}\n"
                  "A running desk keeps the old version until `review-desk stop` and `start`; open pages offer a reload.")
