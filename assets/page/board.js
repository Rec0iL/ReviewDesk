"use strict";
// Review Desk's board: the Ideas board (every idea of every round, with Claude's word on it),
// Claude's question cards, and the summary to copy. Loaded before desk.js; uses its helpers when
// called.

const IDEA_STATES = ["new", "planned", "done", "declined"];
const DRAFTS = "review-desk:drafts";

/** Markdown as plain words (for the board and the summary). */
function plain(md) {
  return String(md || "")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/(^|[^\w*])\*(\S(?:.*?\S)?)\*(?![\w*])/g, "$1$2")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/[,:;]$/, "");
}

/** Every checklist item of a round, nested ones included, in order. */
function allItems(doc) {
  const out = [];
  const walk = (blocks) => {
    for (const b of blocks) {
      if (b.type === "item") {
        out.push(b);
        walk(b.children);
      } else if (b.type === "list") b.items.forEach((entry) => walk(entry.children));
    }
  };
  doc.sections.forEach((s) => walk(s.blocks));
  return out;
}

// -- the Ideas board ----------------------------------------------------------------------------

async function loadIdeas() {
  try {
    S.ideas = (await api("/api/ideas")).ideas;
  } catch {
    S.ideas = S.ideas || [];
  }
}

async function showIdeas() {
  S.view = "ideas";
  remember({ view: "ideas" });
  await loadIdeas();
  renderSide();
  renderIdeas();
  scroller().scrollTop = 0;
}

function renderIdeas() {
  const main = $("main");
  const filter = S.ideaFilter || "all";
  const wrap = el("div", "wrap board");
  const head = el("div", "head");
  const counts = { all: S.ideas.length };
  for (const s of IDEA_STATES) counts[s] = S.ideas.filter((i) => i.status === s).length;
  head.innerHTML = `<div class="row"><div class="titles"><h1>${esc(t("ideas"))}</h1>
    <div class="meta"><span>${esc(t("ideas.about"))}</span></div></div></div>`;
  const chips = el("div", "filters");
  for (const f of ["all", ...IDEA_STATES]) {
    const b = button("chip-button", `${esc(t(f === "all" ? "ideas.all" : "idea." + f))}<b>${counts[f]}</b>`, () => {
      S.ideaFilter = f;
      renderIdeas();
    });
    b.setAttribute("aria-pressed", String(f === filter));
    chips.append(b);
  }
  head.append(chips);
  wrap.append(head);
  wrap.append(ideaForm());
  const shown = S.ideas.filter((i) => filter === "all" || i.status === filter);
  if (!shown.length) {
    wrap.append(el("div", "empty-state small", `<div class="mark">${icon("idea")}</div><p>${esc(t(S.ideas.length ? "ideas.none.filter" : "ideas.none"))}</p>`));
  }
  for (const i of shown) {
    const card = el("article", `idea-card ${i.status}`);
    const top = el("div", "top");
    top.append(el("span", `chip ${i.status}`, esc(t("idea." + i.status))));
    if (i.board) {
      top.append(el("span", "where", esc(t("ideas.general"))));
      top.append(el("span", `where ${i.seen ? "read" : ""}`, `· ${esc(t(i.seen ? "ideas.read" : "ideas.unread"))}`));
      top.append(Object.assign(button("icon-button remove-idea", icon("remove"), () => removeIdea(i.id), t("ideas.remove")), { style: "margin-left:auto" }));
    } else {
      const where = i.number ? `${i.number} ${plain(i.item_text)}` : t("overall.title");
      top.append(button("link where", `${esc(i.round_title)} · ${esc(where)}`, () => goTo(i.round, i.item)));
    }
    card.append(top, ideaText(i, i.id, i.text, i.editable, "said"));
    for (const r of i.replies) {
      const mine = r.from === "you";
      const reply = el("div", `reply ${mine ? "you" : ""}`, mine ? `<span class="avatar you">${icon("reply")}</span>` : `<span class="avatar">C</span>`);
      reply.append(ideaText(i, r.id, r.text, r.editable, "grow"));
      card.append(reply);
    }
    if (i.replies.some((r) => r.from !== "you")) card.append(ideaReplyBox(i));
    wrap.append(card);
  }
  const key = document.activeElement && document.activeElement.dataset && document.activeElement.dataset.key;
  main.replaceChildren(wrap);
  if (key) wrap.querySelector(`[data-key="${CSS.escape(key)}"]`)?.focus();
}

