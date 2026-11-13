"use strict";
// Review Desk's extras: attachments (marked-up screenshots, screen recordings, log lines, any
// file), Run buttons with live output, and the viewer for pictures, recordings, files and the
// commit. Loaded before desk.js; uses its helpers when called, and starts with initExtras().

const IMAGE = /\.(png|jpe?g|gif|webp|avif|bmp|svg)$/i;
const VIDEO = /\.(webm|mp4|mov|mkv|ogv)$/i;
const TEXT = /\.(txt|log|md|json|csv|ya?ml|toml|ini|cfg|conf|rs|py|js|ts|sh|c|h|cpp|hpp|html|css|xml)$/i;
const FILE_ICON = { screenshot: "image", recording: "record", log: "log", file: "file" };
const RED = "#ff4d5e";
const COLOURS = [RED, "#ffc94d", "#4dd2ff", "#ffffff"];

// -- dialogs ---------------------------------------------------------------------------------------

function dialog(cls) {
  const d = el("dialog", `modal ${cls || ""}`);
  document.body.append(d);
  d.addEventListener("close", () => d.remove());
  d.addEventListener("click", (e) => {
    if (e.target === d) d.close(); // a click on the backdrop
  });
  return d;
}

function lightbox(url, video) {
  const d = dialog("lightbox");
  const media = video ? el("video") : el("img");
  media.src = url;
  if (video) Object.assign(media, { controls: true, autoplay: true });
  else media.alt = "";
  d.append(media, button("quiet close", icon("remove"), () => d.close(), t("close")));
  d.showModal();
}

function viewer(title, text, { line = 0, diff = false } = {}) {
  const d = dialog("viewer");
  const head = el("header", null, `<h2 class="mono">${esc(title)}</h2>`);
  head.append(button("quiet close", icon("remove"), () => d.close(), t("close")));
  const box = el("div", "lines");
  const rows = document.createDocumentFragment();
  text.replace(/\n$/, "").split("\n").forEach((s, i) => {
    const row = el("div", "line");
    row.dataset.n = i + 1;
    if (diff) {
      if (s.startsWith("+") && !s.startsWith("+++")) row.classList.add("add");
      else if (s.startsWith("-") && !s.startsWith("---")) row.classList.add("del");
      else if (s.startsWith("@@")) row.classList.add("hunk");
    }
    if (line === i + 1) row.classList.add("hit");
    row.textContent = s || " ";
    rows.append(row);
  });
  box.append(rows);
  d.append(head, box);
  d.showModal();
  const hit = $(".hit", box);
  if (hit) hit.scrollIntoView({ block: "center" });
}

