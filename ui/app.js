/* Talks to Python by polling, which behaves the same on every pywebview
   version and keeps all UI work on the UI thread. */

const $ = (id) => document.getElementById(id);
const body = document.body;

const STATES = {
  offline:     ["Offline",     "Click the core to start listening.", "Activate"],
  calibrating: ["Calibrating", "Tuning the mic to your room. Stay quiet a moment.", "Wait"],
  listening:   ["Listening",   'Say "Hey Jarvis" and then a command.', "Online"],
  waiting:     ["Listening",   "Go ahead.", "Online"],
  thinking:    ["Thinking",    "Working out what to do.", "Busy"],
  executing:   ["Executing",   "Running the task.", "Busy"],
  speaking:    ["Speaking",    "Press Escape to cut me off.", "Online"],
};

let busySince = null;
let pendingAsk = null;
let rows = 0;

/* bezel ticks, drawn once; every fifth runs longer, as on a real dial */
(function ticks() {
  const g = $("ticks");
  for (let i = 0; i < 60; i++) {
    const a = (i / 60) * Math.PI * 2 - Math.PI / 2;
    const long = i % 5 === 0;
    const r1 = long ? 99 : 103;
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", 110 + Math.cos(a) * r1);
    line.setAttribute("y1", 110 + Math.sin(a) * r1);
    line.setAttribute("x2", 110 + Math.cos(a) * 107);
    line.setAttribute("y2", 110 + Math.sin(a) * 107);
    line.setAttribute("opacity", long ? "1" : "0.4");
    g.appendChild(line);
  }
})();

/* ------------------------------------------------------------- clock */

setInterval(() => {
  const d = new Date();
  $("clock").textContent = d.toLocaleTimeString("en-GB", { hour12: false });
  $("date").textContent = d.toLocaleDateString("en-GB",
    { weekday: "short", day: "2-digit", month: "short" });
}, 500);

/* ------------------------------------------------------------- state */

function setState(name) {
  const [word, hint, core] = STATES[name] || STATES.offline;
  if (body.dataset.state === name) return;
  body.dataset.state = name;
  $("stateWord").textContent = word;
  $("hint").textContent = hint;
  $("coreLabel").textContent = core;
  $("topState").textContent = word.toUpperCase();
  busySince = (name === "thinking" || name === "executing") ? Date.now() : null;
  if (!busySince) $("elapsed").textContent = "";
}

/* the only figure on screen that isn't read from the machine is this one,
   and it is a real measurement too: how long the current task has run */
setInterval(() => {
  if (!busySince) return;
  $("elapsed").textContent = ((Date.now() - busySince) / 1000).toFixed(1) + "s";
}, 100);

/* ------------------------------------------------------------- feed */

function addRow(kind, who, message) {
  const feed = $("feed");
  const row = document.createElement("div");
  row.className = "row " + kind;
  row.innerHTML = '<span class="t"></span><span class="w"></span><span class="m"></span>';
  row.children[0].textContent = new Date().toLocaleTimeString("en-GB", { hour12: false });
  row.children[1].textContent = who;
  row.children[2].textContent = message;

  const stuck = feed.scrollTop + feed.clientHeight >= feed.scrollHeight - 30;
  feed.appendChild(row);
  if (stuck) feed.scrollTop = feed.scrollHeight;
  while (feed.children.length > 400) feed.firstChild.remove();
  $("feedCount").textContent = ++rows;
}

function logLine(text) {
  if (text.startsWith("You: ")) return addRow("you", "you", text.slice(5));
  if (text.startsWith("JARVIS: ")) return addRow("jarvis", "jarvis", text.slice(8));
  if (text.startsWith("   > ")) return addRow("tool", "·", text.slice(5));
  const warn = /GEMINI_API_KEY|^I couldn't|isn't signed in|rate limit|no linked/i.test(text);
  addRow(warn ? "warn" : "note", "", text);
}

/* ------------------------------------------------------------- panels */

function gauge(name, percent, label) {
  return `<div class="gauge"><span class="g-name">${name}</span>` +
         `<span class="bar"><i style="width:${Math.min(100, percent)}%"></i></span>` +
         `<span class="g-val">${label}</span></div>`;
}

function kv(pairs) {
  return pairs.map(([k, v, cls]) =>
    `<dt>${k}</dt><dd class="${cls || ""}">${v}</dd>`).join("");
}