/**
 * An idea's words, or your own message on it. Yours can be changed until Claude has been given
 * them (the pencil); then the words turn into a box with Save and Cancel.
 */
function ideaText(i, target, current, editable, cls) {
  const key = `${i.round}|${i.item}|${i.id}|${target}`;
  const wrap = el("div", cls);
  if (S.ideaEditing !== key) {
    wrap.append(Object.assign(el("span", "words"), { textContent: current }));
    if (editable) {
      wrap.append(button("icon-button edit-idea", icon("edit"), () => {
        S.ideaEditing = key;
        S.ideaEditText = undefined;
        renderIdeas();
        document.querySelector(`[data-key="edit:${CSS.escape(key)}"]`)?.focus();
      }, t("ideas.edit")));
    }
    return wrap;
  }
  const box = el("textarea");
  box.rows = 2;
  box.dataset.key = `edit:${key}`;
  box.value = S.ideaEditText ?? current;
  box.oninput = () => (S.ideaEditText = box.value);
  const done = () => { S.ideaEditing = null; S.ideaEditText = undefined; };
  const save = async () => {
    const text = box.value.trim();
    if (!text) { box.focus(); return; }
    try {
      await api("/api/idea/edit", { round: i.round, item: i.item, id: i.id, target, text });
      done();
    } catch (e) {
      toast(t("ask.failed", { e: e.message }));
      done();
    }
    await loadIdeas();
    renderIdeas();
  };
  box.onkeydown = (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save(); }
    if (e.key === "Escape") { done(); renderIdeas(); }
  };
  wrap.append(box, el("div", "edit-row"));
  $(".edit-row", wrap).append(
    button("primary", esc(t("ideas.save")), save),
    button("quiet", esc(t("ideas.cancel")), () => { done(); renderIdeas(); }),
  );
  return wrap;
}

/** Your answer to what Claude said about an idea; Claude reads it with the next hand-back. */
function ideaReplyBox(i) {
  const key = `${i.round}|${i.item}|${i.id}`;
  S.ideaReplies = S.ideaReplies || {};
  const row = el("div", "idea-reply");
  const box = el("textarea");
  box.rows = 1;
  box.dataset.key = key;
  box.placeholder = t("ideas.reply.ph");
  box.value = S.ideaReplies[key] || "";
  const send = async () => {
    const text = (S.ideaReplies[key] || "").trim();
    if (!text) { box.focus(); return; }
    try {
      await api("/api/idea/reply", { round: i.round, item: i.item, id: i.id, text, reply_id: newId() });
      S.ideaReplies[key] = "";
      await loadIdeas();
      renderIdeas();
      toast(t("ideas.reply.sent"));
    } catch (e) {
      toast(t("ask.failed", { e: e.message }));
    }
  };
  box.oninput = () => (S.ideaReplies[key] = box.value);
  box.onkeydown = (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); }
  };
  row.append(box, button("quiet", `${icon("reply")}<span>${esc(t("ideas.reply"))}</span>`, send));
  return row;
}

/** The box for a new idea: it belongs to no review, and Claude reads it with the next hand-back. */
function ideaForm() {
  const form = el("div", "idea-add");
  const box = el("textarea", "idea-text");
  box.dataset.key = "new-idea";
  box.rows = 2;
  box.placeholder = t("ideas.add.ph");
  box.value = S.ideaDraft || "";
  box.oninput = () => (S.ideaDraft = box.value);
  box.onkeydown = (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); addIdea(); }
  };
  form.append(box, button("primary", `${icon("idea")}<span>${esc(t("ideas.add"))}</span>`, addIdea));
  return form;
}

