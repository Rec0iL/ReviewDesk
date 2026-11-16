"""A project's review desk on disk: the `.review/` folder at the project's root, kept out of git
through `.git/info/exclude` (no tracked file changes), its settings, the port its page uses (the
same every time, so bookmarks and the page's memory of where you were survive restarts), and what
the running page left for the command to find it.
"""
import json
import os
import re
import secrets
import subprocess
import zlib
from pathlib import Path

REVIEW = ".review"
EXCLUDE = "/.review/"
FIRST_PORT, PORTS = 41000, 900
DEFAULT_ACCENT = "#55d6ad"
COLOUR = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")


def git(root, *args):
    """A git command's output in `root`, or None outside a repository (or without git)."""
    try:
        out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def find_root(start=None):
    """The project a command means: the git repository around `start` (the current folder by
    default), or that folder itself outside one. From a linked git worktree with no `start`
    given, the main checkout: sessions working in worktrees share its desk."""
    explicit = start is not None
    start = Path(start or os.getcwd()).resolve()
    top = git(start, "rev-parse", "--show-toplevel")
    if not top:
        return start
    top = Path(top).resolve()
    return (None if explicit else main_checkout(top)) or top


def main_checkout(top):
    """For a linked git worktree: the main checkout it belongs to (None for anything else)."""
    common, gitdir = git(top, "rev-parse", "--git-common-dir"), git(top, "rev-parse", "--git-dir")
    if not common or not gitdir:
        return None
    absolute = lambda p: (Path(p) if Path(p).is_absolute() else Path(top) / p).resolve()
    common, gitdir = absolute(common), absolute(gitdir)
    if common == gitdir or common.name != ".git":
        return None
    return common.parent


def default_owner(root, start=None):
    """Who a session listens as on `root`'s desk when it doesn't say (`--as`): $REVIEW_DESK_AS
    (set but empty: no name), or, in a linked git worktree of `root`, the worktree's folder name;
    "" (no owner, the plain case) otherwise, also on any other project's desk."""
    if "REVIEW_DESK_AS" in os.environ:
        return os.environ["REVIEW_DESK_AS"].strip()
    top = git(Path(start or os.getcwd()).resolve(), "rev-parse", "--show-toplevel")
    if not top:
        return ""
    main = main_checkout(Path(top).resolve())
    return Path(top).name if main and main == Path(root).resolve() else ""


def review_dir(root):
    return Path(root) / REVIEW


def ensure(root):
    """`.review/` exists and git leaves it alone. Returns the folder."""
    folder = review_dir(root)
    folder.mkdir(exist_ok=True)
    exclude = git(root, "rev-parse", "--git-path", "info/exclude")
    if exclude:
        path = Path(exclude) if Path(exclude).is_absolute() else Path(root) / exclude
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        if EXCLUDE not in (line.strip() for line in lines):
            with open(path, "a", encoding="utf-8") as f:
                if lines and lines[-1].strip():
                    f.write("\n")
                f.write(f"# Review Desk's reviews\n{EXCLUDE}\n")
    return folder


def stable_port(root):
    """The port this project's page asks for first: the same for the same folder every time."""
    return FIRST_PORT + zlib.crc32(str(Path(root).resolve()).encode("utf-8")) % PORTS


def write_json(path, data):
    """Writes `data` to `path` atomically (a crash never leaves half a file)."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def settings(root):
    """The desk's settings (`desk.json`): the project's title and accent colour."""
    data = read_json(review_dir(root) / "desk.json", {}) or {}
    return {
        "title": data.get("title") or Path(root).name,
        "accent": data["accent"] if COLOUR.match(str(data.get("accent", ""))) else DEFAULT_ACCENT,
    }


def save_settings(root, **changes):
    path = review_dir(root) / "desk.json"
    data = read_json(path, {}) or {}
    data.update({k: v for k, v in changes.items() if v is not None})
    write_json(path, data)
    return settings(root)


def token(root):
    """The page's secret: kept in `.review/.secret` so a tab left open finds the desk again after
    a restart."""
    path = review_dir(root) / ".secret"
    try:
        kept = path.read_text(encoding="utf-8").strip()
        if len(kept) >= 32:
            return kept
    except OSError:
        pass
    fresh = secrets.token_urlsafe(32)
    path.write_text(fresh + "\n", encoding="utf-8")
    path.chmod(0o600)
    return fresh


def runtime(root):
    """What the running page left (`.runtime.json`: port, pid, token), when its process still
    runs."""
    data = read_json(review_dir(root) / ".runtime.json")
    if not data:
        return None
    try:
        os.kill(int(data["pid"]), 0)
    except (OSError, KeyError, ValueError):
        return None
    return data
