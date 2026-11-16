"use strict";
// Review Desk's page: the project's reviews in the sidebar, one review open with its items. Your
// answers, questions and ideas save as you type (and wait on the page until the desk has them);
// "Hand back" wakes Claude; what Claude does shows up live, with a chime or a notification.

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
  question: '<path d="M9.2 9.3a2.9 2.9 0 1 1 4.1 2.6c-.8.4-1.3 1-1.3 1.9v.4"/><path d="M12 17.2v.1"/><circle cx="12" cy="12" r="8.5"/>',
  idea: '<path d="M9 17.5h6M10 20.5h4"/><path d="M12 3.5a5.5 5.5 0 0 0-3.2 10c.7.5 1.2 1.3 1.2 2.2h4c0-.9.5-1.7 1.2-2.2A5.5 5.5 0 0 0 12 3.5z"/>',
  reply: '<path d="M9.5 8.5L5 13l4.5 4.5"/><path d="M5 13h9a5 5 0 0 0 5-5V6"/>',
  remove: '<path d="M7 7l10 10M17 7L7 17"/>',
  panel: '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M9.5 5v14"/>',
  message: '<path d="M5 6.5h14v9H11l-4 3.5v-3.5H5z"/>',
  edit: '<path d="M5 19l.9-3.9L16 5a2 2 0 0 1 3 3L8.9 18.1z"/><path d="M14.5 6.5l3 3"/>',
  send: '<path d="M4.5 12h13"/><path d="M12.5 6.5L18 12l-5.5 5.5"/>',
  bell: '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 1.5h-15z"/><path d="M10 20.5h4"/>',
  "bell-off": '<path d="M6 16.5V11a6 6 0 0 1 9.4-4.9M18 11v5.5l1.5 1.5H8"/><path d="M10 20.5h4"/><path d="M4 4l16 16"/>',
  sound: '<path d="M4.5 9.5h3l4.5-4v13l-4.5-4h-3z"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/>',
  "sound-off": '<path d="M4.5 9.5h3l4.5-4v13l-4.5-4h-3z"/><path d="M16 9.5l5 5M21 9.5l-5 5"/>',
  copy: '<rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 8.5V6a1.5 1.5 0 0 0-1.5-1.5H6A1.5 1.5 0 0 0 4.5 6v8A1.5 1.5 0 0 0 6 15.5h2.5"/>',
  phone: '<rect x="7" y="3" width="10" height="18" rx="2.2"/><path d="M11 17.5h2"/>',
  attach: '<path d="M15.5 7.5l-6.8 6.8a2 2 0 0 0 2.8 2.8l7-7a4 4 0 0 0-5.6-5.6l-7 7a6 6 0 0 0 8.5 8.5l6-6"/>',
  camera: '<path d="M4 8.5h3l1.8-2.5h6.4L17 8.5h3v10H4z"/><circle cx="12" cy="13" r="3.4"/>',
  image: '<rect x="4" y="5" width="16" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M5 17l4.5-4.5 3 3 2.5-2.5L19.5 17"/>',
  record: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.2" fill="currentColor"/>',
  log: '<path d="M6 6.5h12M6 10.5h12M6 14.5h8M6 18.5h10"/>',
  file: '<path d="M7 3.5h7l4 4v13H7z"/><path d="M14 3.5v4h4"/>',
  play: '<path d="M8 5.5v13l10.5-6.5z"/>',
  stop: '<rect x="6.5" y="6.5" width="11" height="11" rx="1.5"/>',
  arrow: '<path d="M5 19L18 6"/><path d="M10 6h8v8"/>',
  box: '<rect x="4.5" y="6" width="15" height="12" rx="1"/>',
  blur: '<path d="M4 4h4v4H4zM12 4h4v4h-4zM8 8h4v4H8zM16 8h4v4h-4zM4 12h4v4H4zM12 12h4v4h-4zM8 16h4v4H8zM16 16h4v4h-4z" fill="currentColor" stroke="none"/>',
  undo: '<path d="M8.5 8.5H15a4.5 4.5 0 0 1 0 9h-5"/><path d="M11.5 5L8 8.5l3.5 3.5"/>',
  down: '<path d="M7 10l5 5 5-5"/>',
  up: '<path d="M7 14l5-5 5 5"/>',
  hourglass: '<path d="M7 3.5h10M7 20.5h10"/><path d="M8 3.5c0 4.5 8 4.5 8 8.5s-8 4-8 8.5M16 3.5c0 4.5-8 4.5-8 8.5s8 4 8 8.5"/>',
};
const LAST = "review-desk:last";
const LANG = "review-desk:lang";
const PREFS = "review-desk:prefs";

const S = {
  lang: pickLang(),
  prefs: { sound: true, notify: true, ...stored(PREFS) },
  state: null,          // the project and its rounds (the sidebar)
  current: null,        // the open round's slug
  round: null,          // the open round: {doc, state}
  outbox: new Map(),    // what the desk doesn't have yet, by "round\nitem[\nmessage]"
  flushTimer: null,
  retryTimer: null,
  flushing: false,
  again: false,
  failed: null,
  live: false,
  handing: false,
  flying: false,
  drafts: {},
  audio: null,
  runs: new Map(),      // the open round's Run output, by code block
  view: "round",        // or "ideas": the Ideas board
  ideas: [],
  ideaFilter: "all",
  questions: [],        // Claude's question sets waiting for answers (of the session shown)
  allQuestions: [],     // ... of every session
  desks: [],            // every running desk, this one first (the Desks list)
  history: [],          // what Claude did lately on every desk (the bell)
  session: keptSession(), // the session the sidebar shows (null: all)
  jump: null,           // the tally's last jump: {v, id} (the item it went to)
  hidden: [],           // items the browser doesn't show (an extension hid or removed their cards)
  phoneOn: Boolean(BOOT.phone),
};

// -- words and small helpers ---------------------------------------------------------------------

function stored(key) {
  try {
    return JSON.parse(localStorage.getItem(key) || "{}") || {};
  } catch {
    return {};
  }
}

function store(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {}
}

function pickLang() {
  try {
    const kept = localStorage.getItem(LANG);
    if (kept === "en" || kept === "de") return kept;
  } catch {}
  return (navigator.language || "en").toLowerCase().startsWith("de") ? "de" : "en";
}

/** A round with `kind: plan` in its header is a plan to comment on: the page says so in its words. */
function isPlan() {
  return Boolean(S.round && S.round.doc && S.round.doc.meta && S.round.doc.meta.kind === "plan");
}

function t(key, vars = {}) {
  const words = window.I18N[S.lang] || window.I18N.en;
  const plan = isPlan() ? words["plan." + key] ?? window.I18N.en["plan." + key] : undefined;
  let s = plan ?? words[key] ?? window.I18N.en[key] ?? key;
  for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, v);
  return s;
}

const $ = (sel, root = document) => root.querySelector(sel);
function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}
function button(cls, html, onclick, title) {
  const b = el("button", cls, html);
  b.type = "button";
  if (onclick) b.onclick = onclick;
  if (title) b.title = title;
  return b;
}
const icon = (name) => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const colour = (v) => `var(--${v})`;
const clock = (at) => (at || "").slice(11, 16) || at || "";
const recall = () => stored(LAST);
const remember = (patch) => store(LAST, { ...recall(), ...patch });

function toast(text, action) {
  const box = $("#toast");
  box.textContent = text;
  box.onclick = action ? () => { box.classList.remove("shown"); action(); } : null;
  box.classList.toggle("link", Boolean(action));
  box.classList.add("shown");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => box.classList.remove("shown"), 4800);
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
  [S.state] = await Promise.all([api("/api/state"), loadIdeas()]);
  if (S.state.version && BOOT.version && S.state.version !== BOOT.version) offerReload();
  applyProject();
  if (S.round) {
    syncSide();
    refreshHead();
  } else renderSide();
  markSeen();
  loadDesks();
}

function summary() {
  return S.state && S.state.rounds.find((r) => r.slug === S.current);
}

function thread(round, id) {
  return id === "overall" ? round.state.overall.messages : (round.state.items[id] || {}).messages;
}

