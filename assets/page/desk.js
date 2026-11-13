"use strict";
// Review Desk's page: the project's reviews in the sidebar, one review open with its items, your
// answers saved as you type (and kept until the desk has them), everything kept live with the
// desk through server-sent events.

const BOOT = window.BOOT || { token: "", project: {} };
const CLIENT = Math.random().toString(36).slice(2, 10);
const VERDICTS = ["works", "partly", "change", "blocked", "skipped"];
const SEVERITIES = ["cosmetic", "annoying", "broken"];
const ICONS = {
  works: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  partly: '<circle cx="12" cy="12" r="7.5"/><path d="M12 4.5a7.5 7.5 0 0 1 0 15z" fill="currentColor"/>',
  change: '<path d="M7 7l10 10M17 7L7 17"/>',
  blocked: '<circle cx="12" cy="12" r="7.5"/><path d="M6.8 17.2l10.4-10.4"/>',
  skipped: '<path d="M5 17l5-5-5-5"/><path d="M13 17l5-5-5-5"/>',
};
const LAST = "review-desk:last";
const LANG = "review-desk:lang";

const S = {
  lang: pickLang(),
  state: null,          // the project and its rounds (the sidebar)
  current: null,        // the open round's slug
  round: null,          // the open round: {doc, state}
  outbox: new Map(),    // answers the desk doesn't have yet: "round\nitem" -> {round, id, fields}
  flushTimer: null,
  retryTimer: null,
  flushing: false,
  again: false,
  failed: null,
  live: false,
};

// -- words ---------------------------------------------------------------------------------------

function pickLang() {
  try {
    const kept = localStorage.getItem(LANG);
    if (kept === "en" || kept === "de") return kept;
  } catch {}
  return (navigator.language || "en").toLowerCase().startsWith("de") ? "de" : "en";
}

function t(key, vars = {}) {
  const words = window.I18N[S.lang] || window.I18N.en;
  let s = words[key] ?? window.I18N.en[key] ?? key;
  for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, v);
  return s;
}

// -- small helpers -------------------------------------------------------------------------------

const $ = (sel, root = document) => root.querySelector(sel);
function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}
const icon = (name) => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const colour = (v) => `var(--${v})`;

function toast(text) {
  const box = $("#toast");
  box.textContent = text;
  box.classList.add("shown");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => box.classList.remove("shown"), 4200);
}

function recall() {
  try {
    return JSON.parse(localStorage.getItem(LAST) || "{}") || {};
  } catch {
    return {};
  }
}

function remember(patch) {
  try {
    localStorage.setItem(LAST, JSON.stringify({ ...recall(), ...patch }));
  } catch {}
}

// -- talking to the desk -------------------------------------------------------------------------

async function api(path, body) {
  const init = { headers: { "X-Desk-Token": BOOT.token } };
  if (body !== undefined) {
    init.method = "POST";
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify({ ...body, client: CLIENT });
  }
  const r = await fetch(path, init);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const e = new Error(data.error || r.statusText);
    e.status = r.status;
    throw e;
  }
  return data;
}

async function loadState() {
  S.state = await api("/api/state");
  applyProject();
  if (S.round) syncSide();
  else renderSide();
}

/** Your answers the desk doesn't have yet, laid over what it sent. */
function overlay(round, slug) {
  for (const entry of S.outbox.values()) {
    if (entry.round !== slug) continue;
    if (entry.id === "overall") Object.assign(round.state.overall, entry.fields);
    else if (round.state.items[entry.id]) Object.assign(round.state.items[entry.id], entry.fields);
  }
  return round;
}

async function openRound(slug, { keepPlace = false } = {}) {
  if (!slug) {
    S.current = S.round = null;
    renderMain();
    renderSide();
    return;
  }
  const moved = slug !== S.current;
  const round = overlay(await api(`/api/round/${encodeURIComponent(slug)}`), slug);
  S.current = slug;
  S.round = round;
  remember({ round: slug });
  renderMain({ keepPlace: keepPlace && !moved });
  syncSide();
  if (moved) {
    const last = recall();
    const target = last.round === slug && last.item ? card(last.item) : null;
    if (target) target.scrollIntoView({ block: "center" });
    else $("main").scrollTop = 0;
  }
}

