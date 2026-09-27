/* Reads /api/state and draws. Every number shown comes from the database;
   nothing is computed hopefully or filled in for effect. */

const $ = (id) => document.getElementById(id);
let data = null;

const fmtTime = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? String(iso).slice(0, 16).replace("T", " ")
                  : d.toLocaleString("en-GB", { day: "2-digit", month: "short",
                                                hour: "2-digit", minute: "2-digit" });
};

const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
};

const statusWord = (s) => (s || "").replace(/_/g, " ").toLowerCase();

/* ------------------------------------------------------------- tiles */

function tile(value, label, tone) {
  const node = el("div", "tile" + (tone ? " " + tone : ""));
  node.append(el("b", null, String(value)), el("span", null, label));
  return node;
}

function drawTiles() {
  const c = data.counts;
  const box = $("tiles");
  box.replaceChildren(
    tile(c.jobs_today, "found today"),
    tile(c.jobs_total, "jobs stored"),
    tile((data.jobs.filter((j) => j.match_score >= 70)).length, "match 70+"),
    tile(c.applied, "submitted", c.applied ? "good" : null),
    tile(c.needs_action, "need you", c.needs_action ? "warning" : null),
    tile(c.failed, "failed", c.failed ? "serious" : null),
  );
}

/* ------------------------------------------------------------- job card */

function jobCard(job) {
  const card = el("article", "card");

  const head = el("header");
  const left = el("div");
  left.append(el("h3", null, job.title), el("div", "company", job.company));
  const score = el("div", "score");
  score.append(el("b", null, job.match_score), el("span", null, "MATCH"));
  head.append(left, score);

  const meta = el("div", "meta");
  [job.location || "location not stated", job.work_mode, job.platform,
   job.salary || "salary not stated"].filter(Boolean)
    .forEach((m) => meta.append(el("span", null, m)));

  const chips = el("div", "chips");
  (job.skills_matched || []).slice(0, 7)
    .forEach((s) => chips.append(el("span", "chip have", s)));
  (job.skills_missing || []).slice(0, 5)
    .forEach((s) => chips.append(el("span", "chip gap", s)));

  const foot = el("footer");
  foot.append(el("span", "status " + (job.status || "").toLowerCase(), statusWord(job.status)));
  if (job.url) {
    const link = el("a", null, "Open posting");
    link.href = job.url;
    link.target = "_blank";
    link.rel = "noopener";
    foot.append(link);
  }

  card.append(head, meta);
  if (chips.children.length) card.append(chips);
  if (job.why) card.append(el("p", "why", job.why));
  card.append(foot);
  return card;
}

function drawJobs() {
  const needle = $("search").value.trim().toLowerCase();
  const min = Number($("minScore").value);
  const status = $("statusFilter").value;

  const shown = data.jobs.filter((job) => {
    if (job.match_score < min) return false;
    if (status && job.status !== status) return false;
    if (!needle) return true;
    const hay = [job.company, job.title, job.location,
                 ...(job.skills_required || [])].join(" ").toLowerCase();
    return hay.includes(needle);
  });

  $("jobsCount").textContent = `${shown.length} of ${data.jobs.length}`;
  const box = $("jobCards");
  box.replaceChildren();
  if (!shown.length) {
    box.append(el("p", "empty", data.jobs.length
      ? "Nothing matches those filters."
      : 'No jobs stored yet. Tell JARVIS: find jobs for me'));
    return;
  }
  shown.forEach((job) => box.append(jobCard(job)));
}

/* ------------------------------------------------------------- applications */

function drawApplications() {
  const box = $("appFeed");
  box.replaceChildren();
  if (!data.applications.length) {
    box.append(el("p", "empty", "Nothing recorded yet."));
    return;
  }
  data.applications.forEach((app) => {
    const row = el("div", "event");
    row.append(el("time", null, fmtTime(app.applied_at) || "not submitted"));

    const body = el("div", "body");
    body.append(el("h3", null, `${app.title} — ${app.company}`));
    const line = el("div", "row");
    line.append(el("span", "status " + (app.status || "").toLowerCase(), statusWord(app.status)));
    line.append(el("span", "meta", `${app.platform || "unknown board"} · match ${app.match_score}`));
    if (app.url) {
      const link = el("a", null, "Open posting");
      link.href = app.url; link.target = "_blank"; link.rel = "noopener";
      line.append(link);
    }
    body.append(line);
    if (app.notes) body.append(el("p", null, app.notes));
    row.append(body);
    box.append(row);
  });
}

/* ------------------------------------------------------------- charts */

/* One series per chart, so magnitude is the only thing colour encodes and
   a categorical palette never comes into it. Values are labelled, so the
   bar length is a convenience rather than the only way to read it. */