function paintStats(s) {
  const sys = s.system || {};
  if (sys.available) {
    $("gauges").innerHTML =
      gauge("CPU", sys.cpu, sys.cpu + "%") +
      gauge("RAM", sys.ram, sys.ram + "%") +
      gauge("DSK", sys.disk, sys.disk + "%");
    $("sysKv").innerHTML = kv([
      ["memory", `${sys.ram_used} / ${sys.ram_total} GB`],
      ["free disk", sys.disk_free + " GB"],
      ["os", s.session.os],
    ]);
  } else {
    $("gauges").innerHTML = '<p class="muted">install psutil for live readings</p>';
    $("sysKv").innerHTML = kv([["os", s.session.os]]);
  }

  const v = s.voice;
  $("voiceKv").innerHTML = kv([
    ["mic", v.mic, v.mic === "on" ? "on" : "off"],
    ["speech", v.speech, v.speech === "on" ? "on" : "off"],
    ["language", v.lang],
    ["model", v.model],
  ]);

  $("sessionKv").innerHTML = kv([
    ["uptime", s.session.uptime],
    ["commands", s.session.commands],
    ["tool calls", s.session.tools],
    ["workspace", s.workspace.split(/[\\/]/).pop() || s.workspace],
  ]);

  $("toolList").innerHTML = s.tools.length
    ? s.tools.map((t) => `<li><span>${t.name}</span><span>${t.ms} ms</span></li>`).join("")
    : '<li class="muted">nothing yet</li>';

  $("remList").innerHTML = s.reminders.length
    ? s.reminders.map((r) => `<li><span>${r.text}</span><span>${r.at}</span></li>`).join("")
    : '<li class="muted">none set</li>';

  const plan = s.plan;
  if (plan) {
    $("planCount").textContent = `${plan.at}/${plan.steps.length}`;
    $("planSteps").innerHTML = plan.steps.map((step, i) => {
      const record = plan.done[i];
      let cls = "";
      if (record) cls = record.ok ? "done" : "bad";
      else if (i + 1 === plan.at) cls = "now";
      return `<li class="${cls}"><span></span></li>`;
    }).join("");
    // set the text separately so a step's wording can never become markup
    $("planSteps").querySelectorAll("li span").forEach((el, i) => {
      el.textContent = plan.steps[i];
    });
  } else {
    $("planCount").textContent = "";
    $("planSteps").innerHTML = '<li class="muted">no plan running</li>';
  }

  $("resKv").innerHTML = kv([
    ["browser", s.browser, s.browser === "open" ? "on" : "off"],
    ["contacts", s.contacts],
  ]);
}

/* ------------------------------------------------------------- confirm */

function showAsk(ask) {
  pendingAsk = ask.id;
  $("askText").textContent = ask.message;
  $("veil").hidden = false;
  $("askYes").focus();
}

function answerAsk(ok) {
  if (pendingAsk === null) return;
  window.pywebview.api.confirm_reply(pendingAsk, ok);
  pendingAsk = null;
  $("veil").hidden = true;
}

/* ------------------------------------------------------------- loop */

async function poll() {
  try {
    const data = await window.pywebview.api.poll();
    if (data.status) setState(data.status);
    (data.lines || []).forEach(logLine);
    if (data.stats) paintStats(data.stats);
    if (data.ask && pendingAsk === null) showAsk(data.ask);
  } catch (e) { /* window closing, or Python not up yet */ }
}

function send() {
  const input = $("input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  window.pywebview.api.send(text);
}

$("power").onclick = () => window.pywebview.api.toggle();
$("send").onclick = send;
$("input").addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
$("askYes").onclick = () => answerAsk(true);
$("askNo").onclick = () => answerAsk(false);

document.querySelectorAll(".acts button").forEach((b) => {
  b.onclick = () => {
    if (b.dataset.act === "clear") {
      $("feed").innerHTML = ""; rows = 0; $("feedCount").textContent = "";
      return;
    }
    window.pywebview.api.control(b.dataset.act).then((label) => {
      if (b.dataset.act === "mute" && label) b.textContent = label;
    });
  };
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (pendingAsk !== null) return answerAsk(false);
    window.pywebview.api.control("stop");
  }
  if (e.ctrlKey && e.code === "Space") window.pywebview.api.toggle();
});

window.addEventListener("pywebviewready", () => {
  addRow("note", "", "Ready. Type a command, or click the core to use your voice.");
  $("input").focus();
  setInterval(poll, 200);
  poll();
});