function connect() {
  const source = new EventSource(`/api/events?t=${encodeURIComponent(BOOT.token)}`);
  let first = true;
  source.onopen = () => {
    S.live = true;
    renderConn();
    if (first && S.state) {
      first = false;
      return;
    }
    first = false;
    // Back after a gap: hand over what waited, then catch up on what changed meanwhile.
    flush();
    loadState().then(() => openRound(S.current || (S.state.rounds[0] || {}).slug, { keepPlace: true })).catch(() => {});
  };
  source.onerror = () => {
    S.live = false;
    renderConn();
    first = false;
    if (source.readyState !== EventSource.CLOSED) return; // the browser tries again by itself
    setTimeout(async () => {
      try {
        const r = await fetch("/api/state", { headers: { "X-Desk-Token": BOOT.token } });
        if (r.status === 403) return location.reload(); // a desk with a new secret: start over
      } catch {}
      connect();
    }, 3000);
  };
  source.onmessage = (e) => {
    let event;
    try {
      event = JSON.parse(e.data);
    } catch {
      return;
    }
    onEvent(event).catch(() => {});
  };
}

async function onEvent(event) {
  if (event.client === CLIENT) return; // our own answer coming back
  if (event.type === "rounds" || event.type === "settings") {
    await loadState();
    if (!S.current && S.state.rounds.length) await openRound(S.state.rounds[0].slug);
    return;
  }
  if (event.type === "round") {
    if (event.by === "claude" && event.new) toast(t("new.round", { t: event.slug }));
    else if (event.by === "claude" && event.slug === S.current) toast(t("changed.by.claude"));
    if (event.slug === S.current) await openRound(S.current, { keepPlace: true });
    else await loadState();
  }
}

// -- saving: every change goes into the outbox, which hands it to the desk ----------------------

function change(id, fields, delay = 0) {
  const key = `${S.current}\n${id}`;
  const before = S.outbox.get(key);
  S.outbox.set(key, { round: S.current, id, fields: { ...(before ? before.fields : {}), ...fields } });
  clearTimeout(S.flushTimer);
  S.flushTimer = setTimeout(flush, delay);
  showSaved();
}

async function flush() {
  if (S.flushing) {
    S.again = true;
    return;
  }
  S.flushing = true;
  clearTimeout(S.retryTimer);
  try {
    for (const [key, entry] of [...S.outbox]) {
      const overall = entry.id === "overall";
      try {
        await api(overall ? "/api/overall" : "/api/item", overall
          ? { round: entry.round, note: entry.fields.note ?? "" }
          : { round: entry.round, item: entry.id, ...entry.fields });
        if (S.outbox.get(key) === entry) S.outbox.delete(key);
        S.failed = null;
      } catch (e) {
        if (e.status === 400) {
          // The desk can't take it (the item is gone from the checklist): say so, drop it.
          S.outbox.delete(key);
          toast(t("save.failed", { e: e.message }));
          continue;
        }
        S.failed = e.status ? t("save.failed", { e: e.message }) : t("save.waiting");
        break;
      }
    }
  } finally {
    S.flushing = false;
  }
  if (S.again) {
    S.again = false;
    return flush();
  }
  if (S.failed && S.outbox.size) S.retryTimer = setTimeout(flush, 5000);
  showSaved();
}

function showSaved() {
  const box = $(".head .saved");
  if (!box) return;
  const waiting = S.outbox.size > 0;
  box.textContent = S.failed && waiting ? S.failed : waiting ? t("saving") : t("saved");
  box.classList.toggle("bad", Boolean(S.failed && waiting));
}

window.addEventListener("beforeunload", (e) => {
  if (S.outbox.size) e.preventDefault();
});

// -- where you are -------------------------------------------------------------------------------

let presenceTimer;
function here(id) {
  if (recall().item === id && $(".item.here")?.dataset.id === id) return;
  remember({ round: S.current, item: id });
  document.querySelectorAll(".item.here").forEach((c) => c.classList.remove("here"));
  card(id)?.classList.add("here");
  clearTimeout(presenceTimer);
  presenceTimer = setTimeout(() => api("/api/presence", { round: S.current, item: id }).catch(() => {}), 700);
}

function card(id) {
  return document.querySelector(`[data-id="${CSS.escape(id)}"]`);
}

// -- the sidebar ---------------------------------------------------------------------------------

function applyProject() {
  const project = (S.state && S.state.project) || BOOT.project || {};
  if (project.accent) document.documentElement.style.setProperty("--accent", project.accent);
  $("#project").textContent = project.title || "";
  document.title = `${project.title ? project.title + " · " : ""}${t("brand")}`;
}