async function openPath(given) {
  const m = given.match(/^(.*?)(?:#L(\d+)|:(\d+)(?::\d+)?)?$/);
  const path = m[1];
  const line = Number(m[2] || m[3] || 0);
  try {
    const data = await api(`/api/source?path=${encodeURIComponent(path)}`);
    viewer(line ? `${data.path}:${line}` : data.path, data.text, { line });
  } catch (e) {
    toast(t("viewer.failed", { e: e.message }));
  }
}

async function openCommit(ref) {
  try {
    const data = await api(`/api/commit?ref=${encodeURIComponent(ref)}`);
    viewer(`${t("commit", { c: ref })}`, data.text, { diff: true });
  } catch (e) {
    toast(t("viewer.failed", { e: e.message }));
  }
}

function fileUrl(name) {
  return `/files/${encodeURIComponent(S.current)}/files/${encodeURIComponent(name)}`;
}

async function showFile(f) {
  const url = fileUrl(f.name);
  if (IMAGE.test(f.name)) return lightbox(url, false);
  if (VIDEO.test(f.name)) return lightbox(url, true);
  if (f.kind === "log" || TEXT.test(f.name)) {
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error(r.statusText);
      return viewer(f.label || f.name, await r.text());
    } catch (e) {
      return toast(t("viewer.failed", { e: e.message }));
    }
  }
  const a = el("a");
  a.href = url;
  a.download = f.name;
  a.click();
}

// -- attachments ------------------------------------------------------------------------------------

async function upload(id, kind, blob, name, label = "") {
  const q = new URLSearchParams({ round: S.current, item: id, kind, name, label, client: CLIENT });
  const r = await fetch(`/api/upload?${q}`, {
    method: "POST",
    headers: { "X-Desk-Token": BOOT.token, "Content-Type": "application/octet-stream" },
    body: blob,
  }).catch(() => {
    throw new Error(t("save.waiting"));
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  await openRound(S.current, { keepPlace: true });
  return data.file;
}

async function removeFile(id, name) {
  try {
    await api("/api/file/remove", { round: S.current, item: id, name });
    await openRound(S.current, { keepPlace: true });
  } catch (e) {
    toast(t("save.failed", { e: e.message }));
  }
}

/** An attachment's own name, without the item the desk put in front of it. */
function withoutItem(name, id) {
  const prefix = `${id.replace(/\./g, "-").replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "")}-`;
  return name.startsWith(prefix) ? name.slice(prefix.length) : name;
}

function filesRow(id, files) {
  const row = el("div", "files");
  for (const f of files) {
    const chip = el("div", `file ${f.kind}`);
    const open = button("file-open", "", () => showFile(f), f.name);
    open.innerHTML = IMAGE.test(f.name)
      ? `<img src="${fileUrl(f.name)}" alt="" loading="lazy">`
      : `<span class="glyph">${icon(FILE_ICON[f.kind] || "file")}</span>`;
    const words = f.label || (f.kind === "file" ? withoutItem(f.name, id) : t("kind." + f.kind));
    chip.append(open, el("span", "label", esc(words)),
      button("quiet tiny remove", icon("remove"), () => removeFile(id, f.name), t("remove.file")));
    row.append(chip);
  }
  return row;
}

const canCapture = () => Boolean(navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia);

function closeMenus() {
  document.querySelectorAll(".menu").forEach((m) => m.remove());
}

function attachMenu(anchor, id) {
  const open = anchor.parentElement.querySelector(".menu");
  closeMenus();
  if (open) return;
  const menu = el("div", "menu");
  menu.setAttribute("role", "menu");
  const entries = [];
  if (canCapture()) entries.push(["camera", "attach.screenshot", () => takeScreenshot(id)]);
  const touch = matchMedia("(pointer: coarse)").matches;
  entries.push(["image", touch ? "attach.photo" : "attach.image", () => pickFiles(id, "image/*")]);
  if (canCapture() && window.MediaRecorder) entries.push(["record", "attach.record", () => recordScreen(id)]);
  if ((S.round.doc.meta || {}).log) entries.push(["log", "attach.log", () => logPicker(id)]);
  entries.push(["file", "attach.file", () => pickFiles(id)]);
  for (const [ic, key, fn] of entries) {
    const item = button("menu-item", `${icon(ic)}<span>${esc(t(key))}</span>`, (e) => {
      e.stopPropagation();
      closeMenus();
      fn();
    });
    item.setAttribute("role", "menuitem");
    menu.append(item);
  }
  if (!touch) menu.append(el("div", "hint", esc(t("attach.paste.hint"))));
  anchor.parentElement.append(menu);
  menu.querySelector("button").focus();
  setTimeout(() => document.addEventListener("click", closeMenus, { once: true }));
}

function pickFiles(id, accept) {
  const input = el("input");
  input.type = "file";
  input.multiple = true;
  if (accept) input.accept = accept;
  input.onchange = () => takeFiles(id, [...input.files]);
  input.click();
}

async function takeFiles(id, files) {
  for (const f of files) {
    if (f.type.startsWith("image/") && f.type !== "image/svg+xml") await markup(id, f);
    else {
      try {
        await upload(id, "file", f, f.name);
      } catch (e) {
        toast(t("upload.failed", { e: e.message }));
      }
    }
  }
}

// -- screenshots, marked up ---------------------------------------------------------------------

async function takeScreenshot(id) {
  let stream;
  try {
    stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false, selfBrowserSurface: "exclude" });
    const video = el("video");
    video.muted = true;
    video.srcObject = stream;
    await video.play();
    await new Promise((r) => setTimeout(r, 300)); // a fresh frame
    const c = el("canvas");
    c.width = video.videoWidth;
    c.height = video.videoHeight;
    c.getContext("2d").drawImage(video, 0, 0);
    const png = await new Promise((r) => c.toBlob(r, "image/png"));
    await markup(id, png);
  } catch (e) {
    if (e.name !== "NotAllowedError") toast(t("upload.failed", { e: e.message }));
  } finally {
    if (stream) stream.getTracks().forEach((track) => track.stop());
  }
}

function markup(id, blob) {
  return new Promise(async (done) => {
    let img;
    try {
      img = await createImageBitmap(blob);
    } catch (e) {
      toast(t("upload.failed", { e: e.message }));
      return done();
    }
    const d = dialog("editor");
    d.addEventListener("close", () => done());
    const canvas = el("canvas");
    canvas.width = img.width;
    canvas.height = img.height;
    const ctx = canvas.getContext("2d");
    const shapes = [];
    const pen = Math.max(3, Math.round(Math.max(img.width, img.height) / 320));
    let tool = "arrow";
    let colour = RED;
    let drawing = null;

    const tools = el("div", "tools");
    const toolButtons = {};
    for (const name of ["arrow", "box", "blur"]) {
      toolButtons[name] = button("quiet tool", `${icon(name)}<span>${esc(t("tool." + name))}</span>`, () => {
        tool = name;
        sync();
      });
      tools.append(toolButtons[name]);
    }
    tools.append(el("span", "sep"));
    const swatches = COLOURS.map((c) => {
      const s = button("swatch", "", () => {
        colour = c;
        sync();
      }, c);
      s.style.setProperty("--swatch", c);
      tools.append(s);
      return s;
    });
    tools.append(el("span", "sep"));
    const undo = button("quiet tool", `${icon("undo")}<span>${esc(t("undo"))}</span>`, () => {
      shapes.pop();
      draw();
      sync();
    });
    tools.append(undo);

    function sync() {
      for (const [name, b] of Object.entries(toolButtons)) b.setAttribute("aria-pressed", String(tool === name));
      swatches.forEach((s, i) => s.setAttribute("aria-pressed", String(COLOURS[i] === colour)));
      undo.disabled = !shapes.length;
    }

    function rect(s) {
      return [Math.min(s.x1, s.x2), Math.min(s.y1, s.y2), Math.abs(s.x2 - s.x1), Math.abs(s.y2 - s.y1)];
    }

    function pixelate(x, y, w, h) {
      if (w < 2 || h < 2) return;
      const cell = Math.max(6, Math.round(Math.max(img.width, img.height) / 90));
      const small = el("canvas");
      small.width = Math.max(1, Math.round(w / cell));
      small.height = Math.max(1, Math.round(h / cell));
      small.getContext("2d").drawImage(img, x, y, w, h, 0, 0, small.width, small.height);
      ctx.save();
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(small, 0, 0, small.width, small.height, x, y, w, h);
      ctx.restore();
    }

    function arrow(s) {
      const a = Math.atan2(s.y2 - s.y1, s.x2 - s.x1);
      const head = pen * 4.5;
      ctx.beginPath();
      ctx.moveTo(s.x1, s.y1);
      ctx.lineTo(s.x2 - Math.cos(a) * head * 0.7, s.y2 - Math.sin(a) * head * 0.7);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(s.x2, s.y2);
      ctx.lineTo(s.x2 - head * Math.cos(a - 0.42), s.y2 - head * Math.sin(a - 0.42));
      ctx.lineTo(s.x2 - head * Math.cos(a + 0.42), s.y2 - head * Math.sin(a + 0.42));
      ctx.closePath();
      ctx.fill();
    }

    function draw() {
      ctx.drawImage(img, 0, 0);
      const all = drawing ? [...shapes, drawing] : shapes;
      for (const s of all) if (s.tool === "blur") pixelate(...rect(s));
      for (const s of all) {
        if (s.tool === "blur") continue;
        ctx.save();
        ctx.strokeStyle = ctx.fillStyle = s.colour;
        ctx.lineWidth = pen;
        ctx.lineCap = ctx.lineJoin = "round";
        ctx.shadowColor = "rgba(0,0,0,0.45)";
        ctx.shadowBlur = pen * 1.5;
        if (s.tool === "box") ctx.strokeRect(...rect(s));
        else arrow(s);
        ctx.restore();
      }
    }

    function at(e) {
      const r = canvas.getBoundingClientRect();
      return [(e.clientX - r.left) * (canvas.width / r.width), (e.clientY - r.top) * (canvas.height / r.height)];
    }

    canvas.addEventListener("pointerdown", (e) => {
      const [x, y] = at(e);
      drawing = { tool, colour, x1: x, y1: y, x2: x, y2: y };
      canvas.setPointerCapture(e.pointerId);
    });
    canvas.addEventListener("pointermove", (e) => {
      if (!drawing) return;
      [drawing.x2, drawing.y2] = at(e);
      draw();
    });
    canvas.addEventListener("pointerup", () => {
      if (drawing && Math.hypot(drawing.x2 - drawing.x1, drawing.y2 - drawing.y1) > pen * 2) shapes.push(drawing);
      drawing = null;
      draw();
      sync();
    });

    const label = el("input", "label");
    label.placeholder = t("editor.label");
    label.maxLength = 300;
    const error = el("span", "error");
    const save = button("primary", esc(t("save.attach")), () => {
      save.disabled = true;
      save.textContent = t("uploading");
      canvas.toBlob(async (png) => {
        try {
          await upload(id, "screenshot", png, "screenshot.png", label.value.trim());
          d.close();
        } catch (e) {
          error.textContent = t("upload.failed", { e: e.message });
          save.disabled = false;
          save.textContent = t("save.attach");
        }
      }, "image/png");
    });
    const head = el("header", null, `<h2>${esc(t("editor.title"))}</h2>`);
    head.append(tools);
    const stage = el("div", "stage");
    stage.append(canvas);
    const foot = el("footer");
    foot.append(label, error, button("quiet", esc(t("cancel")), () => d.close()), save);
    d.append(head, stage, foot);
    d.showModal();
    draw();
    sync();
  });
}

// -- screen recordings ------------------------------------------------------------------------------

async function recordScreen(id) {
  if (document.querySelector(".recbar")) return;
  let stream;
  try {
    stream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 30 }, audio: true, selfBrowserSurface: "exclude" });
  } catch (e) {
    if (e.name !== "NotAllowedError") toast(t("record.failed", { e: e.message }));
    return;
  }
  const type = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"].find((x) => MediaRecorder.isTypeSupported(x));
  const recorder = new MediaRecorder(stream, { mimeType: type, videoBitsPerSecond: 3_500_000 });
  const chunks = [];
  const started = Date.now();
  const bar = el("div", "recbar");
  const time = el("span", "time");
  const stop = button("primary", `${icon("stop")}<span>${esc(t("stop"))}</span>`, () => recorder.state !== "inactive" && recorder.stop());
  bar.append(el("span", "dot"), time, stop);
  document.body.append(bar);
  const tick = setInterval(() => {
    const s = Math.round((Date.now() - started) / 1000);
    time.textContent = t("recording", { t: `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}` });
    if (s >= 600 && recorder.state !== "inactive") recorder.stop(); // ten minutes at most
  }, 250);
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  recorder.onstop = async () => {
    clearInterval(tick);
    stream.getTracks().forEach((track) => track.stop());
    const blob = new Blob(chunks, { type: "video/webm" });
    time.textContent = t("uploading");
    stop.remove();
    try {
      await upload(id, "recording", blob, "recording.webm");
      bar.remove();
    } catch (e) {
      // Nothing gets lost: you can still keep it yourself.
      time.textContent = t("upload.failed", { e: e.message });
      const keep = el("a", "button", esc(t("record.save")));
      keep.href = URL.createObjectURL(blob);
      keep.download = "recording.webm";
      bar.append(keep, button("quiet tiny", icon("remove"), () => bar.remove(), t("close")));
    }
  };
  stream.getVideoTracks()[0].addEventListener("ended", () => recorder.state !== "inactive" && recorder.stop());
  recorder.start(1000);
}

