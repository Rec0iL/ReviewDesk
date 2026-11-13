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
  audio: null,
  runs: new Map(),      // the open round's Run output, by code block
  view: "round",        // or "ideas": the Ideas board
  ideas: [],
  ideaFilter: "all",
  questions: [],        // Claude's question sets waiting for answers
  jump: null,           // the tally's last jump: {v, i}
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

function t(key, vars = {}) {
  const words = window.I18N[S.lang] || window.I18N.en;
  let s = words[key] ?? window.I18N.en[key] ?? key;
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

function toast(text) {
  const box = $("#toast");
  box.textContent = text;
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
  if (event.type === "run") return onRun(event);
  if (event.type === "phone") {
    S.phoneOn = Boolean(event.on);
    renderPrefs();
    return refreshPhone();
  }
  if (event.type === "listening") {
    if (S.state) S.state.listening = event.on;
    refreshHead();
    return;
  }
  if (event.type === "questions") {
    await loadQuestions();
    if (event.notify) announce(event);
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
  const open = allItems(S.round.doc).filter((it) => !(S.round.state.items[it.id] || {}).verdict);
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
    const foot = el("footer");
    foot.append(
      button("quiet", esc(t("open.anyway")), () => { answer = true; d.close(); }),
      button("primary", esc(t("open.show")), () => { d.close(); S.jump = null; jumpTo("open"); }),
    );
    d.append(el("header", null, `<h2>${esc(t("open.title"))}</h2>`), body, foot);
    d.showModal();
  });
}

async function handBack() {
  if (S.handing || !S.current) return;
  if (!(await confirmOpen())) return;
  S.handing = true;
  refreshHead();
  try {
    if (!(await flushNow())) throw new Error(S.failed || t("save.waiting"));
    const r = await api("/api/send", { round: S.current });
    S.round.state.sent = r.sent;
    const entry = summary();
    if (entry) Object.assign(entry, { sent: r.sent, read: false });
    toast(r.listening ? t("handed.listening") : t("handed.later"));
  } catch (e) {
    toast(t("hand.failed", { e: e.message }));
  } finally {
    S.handing = false;
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
  return document.querySelector(`[data-id="${CSS.escape(id)}"]`);
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
  const rounds = (S.state && S.state.rounds) || [];
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
      + (c.retest ? `<span class="badge" title="${esc(t("retest.count", { n: c.retest }))}">${c.retest}</span>` : "");
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
  const listening = Boolean(S.state && S.state.listening);
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
      const at = S.jump && S.jump.v === v && c[v] ? `${Math.min(S.jump.i, c[v] - 1) + 1}/` : "";
      return `<button type="button" class="jump" data-v="${v}" ${c[v] ? "" : "disabled"} title="${esc(t("jump.tip"))}">`
        + `${v === "open" ? "" : `<i style="background:${colour(v)}"></i>`}<b>${at}${c[v]}</b> ${esc(t("count." + v))}</button>`;
    })
    .join("");
  head.innerHTML = `
    <div class="row">
      <div class="titles"><h1>${esc(doc.title)}</h1><div class="meta">${meta.map((m) => `<span>${m}</span>`).join("")}</div></div>
      <div class="actions">
        <div class="send">
          <button type="button" class="primary hand">${icon("send")}<span></span></button>
          <span class="listening ${listening ? "on" : ""}" title="${esc(listening ? t("listening.tip") : t("not.listening.tip"))}">${esc(listening ? t("listening") : t("not.listening"))}</span>
        </div>
      </div>
    </div>
    <div class="bar" aria-hidden="true">${bar}</div>
    <div class="status"><div class="tally">${tally}</div><span class="saved"></span>
      <button type="button" class="link copy-summary">${icon("copy")}<span>${esc(t("summary.copy"))}</span></button></div>`;
  $(".copy-summary", head).onclick = copySummary;
  head.querySelectorAll(".jump").forEach((b) => (b.onclick = () => jumpTo(b.dataset.v)));
  const hand = $(".hand", head);
  $("span", hand).textContent = S.handing ? t("handing") : state.sent ? t("hand.again") : t("hand.back");
  hand.disabled = S.handing;
  hand.onclick = handBack;
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
  const ids = allItems(S.round.doc).map((it) => it.id).filter((id) => (S.round.state.items[id]?.verdict || "open") === v);
  if (!ids.length) return;
  S.jump = S.jump && S.jump.v === v ? { v, i: (S.jump.i + 1) % ids.length } : { v, i: 0 };
  const target = card(ids[S.jump.i]);
  refreshHead();
  if (!target) return;
  target.scrollIntoView({ block: "center" });
  target.classList.remove("flash");
  void target.offsetWidth; // restart the animation
  target.classList.add("flash");
  here(ids[S.jump.i]);
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
  const least = area.classList.contains("big") ? 100 : area.classList.contains("small") ? 40 : 60;
  area.style.height = "auto";
  area.style.height = `${Math.max(least, area.scrollHeight + 2)}px`;
}

