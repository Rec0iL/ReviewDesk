"""What you add to an answer, and what the page may show you from the project.

- Attachments (screenshots, recordings, log lines, any file) land in the round's `files/`, named
  after their item so Claude can tell them apart (`1-2-screenshot.png`).
- Log lines come only from the log files the checklist names (`log:` in its header).
- The viewer shows text files inside the project, and the commit the checklist names.
"""
import os
import re
import subprocess
from pathlib import Path

FILE_KINDS = ("screenshot", "recording", "log", "file")
MAX_UPLOAD = 300 * 1024 * 1024
MAX_VIEW = 1024 * 1024
CHUNK = 1024 * 1024
COMMIT = re.compile(r"^[0-9a-fA-F]{4,40}$")


def safe_part(text, fallback, limit=60):
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")[:limit]
    return cleaned or fallback


def file_name(folder, item_id, kind, original):
    """A free name in `folder` for an attachment: item, then kind (or the file's own name)."""
    stem, ext = os.path.splitext(os.path.basename(original or ""))
    ext = ("." + safe_part(ext.lstrip("."), "", 8).lower()) if ext.strip(".") else ""
    base = f"{safe_part(item_id.replace('.', '-'), 'item')}-{kind if kind != 'file' else safe_part(stem, 'file')}"
    name, n = f"{base}{ext}", 2
    while (folder / name).exists():
        name, n = f"{base}-{n}{ext}", n + 1
    return name


def save_upload(stream, length, folder, item_id, kind, original):
    """Writes `length` bytes of `stream` to a new attachment in `folder`. Returns its name."""
    if kind not in FILE_KINDS:
        raise ValueError(f"an attachment is a {', '.join(FILE_KINDS)}")
    if not 0 < length <= MAX_UPLOAD:
        raise ValueError("an attachment is up to 300 MB")
    folder.mkdir(parents=True, exist_ok=True)
    name = file_name(folder, item_id, kind, original)
    tmp = folder / f".{name}.part"
    left = length
    try:
        with open(tmp, "wb") as f:
            while left > 0:
                chunk = stream.read(min(CHUNK, left))
                if not chunk:
                    raise ValueError("the upload stopped half-way")
                f.write(chunk)
                left -= len(chunk)
        os.replace(tmp, folder / name)
    finally:
        tmp.unlink(missing_ok=True)
    return name


def log_sources(root, doc):
    """The log files a checklist names (`log: path, path`), as given and where they are."""
    named = [p.strip() for p in doc.get("meta", {}).get("log", "").split(",") if p.strip()]
    out = []
    for given in named:
        path = Path(os.path.expanduser(given))
        out.append({"name": given, "path": path if path.is_absolute() else Path(root) / path})
    return out


def tail(path, lines=400, window=512 * 1024):
    """The last `lines` lines of a text file."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - window))
        data = f.read()
    text = data.decode("utf-8", errors="replace").splitlines()
    if size > window and text:
        text = text[1:]  # most likely cut in the middle
    return text[-lines:]


def source(root, rel):
    """A text file inside the project, for the viewer."""
    rel = rel.strip().removeprefix("./")
    base = Path(root).resolve()
    target = (base / os.path.expanduser(rel)).resolve()
    if base != target and base not in target.parents:
        raise ValueError("only files inside the project")
    if not target.is_file():
        raise ValueError(f"no file {rel}")
    if target.stat().st_size > MAX_VIEW:
        raise ValueError(f"{rel} is too big to show here")
    data = target.read_bytes()
    if b"\0" in data[:8192]:
        raise ValueError(f"{rel} isn't text")
    return {"path": str(target.relative_to(base)), "text": data.decode("utf-8", errors="replace")}


def commit(root, ref):
    """What a commit changed: its message, the files and the diff."""
    if not COMMIT.match(ref or ""):
        raise ValueError("a commit is its hash")
    out = subprocess.run(["git", "-C", str(root), "show", "--stat", "--patch", "--format=fuller", ref],
                         capture_output=True, text=True, errors="replace", timeout=15)
    if out.returncode != 0:
        raise ValueError(out.stderr.strip() or f"no commit {ref}")
    text = out.stdout
    if len(text) > MAX_VIEW:
        text = text[:MAX_VIEW] + "\n… (cut here: the rest is too long to show)"
    return {"path": ref, "text": text}