// -- picking lines: from a log the checklist names, or from a Run's output ------------------------

async function logPicker(id) {
  try {
    const { logs } = await api(`/api/log?round=${encodeURIComponent(S.current)}`);
    linePicker(id, logs);
  } catch (e) {
    toast(t("viewer.failed", { e: e.message }));
  }
}

function linePicker(id, sources) {
  const d = dialog("picker");
  let current = 0;
  let anchor = null;
  const picked = new Set();
  const head = el("header", null, `<h2>${esc(t("log.title"))}</h2>`);
  head.append(button("quiet close", icon("remove"), () => d.close(), t("close")));
  const tabs = el("div", "tabs");
  const box = el("div", "lines pick");
  const attachButton = button("primary", "", attachLines);
  const foot = el("footer");
  foot.append(el("span", "hint", esc(t("log.pick"))), button("quiet", esc(t("cancel")), () => d.close()), attachButton);

  function show() {
    const src = sources[current];
    tabs.replaceChildren(...(sources.length > 1 ? sources.map((s, i) => {
      const b = button(i === current ? "tab on" : "tab", esc(s.name), () => {
        current = i;
        picked.clear();
        anchor = null;
        show();
      });
      return b;
    }) : []));
    box.replaceChildren();
    if (src.error) box.append(el("div", "note", esc(src.error)));
    else if (!src.lines.length) box.append(el("div", "note", esc(t("log.empty"))));
    src.lines.forEach((s, i) => {
      const row = el("div", "line");
      row.dataset.n = i + 1;
      row.textContent = s || " ";
      row.onclick = (e) => {
        if (e.shiftKey && anchor !== null) {
          const [a, b] = [Math.min(anchor, i), Math.max(anchor, i)];
          for (let k = a; k <= b; k++) picked.add(k);
        } else if (picked.has(i)) picked.delete(i);
        else picked.add(i);
        anchor = i;
        mark();
      };
      box.append(row);
    });
    mark();
    box.scrollTop = box.scrollHeight;
  }

  function mark() {
    [...box.querySelectorAll(".line")].forEach((row, i) => row.classList.toggle("on", picked.has(i)));
    attachButton.textContent = t("log.attach", { n: picked.size });
    attachButton.disabled = picked.size === 0;
  }

  async function attachLines() {
    const src = sources[current];
    const lines = [...picked].sort((a, b) => a - b).map((i) => src.lines[i]);
    const label = t("log.label", { n: lines.length, s: src.name });
    const blob = new Blob([`# ${src.name}\n${lines.join("\n")}\n`], { type: "text/plain" });
    attachButton.disabled = true;
    try {
      await upload(id, "log", blob, `${src.name.split("/").pop() || "log"}.txt`, label);
      d.close();
    } catch (e) {
      toast(t("upload.failed", { e: e.message }));
      attachButton.disabled = false;
    }
  }

  d.append(head, tabs, box, foot);
  d.showModal();
  show();
}