/** Review Desk itself was updated while the page was open: a button to load the new page. */
function offerReload() {
  if (document.querySelector(".update-pill")) return;
  const pill = button("update-pill", `${icon("undo")}<span>${esc(t("updated"))}</span>`, async () => {
    await flushNow();
    location.reload();
  });
  document.body.append(pill);
}

/** What the desk doesn't have yet, laid over what it sent. */
function overlay(round, slug) {
  for (const entry of S.outbox.values()) {
    if (entry.round !== slug) continue;
    if (entry.mid) {
      const list = thread(round, entry.id);
      if (!list) continue;
      const at = list.findIndex((m) => m.id === entry.mid);
      if (entry.fields.delete) {
        if (at >= 0) list.splice(at, 1);
      } else if (at >= 0) Object.assign(list[at], entry.fields);
      else list.push({ id: entry.mid, from: "you", at: "", ...entry.fields });
    } else if (entry.id === "overall") Object.assign(round.state.overall, entry.fields);
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
  const fromBoard = S.view !== "round";
  if (moved) S.jump = null; // another round's items: the tally starts over
  S.current = slug;
  S.round = round;
  S.view = "round";
  if (moved) await loadRuns();
  remember({ round: slug, view: "round" });
  renderMain({ keepPlace: keepPlace && !moved && !fromBoard });
  syncSide();
  if (moved || fromBoard) {
    const last = recall();
    const target = last.round === slug && last.item ? card(last.item) : null;
    if (target) target.scrollIntoView({ block: "center" });
    else scroller().scrollTop = 0;
  }
}

function connect() {
  const source = new EventSource(`/api/events?t=${encodeURIComponent(BOOT.token)}&c=${CLIENT}`);
  let first = true;
  source.onopen = () => {
    S.live = true;
    renderConn();
    tellPresence();
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
  if (event.client === CLIENT) return; // our own change coming back
  if (event.notify || event.type === "peer") loadHistory();
  if (event.type === "peer") return announcePeer(event);
  if (event.type === "desks") return loadDesks();
  if (event.type === "seen") return loadState();
  if (event.type === "run") return onRun(event);
  if (event.type === "phone") {
    S.phoneOn = Boolean(event.on);
    renderPrefs();
    return refreshPhone();
  }
  if (event.type === "listening") {
    if (S.state) Object.assign(S.state, { listening: event.on, listeners: event.listeners || S.state.listeners });
    refreshHead();
    loadDesks();
    return;
  }
  if (event.type === "questions") {
    await loadQuestions();
    loadDesks();
    if (event.notify) announce(event);
    return;
  }
  if (event.type === "ideas") {
    if (event.notify) announce(event);
    if (S.view === "ideas") {
      await loadIdeas();
      if (!document.querySelector("dialog[open]")) renderIdeas();
    }
    return;
  }
  if (S.view === "ideas" && (event.type === "round" || event.type === "rounds")) {
    if (event.type === "round" && event.by === "claude" && event.notify) announce(event);
    await loadState();
    if (!document.querySelector("dialog[open]")) renderIdeas();
    return;
  }
  if (event.type === "handled" || event.type === "rounds" || event.type === "settings") {
    await loadState();
    if (!S.current && S.state.rounds.length) await openRound(S.state.rounds[0].slug);
    return;
  }
  if (event.type === "round") {
    if (event.by === "claude") {
      if (event.notify) announce(event);
      else if (event.slug === S.current && event.what === "edit") toast(t("changed.by.claude"));
    }
    if (event.slug === S.current) await openRound(S.current, { keepPlace: true });
    if (event.slug !== S.current || event.by === "claude") await loadState();
    if (!S.current) await openRound(event.slug);
  }
}

// -- telling you: a chime, a toast, or a notification while the page is hidden -------------------

function chime() {
  if (!S.prefs.sound) return;
  try {
    S.audio = S.audio || new AudioContext();
    const ctx = S.audio;
    const t0 = ctx.currentTime + 0.02;
    for (const [freq, delay] of [[659.3, 0], [987.8, 0.13]]) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, t0 + delay);
      gain.gain.exponentialRampToValueAtTime(0.09, t0 + delay + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, t0 + delay + 0.6);
      osc.connect(gain).connect(ctx.destination);
      osc.start(t0 + delay);
      osc.stop(t0 + delay + 0.65);
    }
  } catch {}
}

function announce(event) {
  const round = (S.state && S.state.rounds.find((r) => r.slug === event.slug)) || {};
  const title = t(`notify.${event.what}`) || event.notify.title;
  const body = event.what === "new" || event.what === "ask"
    ? event.notify.body
    : [round.title || event.slug, event.what === "reply" ? event.notify.body : ""].filter(Boolean).join(" · ");
  chime();
  if (document.hidden && S.prefs.notify && "Notification" in window && Notification.permission === "granted") {
    const n = new Notification(title, { body, tag: `${event.slug}:${event.what}`, icon: faviconData() });
    n.onclick = () => {
      window.focus();
      n.close();
      if (event.what === "ask") openAsk();
      else goTo(event.slug, event.item);
    };
  } else toast(body ? `${title}: ${body}` : title);
}

function faviconData() {
  const link = document.querySelector('link[rel="icon"]');
  return link ? link.href : undefined;
}

async function goTo(slug, item) {
  if (!shownRounds().some((r) => r.slug === slug)) await setSession(null); // another session's round: show all
  if (slug !== S.current || S.view !== "round") {
    if (item) remember({ round: slug, item });
    await openRound(slug);
  }
  const target = item && card(item);
  if (target) target.scrollIntoView({ block: "center" });
}

function tellPresence(item) {
  const notify = S.prefs.notify && "Notification" in window && Notification.permission === "granted";
  const body = { round: S.current || "", visible: !document.hidden, notify };
  if (item !== undefined) body.item = item;
  api("/api/presence", body).catch(() => {});
}

document.addEventListener("visibilitychange", () => tellPresence());
// The sound may only start after you touched the page once.
document.addEventListener("pointerdown", () => {
  if (S.prefs.sound && !S.audio) {
    try {
      S.audio = new AudioContext();
    } catch {}
  }
  if (S.audio && S.audio.state === "suspended") S.audio.resume().catch(() => {});
});

function renderPrefs() {
  const bell = $("#bell");
  const blocked = "Notification" in window && Notification.permission === "denied";
  const on = S.prefs.notify && "Notification" in window && Notification.permission === "granted";
  bell.innerHTML = icon(on ? "bell" : "bell-off");
  bell.title = blocked ? t("notify.blocked") : on ? t("notify.on") : t("notify.off");
  bell.setAttribute("aria-label", bell.title);
  bell.setAttribute("aria-pressed", String(on));
  const sound = $("#sound");
  sound.innerHTML = icon(S.prefs.sound ? "sound" : "sound-off");
  sound.title = S.prefs.sound ? t("sound.on") : t("sound.off");
  sound.setAttribute("aria-label", sound.title);
  sound.setAttribute("aria-pressed", String(S.prefs.sound));
  const phone = $("#phone");
  phone.hidden = BOOT.local === false;
  phone.innerHTML = icon("phone");
  phone.title = S.phoneOn ? t("phone.is.on") : t("phone.title");
  phone.setAttribute("aria-label", phone.title);
  phone.setAttribute("aria-pressed", String(S.phoneOn));
}

$("#bell").onclick = async () => {
  if (!("Notification" in window)) return;
  if (Notification.permission === "default") {
    await Notification.requestPermission().catch(() => {});
    S.prefs.notify = true;
  } else if (Notification.permission === "granted") S.prefs.notify = !S.prefs.notify;
  store(PREFS, S.prefs);
  renderPrefs();
  tellPresence();
};

$("#phone").onclick = () => openPhone();

$("#sound").onclick = () => {
  S.prefs.sound = !S.prefs.sound;
  store(PREFS, S.prefs);
  renderPrefs();
  if (S.prefs.sound) chime();
};

// -- saving: every change goes into the outbox, which hands it to the desk ----------------------

function change(id, fields, delay = 0, mid = null) {
  const key = [S.current, id, mid].filter((x) => x !== null).join("\n");
  const before = S.outbox.get(key);
  S.outbox.set(key, { round: S.current, id, mid, fields: { ...(before ? before.fields : {}), ...fields } });
  clearTimeout(S.flushTimer);
  S.flushTimer = setTimeout(flush, delay);
  showSaved();
}

