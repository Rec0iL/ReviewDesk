"""A review round's checklist: the small part of Markdown checklists use, read into blocks the page
shows.

The format (see `references/checklist.md`):
- an optional header between `---` lines (`title:`, `about:`, `commit:`, `branch:`, `log:`);
- `# Title (about 15 minutes)`, intro paragraphs, bullets and code;
- `## 1. Sections`;
- `- [ ] items`, continued on lines indented under them, each with an optional `{#name}` at the
  end of its first line, and fields on lines of their own: `Setup:`, `Do:`, `Expected:`, `Where:`;
- pictures `![what](files/before.png)`, links, `code`, **bold**, *italic*;
- fenced code blocks, which the page offers to copy and (`bash` and `sh`) to run.
"""
import html
import re
import textwrap
from urllib.parse import quote

ITEM = re.compile(r"^(\s*)- \[( |x|X)\] (.*)$")
BULLET = re.compile(r"^(\s*)[-*] (.*)$")
FENCE = re.compile(r"^(\s*)```(.*)$")
HEADING = re.compile(r"^(#{1,6}) (.*)$")
FIELD = re.compile(r"^(Setup|Do|Expected|Where):\s*(.*)$", re.I)
NAME = re.compile(r"\s*\{#([A-Za-z0-9][\w.-]{0,63})\}\s*$")
RUNNABLE = ("bash", "sh", "shell", "console")