// -- Run: a checklist's command, run here, its output live -------------------------------------

async function loadRuns() {
  S.runs = new Map();
  try {
    const { runs } = await api(`/api/runs?round=${encodeURIComponent(S.current)}`);
    for (const r of runs) S.runs.set(r.code, r);
  } catch {}
}

async function startRun(code) {
  try {
    const { run } = await api("/api/run", { round: S.current, code });
    onRun({ ...run, lines: [] });
  } catch (e) {
    toast(t("run.failed", { e: e.message }));
  }
}

async function stopRun(code) {
  const run = S.runs.get(code);
  if (run) await api("/api/run/stop", { id: run.id }).catch((e) => toast(e.message));
}

function onRun(event) {
  if (event.round !== S.current) return;
  let run = S.runs.get(event.code);
  if (!run || run.id !== event.id) {
    run = { id: event.id, code: event.code, status: "running", exit: null, lines: [], started: event.started };
    S.runs.set(event.code, run);
    drawRun(event.code);
  }
  if (event.lines && event.lines.length) {
    run.lines.push(...event.lines);
    if (run.lines.length > 5000) run.lines.splice(0, run.lines.length - 5000);
  }
  if (event.status) run.status = event.status;
  if ("exit" in event) run.exit = event.exit;
  drawRun(event.code, event.lines);
}