function request(entry) {
  if (entry.mid) {
    return ["/api/message", entry.fields.delete
      ? { round: entry.round, item: entry.id, id: entry.mid, delete: true }
      : { round: entry.round, item: entry.id, id: entry.mid, kind: entry.fields.kind, text: entry.fields.text ?? "", to: entry.fields.to }];
  }
  if (entry.id === "overall") return ["/api/overall", { round: entry.round, note: entry.fields.note ?? "" }];
  return ["/api/item", { round: entry.round, item: entry.id, ...entry.fields }];
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
      try {
        await api(...request(entry));
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

/** Everything handed to the desk now; false when it can't be. */
async function flushNow() {
  clearTimeout(S.flushTimer);
  for (let i = 0; i < 3 && S.outbox.size; i++) {
    while (S.flushing) await new Promise((r) => setTimeout(r, 50));
    await flush();
    if (S.failed) return false;
  }
  return S.outbox.size === 0;
}

function showSaved(root = document) {
  const box = $(".head .saved", root) || $(".saved", root);
  if (!box) return;
  const waiting = S.outbox.size > 0;
  box.textContent = S.failed && waiting ? S.failed : waiting ? t("saving") : t("saved");
  box.classList.toggle("bad", Boolean(S.failed && waiting));
}

window.addEventListener("beforeunload", (e) => {
  if (S.outbox.size) e.preventDefault();
});

// -- handing back ----------------------------------------------------------------------------------

/** Before a hand-back with items still open: say which, and offer to go to them first. */
function confirmOpen() {
  const open = allItems(S.round.doc).filter((it) => !it.extra && !(S.round.state.items[it.id] || {}).verdict);
  if (!open.length) return Promise.resolve(true);
  return new Promise((resolve) => {
    const d = dialog("confirm");
    let answer = false;
    d.addEventListener("close", () => resolve(answer));
    const list = el("ul", "open-list");
    for (const it of open.slice(0, 8)) list.append(el("li", null, `<span class="mono">${esc(it.number)}</span> ${esc(plain(it.md))}`));
    if (open.length > 8) list.append(el("li", "dim", esc(t("open.more", { n: open.length - 8 }))));
    const body = el("div", "confirm-body");
    body.append(el("p", null, esc(t(open.length === 1 ? "open.one" : "open.many", { n: open.length }))), list);
    const gone = open.filter((it) => S.hidden.includes(it.number)).map((it) => it.number);
    if (gone.length) {
      body.append(el("p", "hidden-note", `<span>${esc(t(gone.length === 1 ? "hidden.one" : "hidden.many", { n: gone.length, list: gone.join(", ") }))}</span>`));
    }
    const foot = el("footer");
    foot.append(
      button("quiet", esc(t("open.anyway")), () => { answer = true; d.close(); }),
      button("primary", esc(t("open.show")), () => { d.close(); S.jump = null; jumpTo("open"); }),
    );
    d.append(el("header", null, `<h2>${esc(t("open.title"))}</h2>`), body, foot);
    d.showModal();
  });
}

const REDUCED = matchMedia("(prefers-reduced-motion: reduce)");
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
const anim = (node, frames, opts) => node.animate(frames, { fill: "forwards", easing: "ease-in-out", ...opts }).finished.catch(() => {});

/**
 * The hand-back animation: the button folds into an envelope, dashes to a tray that only appears
 * now, "Sent" lights up once the desk has it, and the button springs back where an empty outline
 * held its place. `r` is the button's box, `request` the hand-back itself (a failure ends the
 * animation early and is thrown again), `back` puts the real button back.
 */
async function flyAway(r, label, request, back) {
  const root = el("div", "fx");
  const put = (cls, html, box) => {
    const n = el("div", cls, html);
    Object.assign(n.style, Object.fromEntries(Object.entries(box).map(([k, v]) => [k, `${v}px`])));
    root.append(n);
    return n;
  };
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const trayH = r.height + 12;
  const trayX = Math.max(12, r.left - 28 - 92);
  const ghost = put("fx-ghost", "", { left: r.left, top: r.top, width: r.width, height: r.height });
  const tray = put("fx-tray", `<span class="in">${icon("works")}${esc(t("sent.tray"))}</span>`, { left: trayX, top: cy - trayH / 2, height: trayH });
  const clone = put("fx-clone", esc(label), { left: r.left, top: r.top, width: r.width, height: r.height });
  const bars = [-8, -1, 6].map((o) => put("fx-bar", "", { left: cx - 30, top: cy + o }));
  const env = put("fx-env", '<i class="flap"></i>', { left: cx, top: cy });
  const flap = $(".flap", env);
  document.body.append(root);
  const dx = trayX + 46 - cx;
  try {
    await Promise.all([
      anim(clone, [{ transform: "none" }, { transform: "scale(0.2, 0.72)" }], { duration: 360 }),
      anim(ghost, [{ opacity: 0 }, { opacity: 1 }], { duration: 300 }),
      anim(tray, [{ opacity: 0, transform: "scale(0.92)" }, { opacity: 1, transform: "none" }], { duration: 300, delay: 120 }),
    ]);
    anim(clone, [{ opacity: 1 }, { opacity: 0 }], { duration: 120 });
    await anim(env, [{ opacity: 0, transform: "scale(0.6)" }, { opacity: 1, transform: "none" }], { duration: 120 });
    await anim(flap, [{ transform: "rotateX(180deg)" }, { transform: "rotateX(0)" }], { duration: 260 });
    bars.forEach((b, i) => anim(b, [{ opacity: 0, transform: "none" }, { opacity: 0.6, offset: 0.3 }, { opacity: 0, transform: `translateX(${dx}px)` }], { duration: 620, delay: i * 40 }));
    await anim(env, [{ transform: "none" }, { transform: "scale(1.1) rotate(6deg)", offset: 0.15 }, { transform: `translateX(${dx}px)` }], { duration: 620, easing: "cubic-bezier(0.5, 0, 0.2, 1)" });
    anim(env, [{ opacity: 1, transform: `translateX(${dx}px)` }, { opacity: 0, transform: `translateX(${dx}px) scale(0.4)` }], { duration: 160 });
    await request;
    tray.classList.add("ok");
    await anim($(".in", tray), [{ opacity: 0 }, { opacity: 1 }], { duration: 220 });
    await pause(900);
    back();
    await Promise.all([anim(tray, [{ opacity: 1 }, { opacity: 0 }], { duration: 300 }), anim(ghost, [{ opacity: 1 }, { opacity: 0 }], { duration: 300 })]);
  } finally {
    root.remove();
  }
}

async function handBack() {
  if (S.handing || S.flying || !S.current) return;
  if (!(await confirmOpen())) return;
  let answers = [];
  if (ownAsks().length) {
    // "Answer and hand back": Claude's cards first; they go back in the same step
    answers = await walkAsks();
    if (!answers) return;
  }
  postDrafts();   // what waits in a writing box goes in first
  const handBtn = $(".head .hand");
  const rect = handBtn.getBoundingClientRect();
  const label = handBtn.textContent.trim();
  const round = S.current;
  S.handing = true;
  S.flying = !REDUCED.matches;
  refreshHead();
  const request = (async () => {
    if (!(await flushNow())) throw new Error(S.failed || t("save.waiting"));
    const r = await api("/api/send", { round, message: S.drafts[round] || "", answers });
    S.drafts[round] = "";
    if (answers.length) asksHandedBack(answers.map((a) => a.id));
    if (S.current === round) {
      S.round.state.sent = r.sent;
      const entry = summary();
      if (entry) Object.assign(entry, { sent: r.sent, read: false });
    }
    return r;
  })();
  request.catch(() => {});
  const back = () => {
    S.handing = false;
    S.flying = false;
    refreshHead();
    const box = $(".head .handbox");
    if (box) anim(box, [{ transform: "scale(0.15, 0.8)", opacity: 0 }, { transform: "scale(1.06)", opacity: 1, offset: 0.7 }, { transform: "none", opacity: 1 }], { duration: 520, easing: "cubic-bezier(0.34, 1.56, 0.64, 1)" });
  };
  try {
    if (S.flying) await flyAway(rect, label, request, back);
    const r = await request;
    toast(r.listening ? t("handed.listening") : t("handed.later"));
  } catch (e) {
    toast(t("hand.failed", { e: e.message }));
  } finally {
    S.handing = false;
    S.flying = false;
    refreshHead();
    renderSide();
  }
}

// -- where you are -------------------------------------------------------------------------------

let presenceTimer;
function here(id) {
  if (recall().item === id && $(".item.here")?.dataset.id === id) return;
  remember({ round: S.current, item: id });
  document.querySelectorAll(".item.here").forEach((c) => c.classList.remove("here"));
  card(id)?.classList.add("here");
  clearTimeout(presenceTimer);
  presenceTimer = setTimeout(() => tellPresence(id), 700);
}

/** What scrolls: the main column on a wide screen, the whole page on a narrow one. */
function scroller() {
  const main = $("main");
  return getComputedStyle(main).overflowY === "auto" ? main : document.scrollingElement;
}

/** Where you are on the page: the item (innermost) at the top of what you see, and how far down. */
function placeAnchor() {
  const sc = scroller();
  const head = $(".head");
  let edge = sc === document.scrollingElement ? 0 : sc.getBoundingClientRect().top;
  if (head && getComputedStyle(head).position === "sticky") edge += head.offsetHeight;
  const line = edge + 40;
  let best = null;
  for (const box of document.querySelectorAll("main [data-id]")) {
    const r = box.getBoundingClientRect();
    if (r.top <= line && r.bottom > line) best = box; // later in the page = nested deeper
    else if (!best && r.top > line) {
      best = box;
      break;
    }
  }
  return best ? { id: best.dataset.id, top: best.getBoundingClientRect().top, at: sc.scrollTop } : null;
}

/** After the page was drawn again: the same item at the same spot, also while pictures above it
 * finish loading (until you scroll yourself). */
function holdPlace(anchor, wrap) {
  if (!anchor) return;
  const apply = () => {
    const box = card(anchor.id);
    if (box) scroller().scrollTop += box.getBoundingClientRect().top - anchor.top;
    else scroller().scrollTop = anchor.at;
  };
  apply();
  const watch = new ResizeObserver(apply);
  watch.observe(wrap);
  const stop = () => {
    watch.disconnect();
    for (const kind of ["wheel", "touchstart", "keydown", "pointerdown"]) removeEventListener(kind, stop, true);
  };
  for (const kind of ["wheel", "touchstart", "keydown", "pointerdown"]) addEventListener(kind, stop, true);
  setTimeout(stop, 2500);
}

function card(id) {
  return document.querySelector(`main [data-id="${CSS.escape(id)}"]`);
}

/** Is this card really on the screen's page: there, with a size, not hidden by anything? */
function shown(box) {
  if (!box || !box.isConnected || !box.getClientRects().length) return false;
  if (box.offsetHeight < 8 || getComputedStyle(box).visibility === "hidden") return false;
  for (let n = box; n && n !== document.body; n = n.parentElement) {
    if (Number(getComputedStyle(n).opacity) < 0.05) return false;
  }
  const words = box.querySelector(".top > .text");
  return !words || (words.getClientRects().length > 0 && words.offsetHeight >= 8);
}

/** The round's items whose cards the browser doesn't show. The page draws every item, so this is
 * something else at work in the browser: an extension that hides or removes parts of pages (a
 * content blocker hiding what mentions a word, say). The header says so, with the items. */
function checkHidden() {
  const drawn = S.round && S.view === "round" && $("main .wrap .head");
  const hidden = drawn ? allItems(S.round.doc).filter((it) => !shown(card(it.id))).map((it) => it.number) : [];
  if (hidden.join() === S.hidden.join()) return;
  S.hidden = hidden;
  refreshHead();
}

let hiddenTimer;
function watchHidden() {
  const soon = () => {
    clearTimeout(hiddenTimer);
    hiddenTimer = setTimeout(checkHidden, 250);
  };
  new MutationObserver(soon).observe(document.documentElement, {
    subtree: true, childList: true, attributes: true, attributeFilter: ["style", "class", "hidden"],
  });
  addEventListener("resize", soon);
  setInterval(checkHidden, 5000); // a style sheet an extension adds from outside leaves no trace in the page
}

// -- the sidebar ---------------------------------------------------------------------------------

function applyProject() {
  const project = (S.state && S.state.project) || BOOT.project || {};
  if (project.accent) {
    const root = document.documentElement.style;
    root.setProperty("--accent", project.accent);
    // Text on the accent: dark on a light accent, white on a dark one.
    root.setProperty("--accent-ink", luminance(project.accent) > 0.4 ? "#0f1714" : "#ffffff");
  }
  $("#project").textContent = project.title || "";
  document.title = `${project.title ? project.title + " · " : ""}${t("brand")}`;
}

function luminance(hex) {
  let h = hex.replace("#", "");
  if (h.length === 3) h = [...h].map((c) => c + c).join("");
  const [r, g, b] = [0, 2, 4].map((i) => {
    const v = parseInt(h.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
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

function renderViews() {
  const nav = $("#views");
  nav.replaceChildren();
  const ideas = button("view", `${icon("idea")}<span>${esc(t("ideas"))}</span>`
    + (S.ideas.length ? `<span class="n">${S.ideas.length}</span>` : ""), () => showIdeas());
  if (S.view === "ideas") ideas.setAttribute("aria-current", "true");
  nav.append(ideas);
  if (S.questions.length) {
    nav.append(button("view asks", `${icon("question")}<span>${esc(t("asks.title"))}</span><span class="badge">${S.questions.length}</span>`, openAsk));
  }
}

function renderSide() {
  renderViews();
  const list = $("#rounds");
  list.innerHTML = "";
  const rounds = shownRounds();
  if (!rounds.length) {
    list.append(el("li", "empty", esc(t("no.rounds"))));
    return;
  }
  for (const r of rounds) {
    const li = el("li");
    const b = button(null, "", () => openRound(r.slug).catch((e) => toast(e.message)));
    if (r.slug === S.current && S.view === "round") b.setAttribute("aria-current", "true");
    const c = r.counts || { total: 0 };
    const done = (c.total || 0) - (c.open || 0);
    const bits = r.error ? [esc(r.error)] : [esc(t("of", { a: done, b: c.total || 0 }))];
    if (r.round > 1) bits.push(esc(t("round", { n: r.round })));
    if (r.sent) bits.push(`<span class="sent">${esc(t("side.sent"))}</span>`);
    b.innerHTML = `${ring(c)}<span><span class="title">${esc(r.title)}</span><span class="sub">${bits.join(" · ")}</span></span>`
      + (c.retest ? `<span class="badge" title="${esc(t("retest.count", { n: c.retest }))}">${c.retest}</span>`
        : r.unseen ? `<span class="new-dot" title="${esc(t("new.replies"))}"></span>` : "");
    li.append(b);
    list.append(li);
  }
}

/** The open round's numbers in the sidebar, as they are on this page right now. */
function syncSide() {
  const entry = summary();
  if (entry && S.round) entry.counts = counts();
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
    if (a.extra && !a.verdict) continue; // a note handed back under "Anything else": nothing to answer
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
  const entry = summary() || {};
  // A round with `owner: NAME` goes to the session listening as NAME, so "listening" is per round.
  const owner = (doc.meta && doc.meta.owner) || "";
  const listeners = S.state && S.state.listeners;
  const many = listeners ? listeners[owner] || 0 : 0;
  const listening = listeners ? many > 0 : Boolean(S.state && S.state.listening);
  const meta = [];
  if (doc.about) meta.push(esc(t("about", { t: aboutText(doc.about) })));
  if (state.round > 1) meta.push(esc(t("round", { n: state.round })));
  if (doc.meta && doc.meta.commit) {
    meta.push(`<button type="button" class="link mono commit-link" data-ref="${esc(doc.meta.commit)}" title="${esc(t("commit.show"))}">${esc(t("commit", { c: doc.meta.commit }))}</button>`);
  }
  meta.push(state.sent
    ? `${esc(t("sent", { t: clock(state.sent) }))} · <span class="${entry.read ? "read" : ""}">${esc(entry.read ? t("read") : t("unread"))}</span>`
    : esc(t("not.sent")));
  const pct = (n) => `${(100 * n) / Math.max(c.total, 1)}%`;
  const bar = VERDICTS.map((v) => `<span style="width:${pct(c[v])};background:${colour(v)}"></span>`).join("");
  const tally = [...VERDICTS, "open"]
    .filter((v) => c[v] || v === "open")
    .map((v) => {
      const k = S.jump && S.jump.v === v ? idsOf(v).indexOf(S.jump.id) : -1;
      const at = k >= 0 ? `${k + 1}/` : "";
      return `<button type="button" class="jump" data-v="${v}" ${c[v] ? "" : "disabled"} title="${esc(t("jump.tip"))}">`
        + `${v === "open" ? "" : `<i style="background:${colour(v)}"></i>`}<b>${at}${c[v]}</b> ${esc(t("count." + v))}</button>`;
    })
    .join("");
  const typing = document.activeElement && document.activeElement.classList.contains("hand-msg");
  const caret = typing ? document.activeElement.selectionStart : 0;
  head.innerHTML = `
    <div class="row">
      <div class="titles"><h1>${esc(doc.title)}</h1><div class="meta">${meta.map((m) => `<span>${m}</span>`).join("")}</div></div>
      <div class="actions">
        <div class="send">
          <div class="handbox">
            <input type="text" class="hand-msg" maxlength="2000" autocomplete="off">
            <button type="button" class="hand-more" tabindex="-1">${icon("message")}</button>
            <button type="button" class="primary hand">${icon("send")}<span></span></button>
          </div>
          <span class="listening ${listening ? "on" : ""}" title="${esc(listening ? t("listening.tip") : t("not.listening.tip"))}">${esc(many > 1 ? t("listening.many", { n: many }) : listening ? t("listening") : t("not.listening"))}</span>
        </div>
        <span class="bell-slot"></span>
      </div>
    </div>
    <div class="bar" aria-hidden="true">${bar}</div>
    <div class="status"><div class="tally">${tally}</div><span class="saved"></span>
      <button type="button" class="link copy-summary">${icon("copy")}<span>${esc(t("summary.copy"))}</span></button></div>`
    + (S.hidden.length ? `<div class="hidden-note" role="alert">${icon("blocked")}<span><b>${esc(t(S.hidden.length === 1 ? "hidden.one" : "hidden.many", { n: S.hidden.length, list: S.hidden.join(", ") }))}</b> ${esc(t("hidden.why"))}</span></div>` : "");
  $(".bell-slot", head).replaceWith(bellButton());
  $(".copy-summary", head).onclick = copySummary;
  head.querySelectorAll(".jump").forEach((b) => (b.onclick = () => jumpTo(b.dataset.v)));
  const hand = $(".hand", head);
  const asks = ownAsks();
  $("span", hand).textContent = S.handing ? t("handing") : asks.length ? t("hand.answer") : state.sent ? t("hand.again") : t("hand.back");
  hand.title = asks.length && !S.handing ? t("hand.answer.tip", { n: asks.reduce((n, set) => n + set.questions.length, 0) }) : "";
  hand.disabled = S.handing || S.flying;
  hand.onclick = () => handBack();
  const box = $(".handbox", head);
  box.classList.toggle("away", S.flying);
  const msg = $(".hand-msg", head);
  msg.placeholder = t("hand.msg.ph");
  msg.value = S.drafts[S.current] || "";
  box.classList.toggle("has-text", Boolean(msg.value));
  msg.oninput = () => {
    S.drafts[S.current] = msg.value;
    box.classList.toggle("has-text", Boolean(msg.value));
  };
  msg.onkeydown = (e) => {
    if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); handBack(); }
    if (e.key === "Escape") msg.blur();
  };
  const more = $(".hand-more", head);
  more.title = more.ariaLabel = t("hand.msg.toggle");
  more.onclick = () => { box.classList.toggle("open"); if (box.classList.contains("open")) msg.focus(); };
  if (S.handboxOpen) box.classList.add("open");
  if (typing) { msg.focus(); msg.setSelectionRange(caret, caret); }
  showSaved(head);
}

/** "20 minutes" from the checklist, in the page's language. */
function aboutText(text) {
  const m = text.trim().match(/^(\d+(?:[.,]\d+)?)(?:\s*[-–]\s*(\d+(?:[.,]\d+)?))?\s*(minutes?|mins?\.?|minuten?|hours?|hrs?\.?|h|stunden?|std\.?)$/i);
  if (!m) return text;
  const n = m[2] ? `${m[1]}–${m[2]}` : m[1];
  const unit = /^(h|stund|std)/i.test(m[3]) ? "hour" : "minute";
  return t(`unit.${unit}${n === "1" ? "" : "s"}`, { n });
}

/** The tally's buttons: each click goes to the next item of that kind; another kind starts over. */
function jumpTo(v) {
  const all = allItems(S.round.doc).map((it) => it.id);
  const ids = idsOf(v);
  if (!ids.length) return;
  checkHidden();
  if (!ids.some((id) => shown(card(id)))) {
    // Nothing of this kind is on the page to go to: say why instead of doing nothing.
    S.jump = null;
    refreshHead();
    $(".hidden-note")?.scrollIntoView({ block: "nearest" });
    return toast(t("hidden.jump"));
  }
  // On from the item the last click went to, by its place in the round: answered in between,
  // it's no longer of this kind, and the next click goes to the first one after it, not one further.
  const from = S.jump && S.jump.v === v ? all.indexOf(S.jump.id) : -1;
  let i = from < 0 ? 0 : Math.max(ids.findIndex((id) => all.indexOf(id) > from), 0);
  while (!shown(card(ids[i]))) i = (i + 1) % ids.length; // past the ones the browser hides
  S.jump = { v, id: ids[i] };
  refreshHead();
  const target = card(ids[i]);
  target.scrollIntoView({ block: "center" });
  target.classList.remove("flash");
  void target.offsetWidth; // restart the animation
  target.classList.add("flash");
  here(ids[i]);
}

/** The round's items with this answer ("open": none yet), in their order on the page. */
function idsOf(v) {
  return allItems(S.round.doc).filter((it) => !it.extra || S.round.state.items[it.id]?.verdict)
    .map((it) => it.id).filter((id) => (S.round.state.items[id]?.verdict || "open") === v);
}

function refreshHead() {
  const head = $(".head");
  if (head && S.round) renderHead(head);
}

/** After an answer changed: the header's numbers, the sections' counts, the sidebar. */
function refreshTotals() {
  refreshHead();
  updateSectionCounts();
  syncSide();
}

function codeBlock(b) {
  const box = el("div", "code");
  box.dataset.code = b.id;
  const pre = el("pre");
  pre.textContent = b.text;
  const tools = el("div", "tools");
  const copy = button("quiet tiny", esc(t("copy")), async () => {
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
  });
  tools.append(el("span", "lang", esc(b.lang || "")));
  if (b.runnable && BOOT.local !== false) tools.append(runButton(b));
  tools.append(copy);
  box.append(tools, pre);
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
  if (area.hidden || !area.isConnected) return;
  const least = area.classList.contains("big") ? 100 : area.classList.contains("small") ? 40 : area.classList.contains("compose") ? 30 : 60;
  area.style.height = "auto";
  area.style.height = `${Math.max(least, area.scrollHeight + 2)}px`;
}

// -- the conversation: what you said and picked, Claude's replies and re-test notes, in time order --
//
// One column, oldest at the top: yours on the right, Claude's on the left, a thin line where Claude
// sent the item back for another look. Claude's newest bubble is marked. Everything you add goes in
// through the writing box at the bottom and lands below the last bubble.

const unfolded = new Set();   // older rounds you opened ("item:round"), while the page is open
const editing = new Set();    // your bubbles open for changing their words
const DRAFT = "review-desk:draft";

function newId() {
  return `m${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

/** Now, written the way the desk writes times ("2026-11-16 21:05"). */
function nowStamp() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** As the desk does it: when you first answered the item in this round (verdict, note or file). */
function stampAnswer(a) {
  a.answered = a.verdict || a.note.trim() || a.files.length ? a.answered || nowStamp() : null;
}

/** As the desk does it (store.mark): the verdict you picked as a line in the conversation; changing
 *  your mind right away changes that line, a first verdict taken back right away goes. */
function markLocally(a, before) {
  const thread = a.messages;
  const last = thread[thread.length - 1];
  const fresh = last && last.kind === "mark" && !(a.retest && a.retest.at >= last.at);
  if (a.verdict === before) {
    const lines = thread.filter((m) => m.kind === "mark");
    if (lines.length) lines[lines.length - 1].severity = a.severity;
  } else if (fresh && !a.verdict && !last.prev) {
    thread.pop();
  } else if (fresh) {
    Object.assign(last, { verdict: a.verdict, severity: a.severity, at: nowStamp() });
  } else {
    thread.push({ id: `v-${newId()}`, from: "you", kind: "mark", text: "", verdict: a.verdict, severity: a.severity,
      at: nowStamp(), ...(before ? { prev: before } : {}) });
  }
}

/** A bubble's time: the clock today, with the day before that. */
function when(at) {
  if (!at) return "";
  if (at.slice(0, 10) === nowStamp().slice(0, 10)) return clock(at);
  const day = new Date(at.slice(0, 10) + "T12:00").toLocaleDateString(S.lang, { day: "numeric", month: "short" });
  return `${day} ${clock(at)}`;
}

function verdictChip(v, severity) {
  if (!v) return "";
  return `<span class="chip verdict" style="background:${colour(v)}">${esc(t(v))}${severity && !isPlan() ? ` · ${esc(t(severity))}` : ""}</span>`;
}

/** The order of an item's conversation. Each re-test starts a round; a message or file belongs to
 *  the round whose re-test came before it. In a round: Claude's note on what changed first, then
 *  the rest by time. Answers from before verdicts and notes were messages (one note per round)
 *  show as a verdict line and a note bubble at the time you first answered. */
function entriesOf(a, list) {
  const history = a ? a.history : [];
  const last = history.length;
  const openers = a ? [...history.map((h) => h.retest), a.retest] : [null];
  const roundOf = (at) => {
    if (!at) return last;
    let k = 0;
    openers.forEach((r, i) => { if (r && r.at < at) k = i; });
    return k;
  };
  const out = [];
  const marked = new Set(list.filter((m) => m.kind === "mark").map((m) => roundOf(m.at)));
  const start = (k) => (openers[k] && openers[k].at) || "";
  openers.forEach((r, k) => {
    if (r) out.push({ type: "retest", seg: k, key: "", rank: 0, r, html: k < last ? history[k].retest_html : r.html });
  });
  const answers = a ? [...history.map((h, k) => ({ h, k, past: true })), { h: a, k: last, past: false }] : [];
  for (const { h, k, past } of answers) {
    const key = h.answered || start(k);
    if (h.verdict && !marked.has(k) && (past || h.answered)) {
      out.push({ type: "mark", seg: k, key, rank: 1, m: { verdict: h.verdict, severity: h.severity, at: h.answered } });
    }
    if (h.note.trim()) out.push({ type: "oldnote", seg: k, key, rank: 2.5, h, past });   // after its verdict line of the same minute
    for (const f of h.files) out.push({ type: "file", seg: roundOf(f.at), key: f.at || "~", rank: 2, f, past });
  }
  list.forEach((m, i) => {
    if (m.from !== "claude" && m.kind !== "mark" && !m.text.trim() && !editing.has(m.id)) return; // never written
    out.push({ type: m.kind === "mark" ? "mark" : "msg", seg: roundOf(m.at), key: m.at || "~", rank: 2, m, i });
  });
  const by = (x, y) => (x < y ? -1 : x > y ? 1 : 0);
  return out.sort((x, y) => x.seg - y.seg || by(x.key, y.key) || x.rank - y.rank || (x.i || 0) - (y.i || 0));
}

/** The line a reply starts with: what it answers, in a few words; a click shows that bubble. */
function quoteText(target) {
  const who = target.from === "claude" ? t("claude") : t("your." + target.kind);
  return `${who}: ${(target.text || "").trim().split("\n")[0].replace(/[`*]/g, "")}`;   // Claude's Markdown, as plain words
}

function quoteLine(m, list, wrap) {
  const target = m.to && list.find((x) => x.id === m.to);
  if (!target) return null;
  return button("quote", `${icon("reply")}<span>${esc(quoteText(target))}</span>`, () => wrap.show(target.id), t("quote.show"));
}

/** Words you can change in place: plain text, or a box while ✎ is on. */
function editable(box, key, text, save) {
  if (!editing.has(key)) {
    box.append(el("div", "said mine", esc(text)));
    return;
  }
  const area = el("textarea", "note small");
  area.rows = 1;
  area.value = text;
  area.dataset.edit = key;
  area.oninput = () => {
    autosize(area);
    save(area.value);
  };
  area.onkeydown = (e) => {
    if (e.key === "Escape" || (e.key === "Enter" && (e.ctrlKey || e.metaKey))) area.blur();
  };
  area.onblur = () => {
    editing.delete(key);
    const wrap = box.closest(".convo-wrap");
    setTimeout(() => wrap?.draw());   // after the click that took the cursor away
  };
  box.append(area);
}

function editButton(key, wrap) {
  return button("quiet tiny edit", icon("edit"), () => {
    editing.add(key);
    wrap.opened = key;    // the redraw puts the cursor there
    wrap.draw();
  }, t("edit"));
}

function messageBox(id, m, list, wrap) {
  const mine = m.from !== "claude";
  const box = el("div", `bubble ${mine ? "you" : "claude"} ${m.kind}`);
  box.dataset.mid = m.id;
  const head = el("div", "who");
  const quote = quoteLine(m, list, wrap);
  if (mine) {
    head.innerHTML = `${icon(m.kind === "idea" ? "idea" : m.kind === "question" ? "question" : m.kind === "note" ? "edit" : "reply")}<span>${esc(t("your." + m.kind))}</span>`
      + (m.kind === "idea" && m.status && m.status !== "new" ? `<span class="chip ${m.status}">${esc(t("idea." + m.status))}</span>` : "")
      + `<span class="at">${esc(when(m.at))}</span>`;
    head.append(editButton(m.id, wrap), button("quiet tiny remove", icon("remove"), () => {
      list.splice(list.indexOf(m), 1);
      editing.delete(m.id);
      change(id, { delete: true }, 0, m.id);
      wrap.draw();
    }, t("remove")));
    box.append(head);
    if (quote) box.append(quote);
    editable(box, m.id, m.text, (text) => {
      m.text = text;
      change(id, { kind: m.kind, text, ...(m.to ? { to: m.to } : {}) }, 600, m.id);
    });
  } else {
    head.innerHTML = `<span class="avatar">C</span><span>${esc(t("claude"))}</span><span class="at">${esc(when(m.at))}</span>`;
    box.append(head);
    if (quote) box.append(quote);
    box.append(el("div", "said", m.html || esc(m.text)));
    const tools = el("div", "tools");
    tools.append(button("quiet tiny", `${icon("reply")}<span>${esc(t("reply"))}</span>`, () => wrap.replyTo(m.id)));
    box.append(tools);
  }
  return box;
}

/** A verdict you picked: a small line on your side. */
function markLine(m) {
  const line = el("div", "mark-line");
  if (m.id) line.dataset.mid = m.id;
  line.innerHTML = m.verdict
    ? `<span>${esc(t("picked"))}</span>${verdictChip(m.verdict, m.severity)}<span class="at">${esc(when(m.at))}</span>`
    : `<span>${esc(t("took.back"))}</span><span class="at">${esc(when(m.at))}</span>`;
  return line;
}

/** Claude's note when it sent the item back: what changed. */
function retestBox(e) {
  const box = el("div", "bubble claude retest-note");
  box.innerHTML = `<div class="who"><span class="avatar">C</span><span>${esc(t("changed"))}</span><span class="at">${esc(when(e.r.at))}</span></div>`
    + `<div class="said">${e.html || esc(t("changed.none"))}</div>`;
  return box;
}

/** A note from before notes were messages: the round's one note (this round's can still change). */
function oldNoteBox(id, e, wrap) {
  const h = e.h;
  const box = el("div", "bubble you note");
  const head = el("div", "who");
  head.innerHTML = `${icon("edit")}<span>${esc(t("your.note"))}</span><span class="at">${esc(when(h.answered))}</span>`;
  box.append(head);
  if (e.past) {
    box.append(el("div", "said mine", esc(h.note.trim())));
    return box;
  }
  const key = `note:${id}`;
  head.append(editButton(key, wrap), button("quiet tiny remove", icon("remove"), () => {
    h.note = "";
    editing.delete(key);
    change(id, { note: "" });
    wrap.draw();
  }, t("remove")));
  editable(box, key, h.note, (text) => {
    h.note = text;
    change(id, { note: text }, 600);
  });
  return box;
}

/** A file you added, as a bubble of its own (this round's can be taken back). */
function fileBox(id, e) {
  const box = el("div", "bubble you file-bubble");
  box.innerHTML = `<div class="who">${icon(e.f.kind === "recording" ? "record" : e.f.kind === "log" ? "log" : "attach")}`
    + `<span>${esc(t("your.file"))}</span><span class="at">${esc(when(e.f.at))}</span></div>`;
  box.append(filesRow(id, [e.f], e.past));
  return box;
}

/** An item's conversation (`a` and `parts` are null for the round's own "Anything else?"), with
 *  the writing box under it. */
function conversation(id, a, parts, list) {
  const wrap = el("div", "convo-wrap");
  const roundOfMessage = new Map();
  const roundNumber = (k) => (k < a.history.length ? a.history[k].round : a.retest ? a.retest.round : S.round.state.round);
  const kinds = a ? ["note", "question", "idea"] : ["question", "idea"];
  const draftKey = `${DRAFT}:${S.current}:${id}`;
  const saved = stored(draftKey);
  const draft = { text: saved.text || "", kind: kinds.includes(saved.kind) ? saved.kind : kinds[0], to: saved.to || null };

  // -- the writing box
  const composer = el("div", "composer");
  const replying = el("div", "replying");
  const area = el("textarea", "compose");
  area.rows = 1;
  area.value = draft.text;
  area.setAttribute("aria-label", t("compose.ph"));
  const kindRow = el("div", "kinds");
  kindRow.setAttribute("role", "group");
  const kindButtons = {};
  for (const k of kinds) {
    kindButtons[k] = button("", `${icon(k === "note" ? "edit" : k)}<span>${esc(t("add." + k))}</span>`, () => {
      draft.kind = k;
      keep();
      refresh();
      area.focus();
    });
    kindRow.append(kindButtons[k]);
  }
  const attach = button("quiet small-button", `${icon("attach")}<span>${esc(t("attach"))}</span>`, (e) => {
    e.stopPropagation();
    attachMenu(e.currentTarget, id);
  });
  const add = button("primary send", `<span>${esc(t("add"))}</span>${icon("send")}`, () => post(), t("add.hint"));
  const row = el("div", "row");
  row.append(kindRow, attach, el("span", "keys", esc(t("add.hint"))), add);
  composer.append(replying, area, row);
  // A click on the box's buttons leaves the cursor in the box (so the box stays open meanwhile).
  composer.addEventListener("mousedown", (e) => { if (e.target.closest(".row button, .replying button")) e.preventDefault(); });
  if (parts) parts.note = area;

  function keep() {
    try {
      if (draft.text.trim() || draft.to || draft.kind !== kinds[0]) store(draftKey, draft);
      else localStorage.removeItem(draftKey);
    } catch {}
  }
  function refresh() {
    for (const k of kinds) kindButtons[k].setAttribute("aria-pressed", String(draft.kind === k));
    const target = draft.to && list.find((x) => x.id === draft.to);
    replying.hidden = !target;
    replying.replaceChildren();
    if (target) {
      replying.append(el("span", "what", `${icon("reply")}<span>${esc(t("replying", { what: quoteText(target) }))}</span>`),
        button("quiet tiny remove", icon("remove"), () => {
          draft.to = null;
          keep();
          refresh();
        }, t("reply.drop")));
    }
    area.placeholder = draft.kind !== "note" ? t("ph." + draft.kind)
      : target ? t("ph.comment")
      : a && a.verdict && a.verdict !== "works" ? t(`note.${a.verdict}`)
      : t("compose.ph");
    add.disabled = !area.value.trim();
    composer.classList.toggle("open", Boolean(area.value.trim() || target || draft.kind !== kinds[0]));
  }
  area.oninput = () => {
    draft.text = area.value;
    keep();
    autosize(area);
    add.disabled = !area.value.trim();
    composer.classList.toggle("open", Boolean(area.value.trim() || draft.to || draft.kind !== kinds[0]));
  };
  area.onkeydown = (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      post();
    }
  };

  /** What is in the box goes into the conversation as a new bubble at the bottom. */
  function post(focus = true) {
    const text = area.value.trim();
    if (!text) return false;
    const kind = draft.kind === "note" && draft.to ? "comment" : draft.kind;
    const m = { id: newId(), from: "you", kind, text, at: nowStamp() };
    if (draft.to) m.to = draft.to;
    if (kind === "idea") m.status = "new";
    list.push(m);
    change(id, { kind, text, ...(m.to ? { to: m.to } : {}) }, 0, m.id);
    area.value = "";
    Object.assign(draft, { text: "", to: null, kind: kinds[0] });
    keep();
    wrap.draw();
    if (focus) area.focus();
    return true;
  }
  wrap.post = () => post(false);
  wrap.replyTo = (mid) => {
    draft.to = mid;
    if (draft.kind !== "question") draft.kind = kinds[0];
    keep();
    refresh();
    area.focus();
  };
  wrap.writeNote = () => {
    if (a) draft.kind = "note";
    keep();
    refresh();
    area.focus();
  };

  // -- the conversation
  wrap.draw = () => {
    const typing = document.activeElement === area ? { start: area.selectionStart, end: area.selectionEnd } : null;
    if (!wrap.opened && wrap.contains(document.activeElement) && document.activeElement.dataset.edit) {
      wrap.opened = document.activeElement.dataset.edit;    // a bubble you are changing keeps the cursor
    }
    const last = a ? a.history.length : 0;
    const entries = entriesOf(a, list);
    let latest = -1;
    entries.forEach((e, n) => { if (e.type === "retest" || (e.type === "msg" && e.m.from === "claude")) latest = n; });
    const sizes = {};
    for (const e of entries) sizes[e.seg] = (sizes[e.seg] || 0) + 1;

    wrap.replaceChildren();
    const convo = el("div", "convo");
    let seg = -1;
    let folded = false;
    entries.forEach((e, n) => {
      if (e.m && e.m.id) roundOfMessage.set(e.m.id, e.seg);
      if (e.seg !== seg) {
        seg = e.seg;
        const key = `${id}:${seg}`;
        const foldable = last >= 2 && seg < last - 1;     // three rounds or more: all but the last two fold
        folded = foldable && !unfolded.has(key);
        if (last > 0) convo.append(roundLine(seg, folded, foldable, key, sizes[seg]));
      }
      if (folded) return;
      const box = e.type === "retest" ? retestBox(e)
        : e.type === "mark" ? markLine(e.m)
        : e.type === "oldnote" ? oldNoteBox(id, e, wrap)
        : e.type === "file" ? fileBox(id, e)
        : messageBox(id, e.m, list, wrap);
      if (n === latest) {
        box.classList.add("latest");
        $(".who", box).querySelector("span:not(.avatar)").insertAdjacentHTML("afterend", `<span class="chip latest">${esc(t("latest"))}</span>`);
      }
      convo.append(box);
    });
    if (convo.children.length) wrap.append(convo);
    refresh();
    wrap.append(composer);
    wrap.querySelectorAll("textarea").forEach(autosize);   // on the page already (a redraw); else renderMain does it
    if (typing && area.isConnected) {
      area.focus({ preventScroll: true });
      area.setSelectionRange(typing.start, typing.end);
    }
    const opened = wrap.opened && wrap.querySelector(`textarea[data-edit="${CSS.escape(wrap.opened)}"]`);
    wrap.opened = null;
    if (opened) {
      opened.focus();
      opened.setSelectionRange(opened.value.length, opened.value.length);
    }
  };

  function roundLine(k, folded, foldable, key, size) {
    const n = roundNumber(k);
    let words = k === 0 ? t("round.n", { n }) : t("round.back", { n });
    if (folded) {
      const h = a.history[k];
      words = t("round.folded", { n, v: h.verdict ? t(h.verdict) : t("open"), m: size });
    }
    if (!foldable) return el("div", "round-line", `<span>${esc(words)}</span>`);
    const line = button("round-line", `<span>${esc(words)}</span>${icon(folded ? "down" : "up")}`, () => {
      if (folded) unfolded.add(key);
      else unfolded.delete(key);
      wrap.draw();
    }, t(folded ? "round.open" : "round.close"));
    line.setAttribute("aria-expanded", String(!folded));
    return line;
  }

  /** Scrolls to a bubble (opening its round if it is folded) and makes it flash. */
  wrap.show = (mid) => {
    let box = wrap.querySelector(`[data-mid="${CSS.escape(mid)}"]`);
    if (!box && roundOfMessage.has(mid)) {
      unfolded.add(`${id}:${roundOfMessage.get(mid)}`);
      wrap.draw();
      box = wrap.querySelector(`[data-mid="${CSS.escape(mid)}"]`);
    }
    if (!box) return;
    box.scrollIntoView({ block: "center", behavior: "smooth" });
    box.classList.remove("flash");
    void box.offsetWidth;
    box.classList.add("flash");
  };

  return wrap;
}

/** Before a hand-back: what waits in a writing box goes in, so Claude gets it. */
function postDrafts() {
  for (const wrap of document.querySelectorAll("main .convo-wrap")) wrap.post();
}

// -- an item --------------------------------------------------------------------------------------

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
    parts.verdicts[v] = button(v, `${icon(v)}<span>${esc(t(v))}</span>`, () => {
      const before = a.verdict;
      a.verdict = a.verdict === v ? "" : v;
      const fields = { verdict: a.verdict };
      if (a.verdict !== "change" && a.severity) fields.severity = a.severity = "";
      stampAnswer(a);
      markLocally(a, before);
      change(b.id, fields);
      refreshCard(box, b);
      refreshTotals();
      if (a.verdict && a.verdict !== "works") box.convo.writeNote();
    });
    verdicts.append(parts.verdicts[v]);
  }
  answer.append(verdicts);

  parts.severity = el("div", "severity");
  parts.severity.append(el("span", null, esc(t("severity"))));
  for (const s of SEVERITIES) {
    parts.severities[s] = button(s, esc(t(s)), () => {
      a.severity = a.severity === s ? "" : s;
      markLocally(a, a.verdict);
      change(b.id, { severity: a.severity });
      refreshCard(box, b);
      refreshTotals();
    });
    parts.severity.append(parts.severities[s]);
  }
  answer.append(parts.severity);

  box.convo = conversation(b.id, a, parts, a.messages);   // with the writing box (parts.note)
  answer.append(box.convo);
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
  box.className = `item${a.verdict ? " v-" + a.verdict : " open"}${a.retest && !a.verdict ? " retesting" : ""}`
    + `${last.round === S.current && last.item === b.id ? " here" : ""}`;
  for (const v of VERDICTS) parts.verdicts[v].setAttribute("aria-pressed", String(a.verdict === v));
  parts.severity.hidden = a.verdict !== "change" || isPlan();
  for (const s of SEVERITIES) parts.severities[s].setAttribute("aria-pressed", String(a.severity === s));
  box.convo.draw();
}

function updateSectionCounts() {
  for (const part of document.querySelectorAll("section.part")) {
    const ids = [...part.querySelectorAll(".item")].map((c) => c.dataset.id)
      .filter((id) => !(S.round.state.items[id] || {}).extra || S.round.state.items[id].verdict); // handed-back notes: nothing to answer
    const done = ids.filter((id) => S.round.state.items[id] && S.round.state.items[id].verdict).length;
    const box = $("h2 .count", part);
    if (box) box.textContent = ids.length ? t("of", { a: done, b: ids.length }) : "";
  }
}

// -- the page --------------------------------------------------------------------------------------

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
  const typing = focused && focused.tagName === "TEXTAREA";
  const keep = typing ? {
    id: focused.closest("[data-id]")?.dataset.id,
    mid: focused.closest("[data-mid]")?.dataset.mid,
    compose: focused.classList.contains("compose"),
    start: focused.selectionStart,
    end: focused.selectionEnd,
  } : null;
  const anchor = keepPlace ? placeAnchor() : null;

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
    const h = el("h2", null, `<span>${s.kind === "else" ? esc(t("overall.title")) : s.html}</span>`);
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
  if (S.round.state.overall.files.length) overall.append(filesRow("overall", S.round.state.overall.files));
  const talk = conversation("overall", null, null, S.round.state.overall.messages);
  talk.draw();
  overall.append(talk);
  wrap.append(overall);

  main.replaceChildren(wrap);
  for (const code of S.runs.keys()) drawRun(code);
  updateSectionCounts();
  main.querySelectorAll("textarea.note").forEach(autosize);

  if (keep && keep.id) {
    const holder = card(keep.id);
    const again = keep.mid
      ? holder?.querySelector(`[data-mid="${CSS.escape(keep.mid)}"] textarea`)
      : keep.compose ? holder?.querySelector("textarea.compose")
      : keep.id === "overall" ? area : holder?.parts?.note;
    if (again) {
      again.hidden = false;
      again.focus({ preventScroll: true });
      again.setSelectionRange(keep.start, keep.end);
    }
  }
  if (keepPlace) holdPlace(anchor, wrap);
  checkHidden();
  markSeen();
}

// -- start -----------------------------------------------------------------------------------------

function renderWords() {
  document.documentElement.lang = S.lang;
  document.querySelectorAll("[data-t]").forEach((n) => (n.textContent = t(n.dataset.t)));
  $("#lang").value = S.lang;
  applyProject();
  renderConn();
  renderPrefs();
  setSide(document.querySelector(".desk").classList.contains("collapsed") || sideWas);
  sideWas = false;
}

// -- the sidebar can be folded away (Ctrl+B too); the choice is kept in this browser -----------------

const SIDE = "review-desk:side-collapsed";

function setSide(collapsed) {
  document.querySelector(".desk").classList.toggle("collapsed", collapsed);
  try { localStorage.setItem(SIDE, collapsed ? "1" : ""); } catch {}
  const hide = $("#side-hide"), show = $("#side-show");
  hide.innerHTML = icon("panel"); show.innerHTML = icon("panel");
  hide.title = hide.ariaLabel = t("side.hide");
  show.title = show.ariaLabel = t("side.show");
}
$("#side-hide").onclick = () => setSide(true);
$("#side-show").onclick = () => setSide(false);
addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "b") {
    e.preventDefault();
    setSide(!document.querySelector(".desk").classList.contains("collapsed"));
  }
});
let sideWas = false;
try { sideWas = Boolean(localStorage.getItem(SIDE)); } catch {}

$("#lang").onchange = (e) => {
  S.lang = e.target.value;
  try {
    localStorage.setItem(LANG, S.lang);
  } catch {}
  renderWords();
  renderSide();
  renderAsks();
  renderDesks();
  if (S.view === "ideas") renderIdeas();
  else renderMain({ keepPlace: true });
};

const onScroll = () => {
  clearTimeout(S.scrollTimer);
  S.scrollTimer = setTimeout(() => remember({ scroll: scroller().scrollTop }), 300);
};
$("main").addEventListener("scroll", onScroll, { passive: true });
window.addEventListener("scroll", onScroll, { passive: true });

(async function start() {
  initExtras();
  renderWords();
  watchHidden();
  arrived();
  try {
    await loadState();
    const last = recall();
    const slugs = S.state.rounds.map((r) => r.slug);
    await openRound(slugs.includes(last.round) ? last.round : slugs[0]);
    if (last.view === "ideas") await showIdeas();
    await loadQuestions();
    loadHistory();
  } catch {
    toast(t("offline"));
    renderMain();
  }
  connect();
})();