async function addIdea() {
  const text = (S.ideaDraft || "").trim();
  if (!text) { document.querySelector(".idea-text")?.focus(); return; }
  try {
    await api("/api/board/idea", { id: newId(), text });
    S.ideaDraft = "";
    await loadIdeas();
    renderSide();
    renderIdeas();
    toast(t("ideas.added"));
  } catch (e) {
    toast(t("ask.failed", { e: e.message }));
  }
}

async function removeIdea(id) {
  try {
    await api("/api/board/idea", { id, delete: true });
    await loadIdeas();
    renderSide();
    renderIdeas();
  } catch (e) {
    toast(t("ask.failed", { e: e.message }));
  }
}

// -- Claude's question cards ----------------------------------------------------------------------

async function loadQuestions() {
  try {
    S.allQuestions = (await api("/api/questions")).questions;
  } catch {
    S.allQuestions = S.allQuestions || [];
  }
  sessionQuestions();
  renderAsks();
}

function renderAsks() {
  let pill = document.querySelector(".asks-pill");
  if (!S.questions.length) {
    pill?.remove();
    document.querySelector("dialog.ask")?.close();
  } else {
    if (!pill) {
      pill = button("asks-pill primary", "", openAsk);
      document.body.append(pill);
    }
    pill.innerHTML = `${icon("question")}<span>${esc(t("asks.pill", { n: S.questions.length }))}</span>`;
  }
  renderSide();
}

function drafts() {
  return stored(DRAFTS);
}

function openAsk() {
  const set = S.questions[0];
  if (!set) return;
  document.querySelector("dialog.ask")?.close();
  const all = drafts();
  const draft = all[set.id] || set.questions.map(() => ({ chosen: [], other: "", note: "" }));
  const keep = () => store(DRAFTS, { ...drafts(), [set.id]: draft });

  const d = dialog("ask");
  const head = el("header", null, `<h2>${esc(set.title || t("asks.title"))}</h2>`);
  if (S.questions.length > 1) head.append(el("span", "count", esc(t("of", { a: 1, b: S.questions.length }))));
  head.append(button("quiet close", icon("remove"), () => d.close(), t("ask.later")));
  const body = el("div", "ask-body");
  const progress = el("span", "hint");
  const send = button("primary", esc(t("ask.send")), submit);

  set.questions.forEach((q, n) => {
    const a = draft[n];
    const box = el("fieldset", "q");
    box.append(el("legend", null, `${q.header ? `<span class="chip">${esc(q.header)}</span>` : ""}<span>${esc(q.question)}</span>`));
    if (q.multiSelect) box.append(el("div", "how", esc(t("ask.many"))));
    const kind = q.multiSelect ? "checkbox" : "radio";
    const name = `${set.id}-${n}`;
    for (const o of q.options) {
      const label = el("label", "opt");
      const input = el("input");
      Object.assign(input, { type: kind, name, value: o.label, checked: a.chosen.includes(o.label) });
      input.onchange = () => {
        a.chosen = [...box.querySelectorAll(`input[name="${CSS.escape(name)}"]:checked`)].map((x) => x.value).filter((v) => v !== "\u0000other");
        if (!q.multiSelect && input.checked) a.other = "";
        sync();
      };
      const words = el("span", "words", `<b>${esc(o.label)}</b>${o.description ? `<small>${esc(o.description)}</small>` : ""}`);
      label.append(input, words);
      box.append(label);
    }
    const other = el("label", "opt other");
    const otherRadio = el("input");
    Object.assign(otherRadio, { type: kind, name, value: "\u0000other", checked: Boolean(a.other) });
    const otherText = el("input", "other-text");
    Object.assign(otherText, { type: "text", value: a.other, placeholder: t("ask.other") });
    otherText.oninput = () => {
      a.other = otherText.value;
      otherRadio.checked = Boolean(a.other.trim());
      if (!q.multiSelect && a.other.trim()) {
        a.chosen = [];
        box.querySelectorAll(`input[name="${CSS.escape(name)}"]`).forEach((x) => x !== otherRadio && (x.checked = false));
      }
      sync();
    };
    otherRadio.onchange = () => {
      if (otherRadio.checked) otherText.focus();
      if (!q.multiSelect) a.chosen = [];
      sync();
    };
    other.append(otherRadio, otherText);
    box.append(other);
    const note = el("textarea", "note small");
    Object.assign(note, { value: a.note, placeholder: t("ask.note") });
    note.oninput = () => {
      a.note = note.value;
      autosize(note);
      keep();
    };
    box.append(note);
    body.append(box);
  });

  function answered() {
    return draft.filter((a) => a.chosen.length || a.other.trim()).length;
  }

  function sync() {
    keep();
    progress.textContent = t("ask.progress", { a: answered(), b: set.questions.length });
    send.disabled = answered() < set.questions.length;
  }

  async function submit() {
    send.disabled = true;
    try {
      await api("/api/answer", { id: set.id, answers: draft });
      const rest = drafts();
      delete rest[set.id];
      store(DRAFTS, rest);
      d.close();
      toast(S.state && S.state.listening ? t("handed.listening") : t("ask.sent"));
      await loadQuestions();
      if (S.questions.length) openAsk();
    } catch (e) {
      toast(t("ask.failed", { e: e.message }));
      send.disabled = false;
    }
  }

  const foot = el("footer");
  foot.append(progress, button("quiet", esc(t("ask.later")), () => d.close()), send);
  d.append(head, body, foot);
  d.showModal();
  sync();
}