function runStatus(run) {
  if (run.status === "running") return t("running");
  if (run.status === "stopped") return t("run.stopped");
  return t("run.done", { c: run.exit });
}

/** A Run's panel under its code block: drawn fresh, or with `fresh` lines added. */
function drawRun(code, fresh) {
  const block = document.querySelector(`.code[data-code="${CSS.escape(code)}"]`);
  const run = S.runs.get(code);
  if (!block || !run) return;
  let panel = block.querySelector(".run-out");
  if (!panel || !fresh) {
    panel?.remove();
    panel = el("div", "run-out");
    panel.append(el("div", "run-bar"), el("div", "out"));
    block.append(panel);
    fresh = run.lines;
    panel.querySelector(".out").replaceChildren();
  }
  const out = panel.querySelector(".out");
  const atEnd = out.scrollHeight - out.scrollTop - out.clientHeight < 30;
  if (fresh && fresh.length) {
    const frag = document.createDocumentFragment();
    for (const line of fresh) frag.append(el("div", null, esc(line) || " "));
    out.append(frag);
    while (out.childElementCount > 5000) out.firstElementChild.remove();
  }
  if (atEnd) out.scrollTop = out.scrollHeight;
  const bar = panel.querySelector(".run-bar");
  bar.className = `run-bar ${run.status}${run.status === "done" && run.exit !== 0 ? " failed" : ""}`;
  bar.replaceChildren(el("span", "state", esc(runStatus(run))));
  const holder = block.closest("[data-id]");
  if (run.status === "running") bar.append(button("quiet tiny", `${icon("stop")}<span>${esc(t("stop"))}</span>`, () => stopRun(code)));
  if (run.lines.length) {
    bar.append(button("quiet tiny", `${icon("log")}<span>${esc(t("run.attach"))}</span>`, () =>
      linePicker(holder ? holder.dataset.id : "overall", [{ name: t("run.label", { c: code }), lines: [...run.lines] }])));
  }
  bar.append(button("quiet tiny", `${icon("remove")}<span>${esc(t("run.hide"))}</span>`, () => panel.remove()));
  const runButton = block.querySelector(".tools .run");
  if (runButton) runButton.querySelector("span").textContent = run.status === "running" ? t("running") : t("run.again");
}

