// charts.js -- rendering layer for the case study page.
// Consumes window.APPS_DATA and window.ANALYSIS_DATA, produced by
// agents/report.py from the verified dataset. No numbers are hand-typed here.

(function () {
  "use strict";

  const DATA = window.APPS_DATA || [];
  const ANALYSIS = window.ANALYSIS_DATA || {};

  const COLORS = {
    accent: "#2DD4A8", amber: "#F2A623", coral: "#E8593C",
    blue: "#4C8DD9", purple: "#9B8CF2", muted: "#676E7C",
  };
  const PALETTE = [COLORS.accent, COLORS.blue, COLORS.amber, COLORS.purple, COLORS.coral, "#5FB3B3", "#C97BD1", "#7C9EF2", "#E0A458", "#6BC6A0"];

  /* ---------------- Theme toggle ---------------- */
  const root = document.documentElement;
  const themeToggle = document.getElementById("theme-toggle");
  function applyTheme(mode) {
    root.classList.toggle("light", mode === "light");
    if (themeToggle) themeToggle.innerHTML = mode === "light" ? '<i class="ti ti-moon"></i>' : '<i class="ti ti-sun"></i>';
    localStorage.setItem("theme", mode);
  }
  const saved = localStorage.getItem("theme") || (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  applyTheme(saved);
  if (themeToggle) {
    themeToggle.addEventListener("click", () => applyTheme(root.classList.contains("light") ? "dark" : "light"));
  }

  /* ---------------- Hero terminal animation ---------------- */
  const termBody = document.getElementById("terminal-body");
  if (termBody) {
    const buildableToday = (ANALYSIS.buildability_distribution || {}).buildable_today || 0;
    const total = ANALYSIS.total_apps || 100;
    const lines = [
      { html: `<span class="t-dim">$</span> python run_pipeline.py`, cls: "" },
      { html: `<span class="t-ok">[discover]</span> resolving developer docs for ${total} apps...`, cls: "" },
      { html: `<span class="t-ok">[crawler]</span> fetching auth / API reference pages (Firecrawl)`, cls: "" },
      { html: `<span class="t-ok">[extractor]</span> Claude extracting structured fields, grounded in docs`, cls: "" },
      { html: `<span class="t-warn">[verifier]</span> re-deriving claims independently, diffing against pass 1`, cls: "" },
      { html: `<span class="t-warn">[verifier]</span> ${(window.VERIFICATION_SUMMARY||{}).sample_size||20}-app hand-verified sample &rarr; confidence ${(window.VERIFICATION_SUMMARY||{}).avg_confidence_before||"--"} &rarr; ${(window.VERIFICATION_SUMMARY||{}).avg_confidence_after||"--"} avg`, cls: "" },
      { html: `<span class="t-ok">[classifier]</span> buildable_today=${buildableToday} buildable_gated=${(ANALYSIS.buildability_distribution||{}).buildable_gated||0} not_verifiable=${(ANALYSIS.buildability_distribution||{}).not_verifiable||0}`, cls: "" },
      { html: `<span class="t-ok">[report]</span> dataset.json, dataset.csv, dataset.db, analysis.json written`, cls: "" },
      { html: `<span class="t-dim">Pipeline complete.</span> ${total}/${total} apps researched &middot; avg confidence ${ANALYSIS.avg_confidence || "--"}<span class="cursor"></span>`, cls: "" },
    ];
    let i = 0;
    function typeNext() {
      if (i >= lines.length) return;
      const el = document.createElement("div");
      el.className = "terminal-line";
      el.innerHTML = lines[i].html;
      el.style.animationDelay = "0s";
      termBody.appendChild(el);
      i++;
      setTimeout(typeNext, i === 1 ? 260 : 340);
    }
    typeNext();
  }

  /* ---------------- Chart helpers ---------------- */
  function baseOptions(extra) {
    const isLight = document.documentElement.classList.contains("light");
    const gridColor = isLight ? "#E3E2DC" : "#262B35";
    const textColor = isLight ? "#52565F" : "#9BA1AE";
    return Object.assign({
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: textColor, font: { family: "Inter", size: 11.5 }, boxWidth: 12, padding: 12 } },
        tooltip: { titleFont: { family: "Inter" }, bodyFont: { family: "Inter" } },
      },
      scales: {
        x: { ticks: { color: textColor, font: { family: "Inter", size: 11 } }, grid: { color: gridColor, display: false } },
        y: { ticks: { color: textColor, font: { family: "Inter", size: 11 } }, grid: { color: gridColor } },
      },
    }, extra || {});
  }

  function makeChart(id, config) {
    const el = document.getElementById(id);
    if (!el) return null;
    if (typeof Chart === "undefined") {
      // Chart.js failed to load (offline / CDN blocked) -- degrade gracefully
      // instead of throwing and taking the rest of this script (including the
      // registry table below) down with it.
      const wrap = el.closest(".chart-card");
      if (wrap) wrap.innerHTML = '<p class="text-[12px] text-[var(--text-muted)]">Chart unavailable (chart.js did not load).</p>';
      return null;
    }
    try {
      return new Chart(el.getContext("2d"), config);
    } catch (err) {
      console.warn("Chart render failed for", id, err);
      return null;
    }
  }

  function sortEntries(obj, limit) {
    let entries = Object.entries(obj || {}).sort((a, b) => b[1] - a[1]);
    if (limit) entries = entries.slice(0, limit);
    return entries;
  }

  /* 1. Category distribution (bar) */
  const catEntries = sortEntries(ANALYSIS.category_distribution);
  makeChart("chart-category", {
    type: "bar",
    data: { labels: catEntries.map(e => e[0]), datasets: [{ data: catEntries.map(e => e[1]), backgroundColor: COLORS.blue, borderRadius: 4, maxBarThickness: 22 }] },
    options: baseOptions({ indexAxis: "y", plugins: { legend: { display: false } } }),
  });

  /* 2. Auth distribution (pie) */
  const authEntries = sortEntries(ANALYSIS.auth_distribution);
  makeChart("chart-auth", {
    type: "doughnut",
    data: { labels: authEntries.map(e => e[0]), datasets: [{ data: authEntries.map(e => e[1]), backgroundColor: PALETTE, borderColor: "transparent" }] },
    options: baseOptions({ cutout: "62%", scales: {} }),
  });

  /* 3. API type distribution */
  const apiEntries = sortEntries(ANALYSIS.api_type_distribution);
  makeChart("chart-api", {
    type: "bar",
    data: { labels: apiEntries.map(e => e[0]), datasets: [{ data: apiEntries.map(e => e[1]), backgroundColor: COLORS.accent, borderRadius: 4, maxBarThickness: 30 }] },
    options: baseOptions({ plugins: { legend: { display: false } } }),
  });

  /* 4. Confidence histogram */
  const confOrder = ["90-100 (verified this session)", "75-89 (high-confidence knowledge)", "60-74 (medium, flagged for re-check)", "<60 (manual review queue)"];
  const confDist = ANALYSIS.confidence_distribution || {};
  makeChart("chart-confidence", {
    type: "bar",
    data: {
      labels: confOrder.map(l => l.split(" (")[0]),
      datasets: [{ data: confOrder.map(l => confDist[l] || 0), backgroundColor: [COLORS.accent, "#5FB3B3", COLORS.amber, COLORS.coral], borderRadius: 4, maxBarThickness: 46 }],
    },
    options: baseOptions({ plugins: { legend: { display: false } } }),
  });

  /* 5. Self-serve vs gated */
  const ssg = ANALYSIS.self_serve_vs_gated || {};
  makeChart("chart-selfserve", {
    type: "doughnut",
    data: { labels: ["Self-serve", "Gated", "Unclear / not verifiable"], datasets: [{ data: [ssg.self_serve || 0, ssg.gated || 0, ssg.unclear || 0], backgroundColor: [COLORS.accent, COLORS.amber, COLORS.coral], borderColor: "transparent" }] },
    options: baseOptions({ cutout: "62%", scales: {} }),
  });

  /* 6. Buildability tiers */
  const bd = ANALYSIS.buildability_distribution || {};
  const buildLabels = { buildable_today: "Buildable today", buildable_gated: "Buildable, gated", not_buildable: "Not buildable (no API)", not_verifiable: "Not verifiable" };
  const buildKeys = Object.keys(bd);
  makeChart("chart-buildability", {
    type: "bar",
    data: { labels: buildKeys.map(k => buildLabels[k] || k), datasets: [{ data: buildKeys.map(k => bd[k]), backgroundColor: [COLORS.accent, COLORS.amber, COLORS.coral, COLORS.muted], borderRadius: 4, maxBarThickness: 46 }] },
    options: baseOptions({ plugins: { legend: { display: false } } }),
  });

  /* 7. MCP availability */
  makeChart("chart-mcp", {
    type: "doughnut",
    data: { labels: ["Official MCP server", "Third-party MCP only", "No MCP found"], datasets: [{ data: [ANALYSIS.mcp_official, ANALYSIS.mcp_third_party, ANALYSIS.mcp_none], backgroundColor: [COLORS.accent, COLORS.blue, COLORS.muted], borderColor: "transparent" }] },
    options: baseOptions({ cutout: "62%", scales: {} }),
  });

  /* 8. Verification improvement (per-app, from the 20-app sample) */
  const vLog = window.VERIFICATION_LOG || [];
  if (vLog.length) {
    makeChart("chart-verification", {
      type: "bar",
      data: {
        labels: vLog.map(v => v.app),
        datasets: [
          { label: "Confidence before", data: vLog.map(v => v.confidence_before), backgroundColor: COLORS.muted, borderRadius: 3, maxBarThickness: 14 },
          { label: "Confidence after", data: vLog.map(v => v.confidence_after), backgroundColor: COLORS.accent, borderRadius: 3, maxBarThickness: 14 },
        ],
      },
      options: baseOptions({ indexAxis: "y", scales: { x: { min: 0, max: 100, ticks: { color: "#9BA1AE" }, grid: { color: "#262B35" } }, y: { ticks: { color: "#9BA1AE", font: { size: 10.5 } }, grid: { display: false } } } }),
    });
  }

  /* 9. Category ease ranking */
  const ease = ANALYSIS.category_ease_ranking || [];
  makeChart("chart-ease", {
    type: "bar",
    data: { labels: ease.map(e => e.category), datasets: [{ data: ease.map(e => e.pct_easy), backgroundColor: COLORS.purple, borderRadius: 4, maxBarThickness: 22 }] },
    options: baseOptions({ indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { max: 100, ticks: { color: "#9BA1AE", callback: v => v + "%" }, grid: { color: "#262B35" } }, y: { ticks: { color: "#9BA1AE", font: { size: 11 } }, grid: { display: false } } } }),
  });

  /* ---------------- Interactive registry table ---------------- */
  const tbody = document.getElementById("registry-body");
  const searchInput = document.getElementById("registry-search");
  const catFilterWrap = document.getElementById("category-filters");
  const countLabel = document.getElementById("registry-count");
  let activeCategory = "all";
  let sortField = "confidence";
  let sortDir = -1;

  function confColor(c) {
    if (c >= 85) return COLORS.accent;
    if (c >= 65) return "#5FB3B3";
    if (c >= 45) return COLORS.amber;
    return COLORS.coral;
  }

  function verdictPill(tier) {
    const map = {
      buildable_today: ["pill-accent", "buildable today"],
      buildable_gated: ["pill-amber", "buildable, gated"],
      not_buildable: ["pill-coral", "not buildable"],
      not_verifiable: ["pill-coral", "not verifiable"],
    };
    const [cls, label] = map[tier] || ["pill-muted", tier];
    return `<span class="pill ${cls}">${label}</span>`;
  }

  function mcpPill(mcp) {
    const m = (mcp || "").toLowerCase();
    if (m.includes("official")) return `<span class="pill pill-blue"><i class="ti ti-plug"></i> official MCP</span>`;
    if (m.includes("third-party")) return `<span class="pill pill-muted"><i class="ti ti-plug"></i> 3rd-party MCP</span>`;
    return `<span class="pill pill-muted">no MCP</span>`;
  }

  function render() {
    const q = (searchInput?.value || "").toLowerCase().trim();
    let rows = DATA.filter(r => {
      const matchesCat = activeCategory === "all" || r.category === activeCategory;
      const matchesQ = !q || r.name.toLowerCase().includes(q) || (r.description || "").toLowerCase().includes(q) || r.category.toLowerCase().includes(q);
      return matchesCat && matchesQ;
    });
    rows = rows.slice().sort((a, b) => {
      let av = a[sortField], bv = b[sortField];
      if (typeof av === "string") { av = av.toLowerCase(); bv = bv.toLowerCase(); }
      if (av < bv) return -1 * sortDir;
      if (av > bv) return 1 * sortDir;
      return 0;
    });

    if (countLabel) countLabel.textContent = `${rows.length} / ${DATA.length} apps`;
    tbody.innerHTML = rows.map((r, idx) => `
      <tr data-idx="${idx}" class="main-row">
        <td class="font-medium text-[var(--text-primary)]">${r.name}</td>
        <td class="text-[var(--text-secondary)]">${r.category}</td>
        <td>${(r.authentication || []).map(a => `<span class="pill pill-muted">${a}</span>`).join(" ")}</td>
        <td>${verdictPill(r.buildability_tier)}</td>
        <td>${mcpPill(r.mcpSupport)}</td>
        <td><span class="conf-dot" style="background:${confColor(r.confidence)}"></span>${r.confidence}</td>
        <td class="text-[var(--text-muted)]"><i class="ti ti-chevron-down toggle-icon"></i></td>
      </tr>
      <tr class="row-detail hidden" data-detail="${idx}">
        <td colspan="7">
          <p class="mb-2">${r.description || ""}</p>
          <p class="mb-2"><span class="text-[var(--text-muted)]">Self-serve:</span> ${r.selfServe || "unknown"}</p>
          <p class="mb-2"><span class="text-[var(--text-muted)]">Blocker:</span> ${r.blocker || "none"}</p>
          <p class="mb-2"><span class="text-[var(--text-muted)]">Notes:</span> ${r.notes || ""}</p>
          <p><span class="text-[var(--text-muted)]">Evidence:</span> ${
            (r.evidence && r.evidence.length)
              ? r.evidence.map(u => `<a class="ev-link mr-3" href="${u}" target="_blank" rel="noopener">${u.replace(/^https?:\/\//, "")}</a>`).join("")
              : '<span class="italic">none located</span>'
          }</p>
        </td>
      </tr>
    `).join("");

    tbody.querySelectorAll(".main-row").forEach(tr => {
      tr.addEventListener("click", () => {
        const idx = tr.getAttribute("data-idx");
        const detail = tbody.querySelector(`[data-detail="${idx}"]`);
        const icon = tr.querySelector(".toggle-icon");
        detail.classList.toggle("hidden");
        icon.style.transform = detail.classList.contains("hidden") ? "rotate(0deg)" : "rotate(180deg)";
      });
    });
  }

  if (searchInput) searchInput.addEventListener("input", render);

  if (catFilterWrap) {
    const categories = ["all", ...Object.keys(ANALYSIS.category_distribution || {})];
    catFilterWrap.innerHTML = categories.map(c => `<button class="filter-btn ${c === "all" ? "active" : ""}" data-cat="${c}">${c === "all" ? "All categories" : c}</button>`).join("");
    catFilterWrap.querySelectorAll(".filter-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        catFilterWrap.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        activeCategory = btn.getAttribute("data-cat");
        render();
      });
    });
  }

  document.querySelectorAll("[data-sort]").forEach(th => {
    th.addEventListener("click", () => {
      const field = th.getAttribute("data-sort");
      if (sortField === field) sortDir *= -1; else { sortField = field; sortDir = -1; }
      render();
    });
  });

  if (tbody) render();

  /* ---------------- Mobile nav toggle ---------------- */
  const navToggle = document.getElementById("nav-toggle");
  const navMenu = document.getElementById("nav-menu");
  if (navToggle && navMenu) {
    navToggle.addEventListener("click", () => navMenu.classList.toggle("hidden"));
  }
})();
