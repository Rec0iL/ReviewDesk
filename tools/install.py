#!/usr/bin/env python3
"""Installs Review Desk for Claude Code.

    python3 tools/install.py            links this folder as the skill `review-desk` and puts a
                                        `review-desk` command in ~/.local/bin
    python3 tools/install.py --hook     also adds a session-start hook to ~/.claude/settings.json
                                        that tells Claude when answers wait (only when you want it)
    python3 tools/install.py --remove   takes all of it out again (a copy of settings.json stays)

Nothing is copied: the skill and the command point at this folder, so a `git pull` here updates
them.
"""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
HOME = Path.home()
SKILL = HOME / ".claude" / "skills" / "review-desk"
COMMAND = HOME / ".local" / "bin" / "review-desk"
SETTINGS = HOME / ".claude" / "settings.json"
SCRIPT = HERE / "scripts" / "review_desk.py"
HOOK = f"{COMMAND} status --hook"


def link(path, target):
    """`path` points at `target`; an existing link elsewhere or a real file stays and is reported."""
    if path.is_symlink():
        if path.resolve() == target.resolve():
            print(f"ok      {path} → {target}")
            return True
        print(f"left    {path} points at {path.resolve()}, not here; remove it first if you want this one")
        return False
    if path.exists():
        print(f"left    {path} exists and isn't a link; move it away first if you want this one")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target)
    print(f"linked  {path} → {target}")
    return True


def unlink(path, target):
    if path.is_symlink() and path.resolve() == target.resolve():
        path.unlink()
        print(f"removed {path}")


def ours(entry):
    return any("review-desk" in h.get("command", "") and "status --hook" in h.get("command", "")
               for h in entry.get("hooks", []))


def read_settings():
    if not SETTINGS.exists():
        return {}
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except ValueError as e:
        sys.exit(f"{SETTINGS} isn't valid JSON ({e}); fix it first, nothing was changed")


def write_settings(data):
    if SETTINGS.exists():
        stamp, n = time.strftime("%Y%m%d-%H%M%S"), 1
        backup = SETTINGS.with_name(f"settings.json.bak-review-desk-{stamp}")
        while backup.exists():
            n += 1
            backup = SETTINGS.with_name(f"settings.json.bak-review-desk-{stamp}-{n}")
        shutil.copy2(SETTINGS, backup)
        print(f"copy    {backup}")
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS.with_name(".settings.json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(SETTINGS)


def add_hook():
    data = read_settings()
    starts = data.setdefault("hooks", {}).setdefault("SessionStart", [])
    if any(ours(e) for e in starts):
        print(f"ok      the session-start hook is in {SETTINGS}")
        return
    starts.append({"hooks": [{"type": "command", "command": HOOK, "timeout": 10}]})
    write_settings(data)
    print(f"added   the session-start hook to {SETTINGS}")


def remove_hook():
    data = read_settings()
    starts = data.get("hooks", {}).get("SessionStart", [])
    kept = [e for e in starts if not ours(e)]
    if len(kept) == len(starts):
        return
    if kept:
        data["hooks"]["SessionStart"] = kept
    else:
        del data["hooks"]["SessionStart"]
        if not data["hooks"]:
            del data["hooks"]
    write_settings(data)
    print(f"removed the session-start hook from {SETTINGS}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hook", action="store_true", help="also add the session-start hook")
    parser.add_argument("--remove", action="store_true", help="take the skill, the command and the hook out")
    args = parser.parse_args()
    if args.remove:
        unlink(SKILL, HERE)
        unlink(COMMAND, SCRIPT)
        remove_hook()
        return
    if sys.version_info < (3, 10):
        sys.exit("Review Desk needs Python 3.10 or newer")
    SCRIPT.chmod(SCRIPT.stat().st_mode | 0o111)
    link(SKILL, HERE)
    link(COMMAND, SCRIPT)
    if args.hook:
        add_hook()
    if str(COMMAND.parent) not in os.environ.get("PATH", "").split(os.pathsep):
        print(f"note    {COMMAND.parent} isn't on PATH; Claude can call {SCRIPT} with python3 instead")


if __name__ == "__main__":
    main()