function drawBars(target, pairs, emptyText) {
  const box = $(target);
  box.replaceChildren();
  if (!pairs.length) {
    box.append(el("p", "empty", emptyText));
    return;
  }
  const max = Math.max(...pairs.map(([, n]) => n)) || 1;
  pairs.forEach(([name, n]) => {
    const row = el("div", "bar");
    row.append(el("span", "name", name));
    const track = el("span", "track");
    const fill = el("span", "fill");
    fill.style.width = Math.max(2, (n / max) * 100) + "%";
    track.append(fill);
    row.append(track, el("span", "value", n));
    box.append(row);
  });
}

function drawAnalytics() {
  const c = data.counts;
  $("rates").replaceChildren(
    tile(c.attempts, "attempts"),
    tile(c.applied, "submitted", c.applied ? "good" : null),
    tile(c.success_rate + "%", "success rate"),
    tile(c.avg_score, "avg match"),
    tile(c.interviews, "interviews"),
    tile(c.offers, "offers"),
  );

  drawBars("missingChart", data.missing_skills,
           "No jobs scored yet, so there is nothing to compare against.");
  drawBars("platformChart", Object.entries(c.by_platform || {}), "No jobs stored yet.");
  drawBars("locationChart", Object.entries(c.by_location || {}), "No jobs stored yet.");
}

/* ------------------------------------------------------------- resume + log */

function drawResume() {
  const r = data.resume;
  const box = $("resumePanel");
  box.replaceChildren();

  if (!r.name && !r.skills.length) {
    box.append(el("p", "empty", 'No resume scanned. Tell JARVIS: scan my resume resume.pdf'));
    return;
  }

  const dl = el("dl", "kv");
  const rows = [
    ["Name", r.name || "not stated"],
    ["Degree", [r.degree, r.graduation_year].filter(Boolean).join(", ") || "not stated"],
    ["Location", r.location || "not stated"],
    ["Target roles", r.roles.join(", ") || "not set — tell JARVIS: set roles to ..."],
    ["Skills", r.skills.join(", ") || "none found"],
    ["Projects", r.projects.join(" · ") || "none found"],
    ["Source file", r.file || "unknown"],
  ];
  rows.forEach(([k, v]) => { dl.append(el("dt", null, k), el("dd", null, v)); });
  box.append(dl);
}

function drawLog() {
  const body = $("logRows");
  body.replaceChildren();
  if (!data.audit.length) {
    const row = el("tr");
    const cell = el("td", "empty", "Nothing logged yet.");
    cell.colSpan = 5;
    row.append(cell);
    body.append(row);
    return;
  }
  data.audit.forEach((entry) => {
    const row = el("tr");
    [fmtTime(entry.timestamp), entry.action, entry.platform || "",
     entry.company || entry.job || "", entry.error || entry.result || ""]
      .forEach((v) => row.append(el("td", null, v)));
    body.append(row);
  });
}

/* ------------------------------------------------------------- shell */

function drawAll() {
  drawTiles();
  const box = $("dashCards");
  box.replaceChildren();
  const strong = data.jobs.slice(0, 6);
  if (!strong.length) {
    box.append(el("p", "empty", 'No jobs yet. Tell JARVIS: find jobs for me'));
  } else {
    strong.forEach((job) => box.append(jobCard(job)));
  }

  const statuses = [...new Set(data.jobs.map((j) => j.status))].sort();
  const select = $("statusFilter");
  const keep = select.value;
  select.replaceChildren(el("option", null, "Any status"));
  select.firstChild.value = "";
  statuses.forEach((s) => {
    const option = el("option", null, statusWord(s));
    option.value = s;
    select.append(option);
  });
  select.value = keep;

  drawJobs();
  drawApplications();
  drawAnalytics();
  drawResume();
  drawLog();
}

async function refresh() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    data = await response.json();
    drawAll();
    $("updated").textContent = "updated " + new Date().toLocaleTimeString("en-GB");
  } catch (e) {
    $("updated").textContent = "JARVIS not reachable";
  }
}

$("tabs").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b === button));
  document.querySelectorAll(".view").forEach((v) =>
    v.classList.toggle("on", v.dataset.view === button.dataset.view));
});

["search", "statusFilter"].forEach((id) => $(id).addEventListener("input", () => data && drawJobs()));
$("minScore").addEventListener("input", (e) => {
  $("minScoreOut").textContent = e.target.value;
  if (data) drawJobs();
});

setInterval(() => {
  $("clock").textContent = new Date().toLocaleTimeString("en-GB", { hour12: false });
}, 500);

refresh();
setInterval(refresh, 4000);