function runButton(b) {
  return button("quiet tiny run", `${icon("play")}<span>${esc(t("run"))}</span>`, () => startRun(b.id));
}

// -- the phone ----------------------------------------------------------------------------------

async function openPhone() {
  document.querySelector("dialog.phone")?.close();
  const d = dialog("phone");
  const head = el("header", null, `<h2>${esc(t("phone.title"))}</h2>`);
  head.append(button("quiet close", icon("remove"), () => d.close(), t("close")));
  const body = el("div", "phone-body");
  d.append(head, body);
  d.showModal();
  await drawPhone(body);
}

async function refreshPhone() {
  const body = document.querySelector("dialog.phone[open] .phone-body");
  if (body) await drawPhone(body);
}

async function drawPhone(body, status) {
  try {
    status = status || (await api("/api/phone"));
  } catch (e) {
    body.replaceChildren(el("p", "error", esc(t("phone.failed", { e: e.message }))));
    return;
  }
  const toggle = async (on) => {
    try {
      await drawPhone(body, await api("/api/phone", { on }));
    } catch (e) {
      toast(t("phone.failed", { e: e.message }));
    }
  };
  body.replaceChildren();
  if (!status.on) {
    body.append(el("p", null, esc(t("phone.about"))), el("p", "dim", esc(t("phone.safe"))));
    const on = button("primary", `${icon("phone")}<span>${esc(t("phone.on"))}</span>`, () => {
      on.disabled = true;
      on.querySelector("span").textContent = t("phone.opening");
      toggle(true);
    });
    body.append(on);
    return;
  }
  const code = el("div", "qr", status.qr);
  const link = el("div", "link mono");
  link.textContent = status.url;
  body.append(el("p", null, esc(t("phone.scan"))), code, link, el("p", "dim", esc(t("phone.until", { t: status.until }))));
  const fw = status.firewall || {};
  if (fw.checked && !fw.open) {
    const warn = el("div", "warn", `<p>${esc(t("phone.firewall"))}</p>`);
    const cmd = el("pre", "mono");
    cmd.textContent = fw.fix;
    warn.append(cmd);
    body.append(warn);
  }
  body.append(button("", esc(t("phone.off")), () => toggle(false)));
}