// -- threads: your questions, ideas and replies, Claude's answers --------------------------------

function newId() {
  return `m${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
}

function messageBox(id, m, list, redraw) {
  const mine = m.from !== "claude";
  const box = el("div", `msg ${mine ? "you" : "claude"} ${m.kind}`);
  box.dataset.mid = m.id;
  const head = el("div", "who");
  if (mine) {
    head.innerHTML = `${icon(m.kind === "idea" ? "idea" : m.kind === "comment" ? "reply" : "question")}<span>${esc(t("your." + m.kind))}</span>`;
    if (m.kind === "idea" && m.status && m.status !== "new") head.innerHTML += `<span class="chip ${m.status}">${esc(t("idea." + m.status))}</span>`;
    head.append(button("quiet tiny remove", icon("remove"), () => {
      list.splice(list.indexOf(m), 1);
      change(id, { delete: true }, 0, m.id);
      redraw();
    }, t("remove")));
    box.append(head);
    const area = el("textarea", "note small");
    area.value = m.text;
    area.placeholder = t("ph." + m.kind);
    area.setAttribute("aria-label", t("your." + m.kind));
    area.oninput = () => {
      m.text = area.value;
      autosize(area);
      change(id, { kind: m.kind, text: m.text, ...(m.to ? { to: m.to } : {}) }, 600, m.id);
    };
    box.append(area);
    requestAnimationFrame(() => autosize(area));
  } else {
    const target = m.to && list.find((x) => x.id === m.to);
    head.innerHTML = `<span class="avatar">C</span><span>${esc(t("claude"))}</span>`
      + (target ? `<span class="to">${esc(t("on." + target.kind))}</span>` : "")
      + `<span class="at">${esc(clock(m.at))}</span>`;
    box.append(head, el("div", "said", m.html || esc(m.text)));
    const tools = el("div", "tools");
    tools.append(button("quiet tiny", `${icon("reply")}<span>${esc(t("reply"))}</span>`, () => addMessage(id, list, "comment", redraw, m.id)));
    box.append(tools);
  }
  return box;
}

function addMessage(id, list, kind, redraw, to) {
  const m = { id: newId(), from: "you", kind, text: "", at: "" };
  if (to) m.to = to;
  if (kind === "idea") m.status = "new";
  list.push(m);
  change(id, { kind, text: "", ...(to ? { to } : {}) }, 600, m.id);
  redraw();
  const area = document.querySelector(`[data-mid="${m.id}"] textarea`);
  if (area) area.focus();
}

function threadBlock(id, list) {
  const wrap = el("div", "thread-wrap");
  const draw = () => {
    wrap.replaceChildren();
    if (list.length) {
      const box = el("div", "thread");
      for (const m of list) box.append(messageBox(id, m, list, draw));
      wrap.append(box);
    }
    const add = el("div", "add");
    add.append(
      button("quiet small-button", `${icon("question")}<span>${esc(t("add.question"))}</span>`, () => addMessage(id, list, "question", draw)),
      button("quiet small-button", `${icon("idea")}<span>${esc(t("add.idea"))}</span>`, () => addMessage(id, list, "idea", draw)),
      button("quiet small-button", `${icon("attach")}<span>${esc(t("attach"))}</span>`, (e) => {
        e.stopPropagation();
        attachMenu(e.currentTarget, id);
      }),
    );
    wrap.append(add);
  };
  draw();
  return wrap;
}

// -- an item --------------------------------------------------------------------------------------

function retestBlock(a) {
  const box = el("div", "retest");
  box.innerHTML = `<div class="title">${icon("reply")}<b>${esc(t("retest.title", { n: a.retest.round }))}</b></div>`
    + (a.retest.html ? `<div class="said">${a.retest.html}</div>` : "");
  return box;
}

function historyBlock(a) {
  const box = el("div", "history");
  for (const h of [...a.history].reverse()) {
    const v = h.verdict ? t(h.verdict) : t("open");
    const d = el("details");
    d.innerHTML = `<summary><i style="background:${h.verdict ? colour(h.verdict) : "var(--control)"}"></i>${esc(t("history.round", { n: h.round, v }))}${h.severity ? ` (${esc(t(h.severity))})` : ""}</summary>`
      + (h.retest_html ? `<div class="said claude-said">${h.retest_html}</div>` : "")
      + (h.html ? `<div class="said">${h.html}</div>` : "");
    box.append(d);
  }
  return box;
}

function itemCard(b) {
  const a = S.round.state.items[b.id];
  const box = el("article", "item");
  box.dataset.id = b.id;
  const top = el("div", "top");
  top.append(el("div", "num", esc(b.number)), el("div", "text", `<p>${b.html}</p>`));
  const body = el("div", "body");

  if (a.retest) body.append(retestBlock(a));
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
      a.verdict = a.verdict === v ? "" : v;
      const fields = { verdict: a.verdict };
      if (a.verdict !== "change" && a.severity) fields.severity = a.severity = "";
      change(b.id, fields);
      refreshCard(box, b);
      refreshTotals();
      if (a.verdict && a.verdict !== "works") parts.note.focus();
    });
    verdicts.append(parts.verdicts[v]);
  }
  answer.append(verdicts);

  parts.severity = el("div", "severity");
  parts.severity.append(el("span", null, esc(t("severity"))));
  for (const s of SEVERITIES) {
    parts.severities[s] = button(s, esc(t(s)), () => {
      a.severity = a.severity === s ? "" : s;
      change(b.id, { severity: a.severity });
      refreshCard(box, b);
      refreshTotals();
    });
    parts.severity.append(parts.severities[s]);
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
  if (a.files.length) answer.append(filesRow(b.id, a.files));
  answer.append(threadBlock(b.id, a.messages));
  if (a.history.length) answer.append(historyBlock(a));
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
  if (S.round.state.overall.files.length) overall.append(filesRow("overall", S.round.state.overall.files));
  overall.append(threadBlock("overall", S.round.state.overall.messages));
  wrap.append(overall);

  main.replaceChildren(wrap);
  for (const code of S.runs.keys()) drawRun(code);
  updateSectionCounts();
  requestAnimationFrame(() => autosize(area));

  if (keep && keep.id) {
    const holder = card(keep.id);
    const again = keep.mid
      ? holder?.querySelector(`[data-mid="${CSS.escape(keep.mid)}"] textarea`)
      : keep.id === "overall" ? area : holder?.parts?.note;
    if (again) {
      again.hidden = false;
      again.focus({ preventScroll: true });
      again.setSelectionRange(keep.start, keep.end);
    }
  }
  if (keepPlace) holdPlace(anchor, wrap);
}

// -- start -----------------------------------------------------------------------------------------

function renderWords() {
  document.documentElement.lang = S.lang;
  document.querySelectorAll("[data-t]").forEach((n) => (n.textContent = t(n.dataset.t)));
  $("#lang").value = S.lang;
  applyProject();
  renderConn();
  renderPrefs();
}

$("#lang").onchange = (e) => {
  S.lang = e.target.value;
  try {
    localStorage.setItem(LANG, S.lang);
  } catch {}
  renderWords();
  renderSide();
  renderAsks();
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
  try {
    await loadState();
    const last = recall();
    const slugs = S.state.rounds.map((r) => r.slug);
    await openRound(slugs.includes(last.round) ? last.round : slugs[0]);
    if (last.view === "ideas") await showIdeas();
    await loadQuestions();
  } catch {
    toast(t("offline"));
    renderMain();
  }
  connect();
})();
