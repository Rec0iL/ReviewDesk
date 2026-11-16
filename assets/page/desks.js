"use strict";
// The Desks list at the top of the sidebar: every desk running on this computer, and the sessions
// of this one, each with what waits there. Another desk opens in this tab (its own address); a
// session shows only its own rounds and question cards. Desks without a tab of their own chime
// and notify through this one (the desk decides which tab tells you, so you hear it once).

const SESSION = "review-desk:session";

/** The page on this computer (the phone reaches no other desk). */
const deskLocal = () => BOOT.local !== false;

let desksTimer;
function loadDesks() {
  if (!deskLocal()) return;
  clearTimeout(desksTimer);
  desksTimer = setTimeout(async () => {
    try {
      S.desks = (await api("/api/desks")).desks;
    } catch {
      return;
    }
    keepSession();
    renderDesks();
  }, 150);
}

/** What waits in some sessions, added up. */
function waits(list) {
  const w = { questions: 0, retests: 0, replies: 0, claude: 0, listening: false };
  for (const x of list) {
    if (!x) continue;
    w.questions += x.questions || 0;
    w.retests += x.retests || 0;
    w.replies += x.replies || 0;
    w.claude += x.claude || 0;
    w.listening = w.listening || Boolean(x.listening);
  }
  w.you = w.questions + w.retests + w.replies;
  return w;
}

function marks(w) {
  const tip = [
    w.questions && t("desk.questions", { n: w.questions }),
    w.retests && t("desk.retests", { n: w.retests }),
    w.replies && t("desk.replies", { n: w.replies }),
  ].filter(Boolean).join(" · ");
  return `<span class="marks">`
    + (w.listening ? `<span class="live" title="${esc(t("listening"))}"></span>` : "")
    + (w.claude ? `<span class="for-claude" title="${esc(t("desk.claude", { n: w.claude }))}">${icon("hourglass")}</span>` : "")
    + (w.you ? `<span class="badge" title="${esc(tip)}">${w.you}</span>` : "")
    + `</span>`;
}

/** The sessions of this desk: the main one first, then by name. */
function sessionsHere() {
  const here = (S.desks || []).find((d) => d.here);
  const names = new Set(Object.keys((here && here.sessions) || {}));
  for (const r of (S.state && S.state.rounds) || []) names.add(r.owner || "");
  return [...names].sort((a, b) => (a === "" ? -1 : b === "" ? 1 : a.localeCompare(b)));
}

function renderDesks() {
  const box = $("#desks");
  if (!box) return;
  const desks = S.desks || [];
  const sessions = sessionsHere();
  if (!deskLocal() || (desks.length < 2 && sessions.length < 2)) {
    box.hidden = true;
    box.replaceChildren();
    return;
  }
  box.hidden = false;
  const list = el("ul", "desk-list");
  for (const d of desks) {
    const li = el("li");
    const all = Object.values(d.sessions || {});
    const b = button("desk-row", `<span class="swatch" style="background:${esc(d.accent || "")}"></span>`
      + `<span class="title">${esc(d.title)}</span>${marks(waits(all))}`,
      d.here ? () => setSession(null) : () => goDesk(d.url));
    b.title = d.here ? d.project : t("desk.open", { p: d.project });
    if (d.here) b.setAttribute("aria-current", S.session === null ? "true" : "false");
    li.append(b);
    if (d.here && sessions.length > 1) {
      const sub = el("ul", "sessions");
      for (const name of sessions) {
        const s = button("session-row", `<span class="title">${esc(name || t("session.main"))}</span>`
          + marks(waits([(d.sessions || {})[name]])), () => setSession(name));
        if (S.session === name) s.setAttribute("aria-current", "true");
        const row = el("li");
        row.append(s);
        sub.append(row);
      }
      li.append(sub);
    }
    list.append(li);
  }
  box.replaceChildren(el("h2", null, esc(t("desks"))), list);
}

/** The session the sidebar shows (null: all), as you left it on this desk. */
function keptSession() {
  const v = stored(SESSION).v;
  return typeof v === "string" ? v : null;
}

/** A session that is gone (its rounds deleted) shows all again. */
function keepSession() {
  if (S.session !== null && !sessionsHere().includes(S.session)) setSession(null);
}

async function setSession(name) {
  S.session = name;
  store(SESSION, { v: name });
  sessionQuestions();
  renderDesks();
  renderAsks();
  const shown = shownRounds();
  if (S.view === "round" && shown.length && !shown.some((r) => r.slug === S.current)) await openRound(shown[0].slug);
  else renderSide();
}

/** The rounds of the session the sidebar shows. */
function shownRounds() {
  const rounds = (S.state && S.state.rounds) || [];
  return S.session === null ? rounds : rounds.filter((r) => (r.owner || "") === S.session);
}

/** The question cards of the session the sidebar shows. */
function sessionQuestions() {
  const all = S.allQuestions || [];
  S.questions = S.session === null ? all : all.filter((q) => (q.owner || "") === S.session);
}

/** Another desk, in this tab: at the item, when there is one. */
async function goDesk(url, slug, item) {
  try {
    await flushNow();
  } catch {}
  const at = slug ? `#round=${encodeURIComponent(slug)}${item ? `&item=${encodeURIComponent(item)}` : ""}` : "";
  location.href = url + at;
}

/** Opened from another desk at a round (`#round=…&item=…`): there first. */
function arrived() {
  const got = new URLSearchParams(location.hash.slice(1));
  if (!got.get("round")) return;
  remember({ round: got.get("round"), item: got.get("item") || "", view: "round" });
  S.session = null; // the round may be another session's: show all
  store(SESSION, { v: null });
  history.replaceState(null, "", location.pathname);
}

/** Something happened on a desk without a tab of its own: this tab tells you. */
function announcePeer(event) {
  const what = event.what === "desk" ? t("notify.desk") : t(`notify.${event.what}`) || (event.notify || {}).title || "";
  const title = `${event.title} · ${what}`;
  const body = event.what === "desk" ? "" : (event.notify || {}).body || "";
  const go = () => goDesk(event.url, event.slug, event.item);
  chime();
  if (document.hidden && S.prefs.notify && "Notification" in window && Notification.permission === "granted") {
    const n = new Notification(title, { body, tag: `${event.url}:${event.slug}:${event.what}`, icon: faviconData() });
    n.onclick = () => {
      window.focus();
      n.close();
      go();
    };
  } else toast(body ? `${title}: ${body}` : title, go);
  loadDesks();
}

/** You see the open round: Claude's replies in it count as seen (the Desks list counts the rest). */
function markSeen() {
  const r = summary();
  if (!r || !r.unseen || document.hidden || S.view !== "round") return;
  r.unseen = 0;
  api("/api/seen", { round: S.current }).catch(() => {});
  renderSide();
  loadDesks();
}

document.addEventListener("visibilitychange", markSeen);