def inline(md, files=""):
    """Inline Markdown as HTML. Pictures and links to files of the round come from `files` (the
    URL of the round's folder); web links open in a new tab; other paths show as paths."""
    out = []
    for k, part in enumerate(md.split("`")):
        if k % 2:
            out.append(f"<code>{html.escape(part)}</code>")
            continue
        t = html.escape(part, quote=False)

        def picture(m):
            alt, src = m.group(1), m.group(2)
            if not src.startswith(("http://", "https://")):
                src = f"{files}/{quote(src.removeprefix('./'))}"
            return f'<img class="pic" src="{html.escape(src)}" alt="{html.escape(alt)}" loading="lazy">'

        def link(m):
            text, url = m.group(1), m.group(2)
            if url.startswith(("http://", "https://")):
                return f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{text}</a>'
            return f'<span class="path" data-path="{html.escape(url)}" title="{html.escape(url)}">{text}</span>'

        t = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", picture, t)
        t = re.sub(r"(?<![\"=])\[([^\]]+)\]\(([^)\s]+)\)", link, t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", t)
        out.append(t)
    return "".join(out)


def indent(line):
    return len(line) - len(line.lstrip(" "))


def take_body(lines, i, ind):
    """The lines from `i` that belong to a list entry at indent `ind`: indented deeper, blank lines
    included when more of it follows. Returns them and where the next block starts."""
    body = []
    while i < len(lines):
        if not lines[i].strip():
            j = i
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and indent(lines[j]) > ind:
                body.extend(lines[i:j])
                i = j
                continue
            break
        if indent(lines[i]) <= ind:
            break
        body.append(lines[i])
        i += 1
    return body, i


def split_entry(first, body):
    """An entry's own text (its first line and the plain lines straight after it), its fields
    (`Setup:` and the like, each going on until the next), and the rest of its body."""
    text, fields, k = [first], [], 0
    while k < len(body) and body[k].strip() and not (BULLET.match(body[k]) or FENCE.match(body[k])):
        line = body[k].strip()
        if m := FIELD.match(line):
            fields.append([m.group(1).lower(), [m.group(2)]])
        elif fields:
            fields[-1][1].append(line)
        else:
            text.append(line)
        k += 1
    rest = textwrap.dedent("\n".join(body[k:])).split("\n") if k < len(body) else []
    return " ".join(text), [(label, " ".join(lines).strip()) for label, lines in fields], rest


def starts_block(line):
    return bool(FENCE.match(line) or ITEM.match(line) or BULLET.match(line) or HEADING.match(line))


class Reader:
    """Reads one checklist: numbers its items and code blocks as it goes."""

    def __init__(self, files):
        self.files = files
        self.codes = {}
        self.names = set()

    def code(self, lang, text):
        code_id = f"c{len(self.codes) + 1}"
        self.codes[code_id] = {"lang": lang, "text": text}
        return {"type": "code", "id": code_id, "lang": lang, "text": text, "runnable": lang.lower() in RUNNABLE}

    def name(self, wanted, fallback):
        """An item's id: its `{#name}` when it has a free one, otherwise its number."""
        chosen = wanted if wanted and wanted not in self.names else fallback
        self.names.add(chosen)
        return chosen

    def blocks(self, lines, prefix, counter):
        """Paragraphs, lists, code and checklist items. Items are numbered `<prefix>.<n>`."""
        blocks, i = [], 0
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue
            if m := FENCE.match(line):
                ind, lang, code = len(m.group(1)), m.group(2).strip(), []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code.append(lines[i][ind:] if not lines[i][:ind].strip() else lines[i].lstrip())
                    i += 1
                blocks.append(self.code(lang, "\n".join(code)))
                i += 1
                continue
            if m := ITEM.match(line):
                body, i = take_body(lines, i + 1, len(m.group(1)))
                first, wanted = m.group(3), None
                if n := NAME.search(first):
                    first, wanted = first[: n.start()], n.group(1)
                md, fields, rest = split_entry(first, body)
                counter[0] += 1
                number = f"{prefix}.{counter[0]}"
                item_id = self.name(wanted, number)
                blocks.append({
                    "type": "item", "id": item_id, "number": number, "md": md, "html": inline(md, self.files),
                    "done": m.group(2) in "xX",
                    "fields": [{"label": label, "html": inline(text, self.files)} for label, text in fields],
                    "children": self.blocks(rest, number, [0]),
                })
                continue
            if m := BULLET.match(line):
                ind, entries = len(m.group(1)), []
                while i < len(lines):
                    bullet = BULLET.match(lines[i])
                    if not bullet or len(bullet.group(1)) != ind or ITEM.match(lines[i]):
                        break
                    body, i = take_body(lines, i + 1, ind)
                    md, _, rest = split_entry(bullet.group(2), body)
                    entries.append({"html": inline(md, self.files), "children": self.blocks(rest, prefix, counter)})
                    while i < len(lines) and not lines[i].strip():
                        i += 1
                blocks.append({"type": "list", "items": entries})
                continue
            if m := HEADING.match(line):
                blocks.append({"type": "heading", "html": inline(m.group(2).strip(), self.files)})
                i += 1
                continue
            para = []
            while i < len(lines) and lines[i].strip() and not starts_block(lines[i]):
                para.append(lines[i].strip())
                i += 1
            blocks.append({"type": "p", "html": inline(" ".join(para), self.files)})
        return blocks


def header(lines):
    """The `key: value` lines between `---` at the top, and the lines after them."""
    meta = {}
    if lines and lines[0].strip() == "---":
        for end in range(1, len(lines)):
            if lines[end].strip() == "---":
                for line in lines[1:end]:
                    key, _, value = line.partition(":")
                    if key.strip() and value.strip():
                        meta[key.strip().lower()] = value.strip()
                return meta, lines[end + 1 :]
    return meta, lines


def parse(text, name, files=""):
    """A checklist as the page shows it: its title, how long it takes, its header, its intro and
    sections, and its code blocks by id (for Run). `files` is the URL of the round's folder."""
    meta, lines = header(text.splitlines())
    title, about = meta.get("title", name), meta.get("about", "")
    if lines and lines[0].startswith("# "):
        heading = lines.pop(0)[2:].strip()
        if m := re.match(r"^(.*?)\s*\(([^)]*)\)$", heading):
            heading, about = m.group(1), about or m.group(2)
        title = meta.get("title", heading)
    # "(about 15 minutes)": the page says "about" itself, in its own language.
    about = re.sub(r"^(?:about|around|roughly|etwa|ca\.|circa|ungefähr)\s+", "", about, flags=re.I)
    chunks = [("", [])]
    for line in lines:
        if line.startswith("## "):
            chunks.append((line[3:].strip(), []))
        else:
            chunks[-1][1].append(line)
    reader = Reader(files)
    sections = []
    for n, (title_md, body) in enumerate(chunks):
        blocks = reader.blocks(body, str(n), [0])
        if title_md or blocks:
            sections.append({"id": str(n), "title": title_md, "html": inline(title_md, files), "blocks": blocks})
    return {"title": title, "about": about, "meta": meta, "sections": sections, "codes": reader.codes}


def items(blocks):
    """Every checklist item in `blocks`, nested ones included, in order."""
    for b in blocks:
        if b["type"] == "item":
            yield b
            yield from items(b["children"])
        elif b["type"] == "list":
            for entry in b["items"]:
                yield from items(entry["children"])


def all_items(doc):
    return [it for s in doc["sections"] for it in items(s["blocks"])]