function ring(counts) {
  const total = Math.max(counts.total || 0, 1);
  const r = 13;
  const c = 2 * Math.PI * r;
  let offset = 0;
  const parts = VERDICTS.map((v) => {
    const len = ((counts[v] || 0) / total) * c;
    const seg = len > 0
      ? `<circle cx="17" cy="17" r="${r}" stroke="${colour(v)}" stroke-dasharray="${len} ${c - len}" stroke-dashoffset="${-offset}" transform="rotate(-90 17 17)"/>`
      : "";
    offset += len;
    return seg;
  }).join("");
  return `<svg class="ring" viewBox="0 0 34 34" aria-hidden="true"><circle cx="17" cy="17" r="${r}" stroke="var(--control)"/>${parts}</svg>`;
}

function renderSide() {
  const list = $("#rounds");
  list.innerHTML = "";
  const rounds = (S.state && S.state.rounds) || [];
  if (!rounds.length) {
    list.append(el("li", "empty", esc(t("no.rounds"))));
    return;
  }
  for (const r of rounds) {
    const li = el("li");
    const b = el("button");
    b.type = "button";
    if (r.slug === S.current) b.setAttribute("aria-current", "true");
    const c = r.counts || { total: 0 };
    const done = (c.total || 0) - (c.open || 0);
    const sub = r.error
      ? esc(r.error)
      : esc(t("of", { a: done, b: c.total || 0 })) + (r.round > 1 ? ` · ${esc(t("round", { n: r.round }))}` : "");
    b.innerHTML = `${ring(c)}<span><span class="title">${esc(r.title)}</span><span class="sub">${sub}</span></span>`
      + (c.retest ? `<span class="badge" title="${esc(t("retest.count", { n: c.retest }))}">${c.retest}</span>` : "");
    b.onclick = () => openRound(r.slug).catch((e) => toast(e.message));
    li.append(b);
    list.append(li);
  }
}

/** The open round's numbers in the sidebar, as they are on this page right now. */
function syncSide() {
  const entry = S.state && S.round && S.state.rounds.find((r) => r.slug === S.current);
  if (entry) entry.counts = counts();
  renderSide();
}

function renderConn() {
  const box = $("#conn");
  box.textContent = S.live ? t("live") : t("not.live");
  box.classList.toggle("off", !S.live);
}

// -- the open round ------------------------------------------------------------------------------

function counts() {
  const c = { works: 0, partly: 0, change: 0, blocked: 0, skipped: 0, open: 0, retest: 0, broken: 0, total: 0 };
  for (const a of Object.values(S.round.state.items)) {
    c[a.verdict || "open"] += 1;
    c.retest += Boolean(a.retest && !a.verdict);
    c.broken += a.severity === "broken";
    c.total += 1;
  }
  return c;
}

function renderHead(head) {
  const { doc, state } = S.round;
  const c = counts();
  const meta = [];
  if (doc.about) meta.push(esc(t("about", { t: doc.about })));
  if (state.round > 1) meta.push(esc(t("round", { n: state.round })));
  if (doc.meta && doc.meta.commit) meta.push(`<span class="mono">${esc(t("commit", { c: doc.meta.commit }))}</span>`);
  meta.push(esc(state.sent ? t("sent", { t: state.sent }) : t("not.sent")));
  const pct = (n) => `${(100 * n) / Math.max(c.total, 1)}%`;
  const bar = VERDICTS.map((v) => `<span style="width:${pct(c[v])};background:${colour(v)}"></span>`).join("");
  const tally = [...VERDICTS, "open"]
    .filter((v) => c[v] || v === "open")
    .map((v) => `<span>${v === "open" ? "" : `<i style="background:${colour(v)}"></i>`}<b>${c[v]}</b> ${esc(t("count." + v))}</span>`)
    .join("");
  head.innerHTML = `
    <div class="row">
      <div class="titles"><h1>${esc(doc.title)}</h1><div class="meta">${meta.map((m) => `<span>${m}</span>`).join("")}</div></div>
      <div class="actions"><span class="saved"></span></div>
    </div>
    <div class="bar" aria-hidden="true">${bar}</div>
    <div class="tally">${tally}</div>`;
  showSaved();
}

/** After an answer changed: the header's numbers, the sections' counts, the sidebar. */
function refreshTotals() {
  const head = $(".head");
  if (head) renderHead(head);
  updateSectionCounts();
  syncSide();
}