// -- once, at the start ---------------------------------------------------------------------------

function initExtras() {
  const main = document.querySelector("main");
  main.addEventListener("click", (e) => {
    const path = e.target.closest(".path[data-path]");
    if (path) return openPath(path.dataset.path);
    const pic = e.target.closest("img.pic");
    if (pic) return lightbox(pic.src, false);
    const commit = e.target.closest(".commit-link");
    if (commit) return openCommit(commit.dataset.ref);
  });
  // Paste a picture while working on an item: it opens in the editor for that item.
  document.addEventListener("paste", (e) => {
    const files = [...((e.clipboardData && e.clipboardData.files) || [])].filter((f) => f.type.startsWith("image/"));
    if (!files.length || !S.round || document.querySelector("dialog[open]")) return;
    const holder = (document.activeElement && document.activeElement.closest && document.activeElement.closest("[data-id]"))
      || document.querySelector(".item.here");
    if (!holder) return;
    e.preventDefault();
    markup(holder.dataset.id, files[0]);
  });
  // Drop files on an item to attach them there.
  let over = null;
  main.addEventListener("dragover", (e) => {
    const holder = e.target.closest("[data-id]");
    if (!holder || !e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    if (over !== holder) {
      over?.classList.remove("dropping");
      over = holder;
      holder.classList.add("dropping");
    }
  });
  main.addEventListener("dragleave", (e) => {
    if (over && !over.contains(e.relatedTarget)) {
      over.classList.remove("dropping");
      over = null;
    }
  });
  main.addEventListener("drop", (e) => {
    const holder = e.target.closest("[data-id]");
    over?.classList.remove("dropping");
    over = null;
    if (!holder || !e.dataTransfer.files.length) return;
    e.preventDefault();
    takeFiles(holder.dataset.id, [...e.dataTransfer.files]);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeMenus();
  });
}
