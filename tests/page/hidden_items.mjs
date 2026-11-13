// A check of the page in headless Chrome: the tally's jump always lands on an item you can see, and
// when something in the browser hides item cards (an extension that hides what mentions a word,
// say), the page says so instead of counting items nobody can find.
//
// Run: node tests/page/hidden_items.mjs <desk url> <round slug> [path to a folder with puppeteer-core]
// The round needs unanswered items, some of them with "Claude" in their text.
import { createRequire } from "module";

const [url, slug, modules = process.cwd() + "/"] = process.argv.slice(2);
const puppeteer = createRequire(modules)("puppeteer-core");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let failed = 0;
const check = (ok, what) => {
  if (!ok) failed += 1;
  console.log(`${ok ? "ok  " : "FAIL"} ${what}`);
};

// What an extension does to the page, three ways: an inline style, taking the card out, a style sheet.
const HIDERS = {
  none: () => {},
  style: () => setInterval(() => document.querySelectorAll("article.item").forEach((c) => {
    if (c.querySelector(".top > .text").textContent.includes("Claude")) c.style.setProperty("display", "none", "important");
  }), 300),
  remove: () => setInterval(() => document.querySelectorAll("article.item").forEach((c) => {
    if (c.querySelector(".top > .text").textContent.includes("Claude")) c.remove();
  }), 300),
  sheet: () => setInterval(() => document.querySelectorAll("article.item:not([data-x])").forEach((c) => {
    if (!document.querySelector("#x-hide")) {
      const s = document.createElement("style");
      s.id = "x-hide";
      s.textContent = "article.item[data-x='1'] { visibility: hidden !important; height: 0 !important; overflow: hidden; padding: 0; margin: 0; border: 0 }";
      document.head.append(s);
    }
    c.dataset.x = c.querySelector(".top > .text").textContent.includes("Claude") ? "1" : "0";
  }), 300),
};

const browser = await puppeteer.launch({ executablePath: process.env.CHROME || "/usr/bin/google-chrome", headless: "new", args: ["--lang=en-US", "--disable-gpu"] });
const look = (page) => page.evaluate(() => {
  const head = document.querySelector(".head").getBoundingClientRect();
  const top = getComputedStyle(document.querySelector(".head")).position === "sticky" ? Math.max(head.bottom, 0) : 0;
  const seen = (c) => {
    const r = c.getBoundingClientRect();
    return c.getClientRects().length > 0 && getComputedStyle(c).visibility !== "hidden" && Math.min(r.bottom, innerHeight) - Math.max(r.top, top) > 60;
  };
  const all = allItems(S.round.doc);
  const open = all.filter((it) => !S.round.state.items[it.id].verdict);
  const flashed = document.querySelector("main .item.here.flash");
  return {
    open: open.map((it) => it.number),
    openHidden: open.filter((it) => !document.querySelector(`main [data-id="${it.id}"]`)?.getClientRects().length || document.querySelector(`main [data-id="${it.id}"]`).offsetHeight < 8).map((it) => it.number),
    left: document.querySelector('.jump[data-v="open"]').textContent.trim(),
    side: document.querySelector('#rounds [aria-current] .sub').textContent,
    note: document.querySelector(".head .hidden-note")?.textContent || "",
    toast: document.querySelector("#toast.shown")?.textContent || "",
    flashed: flashed ? { id: flashed.dataset.id, open: flashed.classList.contains("open"), seen: seen(flashed) } : null,
  };
});

for (const [w, h, scale] of [[1280, 720, 1], [700, 720, 1], [1280, 420, 1], [853, 480, 1.5]]) {
  for (const hider of Object.keys(HIDERS)) {
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.setViewport({ width: w, height: h, deviceScaleFactor: scale });
    await page.evaluateOnNewDocument((s) => {
      localStorage.setItem("review-desk:lang", "en");
      // What a browser used for many sessions remembers: a round and an item long gone.
      localStorage.setItem("review-desk:last", JSON.stringify({ round: s, item: "9.9", view: "round", scroll: 99999 }));
      // ... and values no version of the page ever wrote.
      localStorage.setItem("review-desk:prefs", JSON.stringify("odd"));
      localStorage.setItem("review-desk:drafts", JSON.stringify([1, null]));
    }, slug);
    await page.evaluateOnNewDocument(`(${HIDERS[hider]})()`);
    await page.goto(url, { waitUntil: "domcontentloaded" });
    await sleep(1500);
    const tag = `${w}x${h}@${scale} ${hider}:`;
    let s = await look(page);
    const expectHidden = hider === "none" ? [] : s.openHidden;
    if (hider === "none") check(s.openHidden.length === 0 && !s.note, `${tag} every open item is on the page, no note`);
    else {
      check(s.openHidden.length > 0, `${tag} the stand-in extension hid open items (${s.openHidden.join(", ")})`);
      check(s.openHidden.every((n) => s.note.includes(n)) && s.note.includes(`${s.openHidden.length} item`), `${tag} the header names them: "${s.note.slice(0, 60)}…"`);
    }
    check(s.left === `${s.open.length} left`, `${tag} tally says ${s.left}`);
    const reachable = s.open.filter((n) => !expectHidden.includes(n));
    const landed = new Set();
    for (let k = 0; k < Math.max(reachable.length, 1) * 2; k++) {
      await page.click('.jump[data-v="open"]');
      await sleep(350);
      s = await look(page);
      if (reachable.length) {
        check(s.flashed && s.flashed.open && s.flashed.seen, `${tag} click ${k + 1} brings an unanswered item into view (${s.flashed && s.flashed.id}, ${s.left})`);
        if (s.flashed) landed.add(s.flashed.id);
      } else check(/hiding/.test(s.toast), `${tag} click ${k + 1} with nothing to go to says why`);
      if (w <= 760) await page.evaluate(() => scrollTo(0, 0)); // the header scrolls away on a narrow page
    }
    if (reachable.length) check(landed.size === reachable.length, `${tag} the clicks reached all ${reachable.length} items that can be seen`);
    // The hand-back check lists exactly the unanswered items (closed again with Escape: nothing is handed back).
    if (s.open.length) {
      await page.evaluate(() => scrollTo(0, 0));
      await page.click(".head .hand");
      await sleep(250);
      const listed = await page.evaluate(() => [...document.querySelectorAll("dialog[open] .open-list .mono")].map((n) => n.textContent));
      check(listed.join() === s.open.slice(0, 8).join(), `${tag} the hand-back check lists ${listed.join(", ")}`);
      await page.keyboard.press("Escape");
      await sleep(150);
      check(!(await page.$("dialog[open]")) && (await page.evaluate(() => !S.round.state.sent)), `${tag} closed without handing back`);
    }
    if (process.env.SHOTS && hider !== "sheet") await page.screenshot({ path: `${process.env.SHOTS}/hidden-${w}x${h}-${hider}.png` });
    check(errors.length === 0, `${tag} no script errors ${errors.join(" | ")}`);
    await page.close();
  }
}
await browser.close();
console.log(failed ? `${failed} FAILED` : "all fine");
process.exit(failed ? 1 : 0);