function codeBlock(b) {
  const box = el("div", "code");
  const pre = el("pre");
  pre.textContent = b.text;
  const tools = el("div", "tools");
  const copy = el("button", null, esc(t("copy")));
  copy.type = "button";
  copy.onclick = async () => {
    try {
      await navigator.clipboard.writeText(b.text);
      copy.textContent = t("copied");
    } catch {
      const range = document.createRange();
      range.selectNodeContents(pre);
      getSelection().removeAllRanges();
      getSelection().addRange(range);
      copy.textContent = t("select.it");
    }
    setTimeout(() => (copy.textContent = t("copy")), 1400);
  };
  tools.append(copy);
  box.append(pre, tools);
  return box;
}

function blocks(list, into) {
  for (const b of list) {
    if (b.type === "p") into.append(el("p", null, b.html));
    else if (b.type === "heading") into.append(el("h3", null, b.html));
    else if (b.type === "code") into.append(codeBlock(b));
    else if (b.type === "list") {
      const ul = el("ul");
      for (const entry of b.items) {
        const li = el("li", null, entry.html);
        blocks(entry.children, li);
        ul.append(li);
      }
      into.append(ul);
    } else if (b.type === "item") into.append(itemCard(b));
  }
}

function autosize(area) {
  if (area.hidden) return;
  area.style.height = "auto";
  area.style.height = `${Math.max(area.classList.contains("big") ? 100 : 60, area.scrollHeight + 2)}px`;
}

function itemCard(b) {
  const a = S.round.state.items[b.id];
  const box = el("article", "item");
  box.dataset.id = b.id;
  const top = el("div", "top");
  top.append(el("div", "num", esc(b.number)), el("div", "text", `<p>${b.html}</p>`));
  const body = el("div", "body");

  if (b.fields.length) {
    const fields = el("div", "fields");
    for (const f of b.fields) {
      fields.append(el("div", `field ${f.label}`, `<span class="label">${esc(t(f.label))}</span><span>${f.html}</span>`));
    }
    body.append(fields);
  }
  // What explains the item comes first, then your answer, then the items nested under it.
  blocks(b.children.filter((c) => c.type !== "item"), body);

  const parts = { verdicts: {}, severities: {} };
  const answer = el("div", "answer");
  const verdicts = el("div", "verdicts");
  verdicts.setAttribute("role", "group");
  for (const v of VERDICTS) {
    const btn = el("button", v, `${icon(v)}<span>${esc(t(v))}</span>`);
    btn.type = "button";
    btn.onclick = () => {
      a.verdict = a.verdict === v ? "" : v;
      const fields = { verdict: a.verdict };
      if (a.verdict !== "change" && a.severity) fields.severity = a.severity = "";
      change(b.id, fields);
      refreshCard(box, b);
      refreshTotals();
      if (a.verdict && a.verdict !== "works") parts.note.focus();
    };
    parts.verdicts[v] = btn;
    verdicts.append(btn);
  }
  answer.append(verdicts);

  parts.severity = el("div", "severity");
  parts.severity.append(el("span", null, esc(t("severity"))));
  for (const s of SEVERITIES) {
    const btn = el("button", s, esc(t(s)));
    btn.type = "button";
    btn.onclick = () => {
      a.severity = a.severity === s ? "" : s;
      change(b.id, { severity: a.severity });
      refreshCard(box, b);
      refreshTotals();
    };
    parts.severities[s] = btn;
    parts.severity.append(btn);
  }
  answer.append(parts.severity);

  parts.note = el("textarea", "note");
  parts.note.value = a.note;
  parts.note.setAttribute("aria-label", `${t("note")} ${b.number}`);
  parts.note.oninput = () => {
    a.note = parts.note.value;
    autosize(parts.note);
    change(b.id, { note: a.note }, 600);
  };
  answer.append(parts.note);
  body.append(answer);

  blocks(b.children.filter((c) => c.type === "item"), body);
  top.append(body);
  box.append(top);
  box.parts = parts;
  const mine = (e) => e.target.closest(".item") === box;
  box.addEventListener("focusin", (e) => mine(e) && here(b.id));
  box.addEventListener("pointerdown", (e) => mine(e) && here(b.id));
  refreshCard(box, b);
  return box;
}