// -- the summary to copy ------------------------------------------------------------------------

function summaryText() {
  const { doc, state } = S.round;
  const c = counts();
  const items = allItems(doc);
  const out = [`## ${doc.title}${state.round > 1 ? ` · ${t("round", { n: state.round })}` : ""}`, ""];
  out.push([t("of", { a: c.total - c.open, b: c.total }), ...VERDICTS.filter((v) => c[v]).map((v) => `${c[v]} ${t("count." + v)}`)].join(" · "), "");
  for (const v of ["change", "partly", "blocked", "skipped"]) {
    const these = items.filter((it) => state.items[it.id] && state.items[it.id].verdict === v);
    if (!these.length) continue;
    out.push(`**${t(v)}**`);
    for (const it of these) {
      const a = state.items[it.id];
      const note = a.note.trim().replace(/\s*\n\s*/g, " ");
      out.push(`- ${it.number} ${plain(it.md)}${a.severity ? ` (${t(a.severity)})` : ""}${note ? ` · ${note}` : ""}`);
    }
    out.push("");
  }
  const works = items.filter((it) => state.items[it.id] && state.items[it.id].verdict === "works");
  if (works.length) out.push(`**${t("works")}:** ${works.map((it) => it.number).join(", ")}`, "");
  for (const kind of ["question", "idea"]) {
    const said = [];
    for (const it of [...items, { id: "overall", number: "" }]) {
      const thread = it.id === "overall" ? state.overall.messages : (state.items[it.id] || {}).messages || [];
      for (const m of thread) {
        if (m.from !== "claude" && m.kind === kind && m.text.trim()) said.push(`- ${it.number ? it.number + " " : ""}${m.text.trim().replace(/\s*\n\s*/g, " ")}`);
      }
    }
    if (said.length) out.push(`**${t(kind === "question" ? "summary.questions" : "summary.ideas")}**`, ...said, "");
  }
  if (state.overall.note.trim()) out.push(`**${t("overall.title")}**`, state.overall.note.trim(), "");
  return out.join("\n").trim() + "\n";
}

async function copySummary() {
  const text = summaryText();
  try {
    await navigator.clipboard.writeText(text);
    toast(t("summary.copied"));
  } catch {
    viewer(t("summary.copy"), text);
  }
}