function refreshCard(box, b) {
  const a = S.round.state.items[b.id];
  const { parts } = box;
  const last = recall();
  box.className = `item${a.verdict ? " v-" + a.verdict : ""}${last.round === S.current && last.item === b.id ? " here" : ""}`;
  for (const v of VERDICTS) parts.verdicts[v].setAttribute("aria-pressed", String(a.verdict === v));
  parts.severity.hidden = a.verdict !== "change";
  for (const s of SEVERITIES) parts.severities[s].setAttribute("aria-pressed", String(a.severity === s));
  parts.note.placeholder = a.verdict ? t(`note.${a.verdict}`) : t("note");
  parts.note.hidden = !a.verdict && !a.note.trim() && parts.note !== document.activeElement;
  requestAnimationFrame(() => autosize(parts.note));
}

function updateSectionCounts() {
  for (const part of document.querySelectorAll("section.part")) {
    const ids = [...part.querySelectorAll(".item")].map((c) => c.dataset.id);
    const done = ids.filter((id) => S.round.state.items[id] && S.round.state.items[id].verdict).length;
    const box = $("h2 .count", part);
    if (box) box.textContent = ids.length ? t("of", { a: done, b: ids.length }) : "";
  }
}

function renderEmpty(main) {
  const none = !S.state || !S.state.rounds.length;
  main.innerHTML = `<div class="empty-state"><div class="mark">${icon("works")}</div>
    <h1>${esc(none ? t("empty.title") : t("pick"))}</h1>${none ? `<p>${esc(t("empty.text"))}</p>` : ""}</div>`;
}

function renderMain({ keepPlace = false } = {}) {
  const main = $("main");
  if (!S.round) return renderEmpty(main);

  // Whatever you are typing in stays focused, with the caret where it was; the page stays put.
  const focused = document.activeElement;
  const holder = focused && focused.tagName === "TEXTAREA" ? focused.closest("[data-id]") : null;
  const keep = holder ? { id: holder.dataset.id, start: focused.selectionStart, end: focused.selectionEnd } : null;
  const scroll = main.scrollTop;

  const wrap = el("div", "wrap");
  const head = el("div", "head");
  wrap.append(head);
  renderHead(head);
  for (const s of S.round.doc.sections) {
    if (!s.title) {
      const intro = el("div", "intro");
      blocks(s.blocks, intro);
      wrap.append(intro);
      continue;
    }
    const part = el("section", "part");
    const h = el("h2", null, `<span>${s.html}</span>`);
    h.append(el("span", "count"));
    part.append(h);
    blocks(s.blocks, part);
    wrap.append(part);
  }

  const overall = el("div", "overall");
  overall.dataset.id = "overall";
  overall.append(el("h2", null, esc(t("overall.title"))), el("p", null, esc(t("overall.text"))));
  const area = el("textarea", "note big");
  area.value = S.round.state.overall.note;
  area.setAttribute("aria-label", t("overall.title"));
  area.oninput = () => {
    S.round.state.overall.note = area.value;
    autosize(area);
    change("overall", { note: area.value }, 600);
  };
  overall.append(area);
  wrap.append(overall);

  main.replaceChildren(wrap);
  updateSectionCounts();
  requestAnimationFrame(() => autosize(area));

  if (keep) {
    const again = keep.id === "overall" ? area : card(keep.id)?.parts?.note;
    if (again) {
      again.hidden = false;
      again.focus({ preventScroll: true });
      again.setSelectionRange(keep.start, keep.end);
    }
  }
  if (keepPlace) main.scrollTop = scroll;
}

// -- start -----------------------------------------------------------------------------------------

function renderWords() {
  document.documentElement.lang = S.lang;
  document.querySelectorAll("[data-t]").forEach((n) => (n.textContent = t(n.dataset.t)));
  $("#lang").value = S.lang;
  applyProject();
  renderConn();
}

$("#lang").onchange = (e) => {
  S.lang = e.target.value;
  try {
    localStorage.setItem(LANG, S.lang);
  } catch {}
  renderWords();
  renderSide();
  renderMain({ keepPlace: true });
};

$("main").addEventListener("scroll", () => {
  clearTimeout(S.scrollTimer);
  S.scrollTimer = setTimeout(() => remember({ scroll: $("main").scrollTop }), 300);
}, { passive: true });

(async function start() {
  renderWords();
  try {
    await loadState();
    const last = recall();
    const slugs = S.state.rounds.map((r) => r.slug);
    await openRound(slugs.includes(last.round) ? last.round : slugs[0]);
  } catch {
    toast(t("offline"));
    renderMain();
  }
  connect();
})();
