// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

/* HR Overview — the HR home dashboard.
 *
 * One call fills it (hrms_addon.hrms_addon.hr_overview.overview) and
 * nothing here writes. The header greets the user over four tiles (the
 * people employed, who is on site today, who is on leave, the year's
 * turnover); below them the headcount month by month and the attendance
 * of the last days marked; then the user's own tasks, the appraisal cycle
 * and the people by employment type.
 *
 * The charts are SVG drawn here rather than frappe-charts, for the rings,
 * the gauge, the donut and the rounded bars. The styles live in this file
 * for the reason the attendance board gives: a page script is served as
 * it is, so the page never waits on `bench build`.
 */

frappe.provide("hrms_addon");

const HRO_COLOURS = {
	navy: "#14395E",
	steel: "#2A5A8C",
	blue: "#3B78B5",
	sky: "#9DBCE0",
	gold: "#E8A317",
	red: "#D9534F",
	grey: "#B8C2CF",
};
// the attendance stack and the donut, in order
const HRO_STACK = { "On Time": HRO_COLOURS.blue, Late: HRO_COLOURS.gold, Absent: HRO_COLOURS.red, "On Leave": HRO_COLOURS.grey };
// neighbours kept apart: navy never next to steel
const HRO_SLICES = [HRO_COLOURS.navy, HRO_COLOURS.gold, HRO_COLOURS.blue, HRO_COLOURS.sky, HRO_COLOURS.grey, HRO_COLOURS.steel];
const HRO_URGENCY = { overdue: HRO_COLOURS.red, today: HRO_COLOURS.gold, soon: HRO_COLOURS.blue, later: HRO_COLOURS.steel, none: HRO_COLOURS.grey };
// line glyphs for the tiles, drawn in a 24 x 24 box
const HRO_GLYPHS = {
	people: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6.5 6.5-6.5s6.5 2.9 6.5 6.5"/><circle cx="17" cy="9" r="2.6"/><path d="M15.5 13.8c3.4-.4 6 1.9 6 5.2"/>',
	clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
	leave: '<rect x="3.5" y="5" width="17" height="15" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4M9.5 14.5l5 3M14.5 14.5l-5 3"/>',
	turnover: '<path d="M4 9h13l-3.5-3.5M20 15H7l3.5 3.5"/>',
};

const HRO_STYLE = `
.hro {
  --hro-navy: var(--hra-primary, ${HRO_COLOURS.navy});
  --hro-gold: ${HRO_COLOURS.gold};
  --hro-card: var(--card-bg, #FFFFFF);
  --hro-ink: var(--text-color, #1A2733);
  --hro-muted: var(--text-muted, #6B7A8C);
  --hro-line: var(--border-color, #DCE4EF);
  --hro-hero: #E7F0FA;
  --hro-radius: 18px;
  padding: 6px 0 28px;
  color: var(--hro-ink);
}
html[data-theme="dark"] .hro { --hro-hero: rgba(91, 143, 199, 0.16); }
.page-container[data-page-route="hr-overview"] .layout-main-section {
  background: transparent !important; border: 0 !important; box-shadow: none !important; padding: 0 !important;
}
.hro-card {
  background: var(--hro-card); border: 1px solid var(--hro-line); border-radius: var(--hro-radius);
  padding: 18px 20px; min-width: 0;
}
.hro-card h4 { margin: 0; font-size: 15px; font-weight: 600; color: var(--hro-ink); }
.hro-card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
.hro-card-head .hro-sub { font-size: 12px; color: var(--hro-muted); }
.hro-link { cursor: pointer; }
.hro-link:hover h4 { color: var(--hro-navy); }

.hro-hero {
  display: grid; grid-template-columns: minmax(220px, 1fr) minmax(0, 2.4fr); gap: 18px; align-items: center;
  background: var(--hro-hero); border-radius: 22px; padding: 22px 22px 22px 28px; margin-bottom: 18px;
}
.hro-date { font-size: 13px; color: var(--hro-muted); margin: 0 0 6px; }
.hro-hello { font-size: 28px; font-weight: 600; margin: 0; color: var(--hro-navy); line-height: 1.25; }
.hro-where { font-size: 13px; color: var(--hro-muted); margin: 6px 0 0; }
.hro-tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.hro-tile {
  background: var(--hro-card); border-radius: var(--hro-radius); padding: 14px 16px; cursor: pointer;
  border: 1px solid transparent; transition: border-color .15s ease, transform .15s ease;
}
.hro-tile:hover { border-color: var(--hro-line); transform: translateY(-1px); }
.hro-badge { position: relative; width: 46px; height: 46px; margin-bottom: 10px; }
.hro-badge svg.hro-ring { position: absolute; inset: 0; }
.hro-badge .hro-dot {
  position: absolute; inset: 5px; border-radius: 50%; background: var(--hro-navy);
  display: flex; align-items: center; justify-content: center;
}
.hro-badge .hro-dot svg { width: 18px; height: 18px; fill: none; stroke: #FFFFFF; stroke-width: 1.9;
  stroke-linecap: round; stroke-linejoin: round; }
.hro-value { font-size: 26px; font-weight: 600; line-height: 1.1; color: var(--hro-ink); }
.hro-label { font-size: 13px; color: var(--hro-ink); margin-top: 2px; }
.hro-note { font-size: 12px; color: var(--hro-muted); margin-top: 2px; }

.hro-row { display: grid; gap: 18px; margin-bottom: 18px; }
.hro-row-2 { grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); }
.hro-row-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.hro-big { font-size: 30px; font-weight: 600; color: var(--hro-ink); }
.hro-delta { display: inline-block; font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 999px; margin-left: 8px;
  vertical-align: middle; }
.hro-delta.up { background: #E3F1E7; color: #256F3A; }
.hro-delta.down { background: #FBEAE9; color: #A62B25; }
.hro-delta.flat { background: #EEF1F4; color: var(--hro-muted); }
.hro-chart svg { width: 100%; height: auto; max-height: 300px; display: block; overflow: visible; }
.hro-chart text { font-size: 11px; fill: var(--hro-muted); }
.hro-legend { display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; color: var(--hro-muted); }
.hro-legend i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; }
.hro-empty { font-size: 13px; color: var(--hro-muted); padding: 28px 0; text-align: center; }

.hro-task { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 14px;
  background: var(--subtle-fg, #F4F7FB); margin-bottom: 8px; cursor: pointer; }
.hro-task:hover { background: var(--hro-hero); }
.hro-task-text { min-width: 0; flex: 1; }
.hro-task-title { font-size: 13px; font-weight: 600; color: var(--hro-ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hro-task-when { font-size: 12px; color: var(--hro-muted); }

.hro-bands { margin-top: 6px; }
.hro-band { display: grid; grid-template-columns: 96px minmax(0, 1fr) 32px; gap: 8px; align-items: center; font-size: 12px;
  color: var(--hro-muted); margin-bottom: 6px; }
.hro-band-bar { height: 7px; border-radius: 999px; background: var(--hro-line); overflow: hidden; }
.hro-band-bar span { display: block; height: 100%; border-radius: 999px; background: var(--hro-navy); }
.hro-band b { text-align: right; color: var(--hro-ink); font-weight: 600; }

.hro-donut { display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 14px; align-items: center; }
.hro-slices { font-size: 12px; }
.hro-slice { display: flex; align-items: center; gap: 8px; padding: 4px 0; cursor: pointer; color: var(--hro-ink); }
.hro-slice i { width: 9px; height: 9px; border-radius: 50%; flex: none; }
.hro-slice span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hro-slice b { font-weight: 600; }

@media (max-width: 1199px) {
  .hro-hero { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 991px) {
  .hro-row-2, .hro-row-3 { grid-template-columns: minmax(0, 1fr); }
  .hro-tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 575px) {
  .hro-hero { padding: 18px; }
  .hro-hello { font-size: 22px; }
  .hro-donut { grid-template-columns: minmax(0, 1fr); justify-items: center; }
}
`;

frappe.pages["hr-overview"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("HR Overview"), single_column: true });
	wrapper.overview = new hrms_addon.HROverview(page);
};

frappe.pages["hr-overview"].on_page_show = function (wrapper) {
	if (wrapper.overview) wrapper.overview.refresh();
};

hrms_addon.HROverview = class HROverview {
	constructor(page) {
		this.page = page;
		if (!document.getElementById("hro-style")) {
			$('<style id="hro-style"></style>').text(HRO_STYLE).appendTo("head");
		}
		this.body = $('<div class="hro"></div>').appendTo(this.page.main);
		this.branch_field = this.page.add_field({
			fieldname: "branch",
			fieldtype: "Link",
			options: "Branch",
			label: __("Branch"),
			change: () => this.refresh(),
		});
		this.page.set_secondary_action(__("Refresh"), () => this.refresh(), "refresh");
	}

	refresh() {
		const args = {};
		const branch = this.branch_field.get_value();
		if (branch) args.branch = branch;
		return frappe.xcall("hrms_addon.hrms_addon.hr_overview.overview", args).then((data) => this.render(data || {}));
	}

	render(data) {
		this.data = data;
		const esc = frappe.utils.escape_html;
		const kpis = data.kpis || {};
		const turnover = kpis.turnover || {};
		const joined = kpis.joined_this_month || 0;
		this.body.html(`
			<div class="hro-hero">
				<div>
					<p class="hro-date">${esc(moment(data.today).format("dddd, D MMMM YYYY"))}</p>
					<h2 class="hro-hello">${esc(__(data.greeting || "Hello"))}, ${esc(data.first_name || "")}</h2>
					<p class="hro-where">${esc(data.branch || __("All branches"))}</p>
				</div>
				<div class="hro-tiles">
					${this.tile("employees", "people", null, this.number(kpis.employees), __("Employees"),
						joined ? __("{0} joined this month", [joined]) : __("No one joined this month"))}
					${this.tile("on_site", "clock", kpis.on_site_percent, this.number(kpis.on_site), __("On site today"),
						__("{0}% of employees", [this.number(kpis.on_site_percent)]))}
					${this.tile("on_leave", "leave", null, this.number(kpis.on_leave), __("On leave today"),
						__("On approved leave"))}
					${this.tile("turnover", "turnover", turnover.rate, `${this.number(turnover.rate)}%`, __("Turnover"),
						__("{0} left in 12 months", [turnover.leavers || 0]))}
				</div>
			</div>
			<div class="hro-row hro-row-2">
				<div class="hro-card hro-link" data-go="headcount">${this.headcount_card(data.headcount || {})}</div>
				<div class="hro-card hro-link" data-go="attendance">${this.attendance_card(data.attendance || [])}</div>
			</div>
			<div class="hro-row hro-row-3">
				<div class="hro-card">${this.tasks_card(data.tasks || [])}</div>
				<div class="hro-card hro-link" data-go="appraisals">${this.appraisal_card(data.appraisals)}</div>
				<div class="hro-card">${this.employment_card(data.employment || [])}</div>
			</div>
		`);
		this.bind();
	}

	bind() {
		const routes = {
			employees: () => frappe.set_route("List", "Employee", { status: "Active" }),
			on_site: () => frappe.set_route("attendance-board"),
			on_leave: () => frappe.set_route("List", "Leave Application", { status: "Approved" }),
			turnover: () => frappe.set_route("List", "Employee", { status: "Left" }),
			headcount: () => frappe.set_route("List", "Employee", { status: "Active" }),
			attendance: () => frappe.set_route("List", "Attendance"),
			appraisals: () => frappe.set_route("List", "Appraisal"),
		};
		this.body.find("[data-go]").on("click", (event) => {
			const go = routes[$(event.currentTarget).attr("data-go")];
			if (go) go();
		});
		this.body.find("[data-task]").on("click", (event) => {
			event.stopPropagation();
			const task = (this.data.tasks || [])[parseInt($(event.currentTarget).attr("data-task"), 10)];
			if (task && task.doctype && task.docname) frappe.set_route("Form", task.doctype, task.docname);
		});
		this.body.find("[data-slice]").on("click", (event) => {
			const slice = (this.data.employment || [])[parseInt($(event.currentTarget).attr("data-slice"), 10)];
			if (slice) frappe.set_route("List", "Employee", { status: "Active", employment_type: slice[0] === "Not Set" ? ["is", "not set"] : slice[0] });
		});
	}

	// ── the tiles ────────────────────────────────────────────────────
	tile(go, glyph, ring, value, label, note) {
		const esc = frappe.utils.escape_html;
		const around = ring === null || ring === undefined ? "" : hro_ring(Math.min(Math.max(ring, 0), 100), 46, 4, HRO_COLOURS.gold);
		return `<div class="hro-tile" data-go="${go}">
			<div class="hro-badge">${around}<div class="hro-dot"><svg viewBox="0 0 24 24">${HRO_GLYPHS[glyph]}</svg></div></div>
			<div class="hro-value">${esc(value)}</div>
			<div class="hro-label">${esc(label)}</div>
			<div class="hro-note">${esc(note)}</div>
		</div>`;
	}

	// ── the headcount, month by month ────────────────────────────────
	headcount_card(headcount) {
		const values = headcount.values || [];
		const months = (headcount.months || []).map((day) => moment(day).format("MMM"));
		const now = values.length ? values[values.length - 1] : 0;
		const before = values.length > 1 ? values[values.length - 2] : now;
		const change = now - before;
		const delta = change > 0 ? `<span class="hro-delta up">+${change}</span>`
			: change < 0 ? `<span class="hro-delta down">${change}</span>` : `<span class="hro-delta flat">0</span>`;
		return `<div class="hro-card-head"><h4>${__("Headcount")}</h4><span class="hro-sub">${__("Last 12 months")}</span></div>
			<div><span class="hro-big">${this.number(now)}</span>${delta}</div>
			<div class="hro-sub" style="font-size:12px;color:var(--hro-muted);margin-bottom:6px">${__("Change since last month")}</div>
			<div class="hro-chart">${values.length ? hro_line(months, values) : `<div class="hro-empty">${__("No employees yet.")}</div>`}</div>`;
	}

	// ── the attendance of the last days marked ───────────────────────
	attendance_card(days) {
		const legend = Object.entries(HRO_STACK)
			.map(([kind, colour]) => `<span><i style="background:${colour}"></i>${__(kind)}</span>`).join("");
		const chart = days.length ? hro_stack(days) : `<div class="hro-empty">${__("No attendance marked in the last three weeks.")}</div>`;
		return `<div class="hro-card-head"><h4>${__("Attendance")}</h4><span class="hro-sub">${__("Last days marked")}</span></div>
			<div class="hro-legend" style="margin-bottom:8px">${legend}</div>
			<div class="hro-chart">${chart}</div>`;
	}

	// ── the user's own tasks ─────────────────────────────────────────
	tasks_card(tasks) {
		const esc = frappe.utils.escape_html;
		const rows = tasks.map((task, index) => `<div class="hro-task" data-task="${index}">
				${hro_ring(task.ring || 0, 38, 4, HRO_URGENCY[task.urgency] || HRO_COLOURS.grey)}
				<div class="hro-task-text">
					<div class="hro-task-title">${esc(task.title || "")}</div>
					<div class="hro-task-when">${esc([task.doctype ? __(task.doctype) : "", task.when || ""].filter(Boolean).join(" · "))}</div>
				</div>
			</div>`).join("");
		return `<div class="hro-card-head"><h4>${__("My Tasks")}</h4><span class="hro-sub">${__("Most pressing first")}</span></div>
			${rows || `<div class="hro-empty">${__("Nothing assigned to you.")}</div>`}`;
	}

	// ── the appraisal cycle ──────────────────────────────────────────
	appraisal_card(appraisals) {
		const esc = frappe.utils.escape_html;
		if (!appraisals || !appraisals.total) {
			return `<div class="hro-card-head"><h4>${__("Appraisals")}</h4></div>
				<div class="hro-empty">${__("No appraisals in the current cycle.")}</div>`;
		}
		const most = Math.max(1, ...(appraisals.bands || []).map(([, count]) => count));
		const bands = (appraisals.bands || []).map(([band, count]) => `<div class="hro-band">
				<span>${esc(__(band))}</span>
				<div class="hro-band-bar"><span style="width:${Math.round((100 * count) / most)}%"></span></div>
				<b>${count}</b>
			</div>`).join("");
		return `<div class="hro-card-head"><h4>${__("Appraisals")}</h4><span class="hro-sub">${esc(appraisals.cycle || "")}</span></div>
			<div class="hro-chart" style="max-width:240px;margin:0 auto">${hro_gauge(appraisals.percent || 0,
				__("{0} of {1} submitted", [appraisals.submitted, appraisals.total]))}</div>
			<div class="hro-sub" style="text-align:center;font-size:12px;color:var(--hro-muted);margin:2px 0 8px">
				${__("Average score {0}%", [this.number(appraisals.average)])}</div>
			<div class="hro-bands">${bands}</div>`;
	}

	// ── the people by employment type ────────────────────────────────
	employment_card(employment) {
		const esc = frappe.utils.escape_html;
		const total = employment.reduce((sum, [, count]) => sum + count, 0);
		if (!total) {
			return `<div class="hro-card-head"><h4>${__("Employment Type")}</h4></div>
				<div class="hro-empty">${__("No active employees.")}</div>`;
		}
		const slices = employment.map(([kind, count], index) => `<div class="hro-slice" data-slice="${index}">
				<i style="background:${HRO_SLICES[index % HRO_SLICES.length]}"></i><span>${esc(__(kind))}</span>
				<b>${count}</b></div>`).join("");
		return `<div class="hro-card-head"><h4>${__("Employment Type")}</h4><span class="hro-sub">${__("Active employees")}</span></div>
			<div class="hro-donut"><div class="hro-chart">${hro_donut(employment, total)}</div>
			<div class="hro-slices">${slices}</div></div>`;
	}

	number(value) {
		return format_number(value || 0, null, Number.isInteger(value || 0) ? 0 : 1);
	}
};

// ── SVG drawing ──────────────────────────────────────────────────────
// A ring filled to `percent`, starting at the top and going clockwise.
function hro_ring(percent, size, width, colour) {
	const radius = (size - width) / 2;
	const length = 2 * Math.PI * radius;
	const filled = (length * Math.min(Math.max(percent || 0, 0), 100)) / 100;
	const centre = size / 2;
	return `<svg class="hro-ring" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="flex:none">
		<circle cx="${centre}" cy="${centre}" r="${radius}" fill="none" stroke="rgba(120,140,165,.22)" stroke-width="${width}"/>
		<circle cx="${centre}" cy="${centre}" r="${radius}" fill="none" stroke="${colour}" stroke-width="${width}"
			stroke-linecap="round" stroke-dasharray="${filled} ${length}" transform="rotate(-90 ${centre} ${centre})"/>
	</svg>`;
}

// A smooth line over the months, its area shaded, the last month called out.
function hro_line(labels, values) {
	const width = 640, height = 230, left = 40, right = 18, top = 30, bottom = 28;
	const low = Math.min(...values), high = Math.max(...values);
	const span = high - low || Math.max(1, high * 0.1);
	const floor = Math.max(0, Math.floor(low - span * 0.15)), ceiling = Math.ceil(high + span * 0.15);
	const x = (i) => left + (values.length > 1 ? (i * (width - left - right)) / (values.length - 1) : (width - left - right) / 2);
	const y = (v) => top + (height - top - bottom) * (1 - (v - floor) / (ceiling - floor || 1));
	const points = values.map((v, i) => [x(i), y(v)]);
	let path = `M${points[0][0]},${points[0][1]}`;
	for (let i = 0; i < points.length - 1; i++) {
		const [x0, y0] = points[i - 1] || points[i];
		const [x1, y1] = points[i];
		const [x2, y2] = points[i + 1];
		const [x3, y3] = points[i + 2] || points[i + 1];
		path += ` C${x1 + (x2 - x0) / 6},${y1 + (y2 - y0) / 6} ${x2 - (x3 - x1) / 6},${y2 - (y3 - y1) / 6} ${x2},${y2}`;
	}
	const area = `${path} L${points[points.length - 1][0]},${height - bottom} L${points[0][0]},${height - bottom} Z`;
	const grid = [0, 1, 2, 3].map((step) => {
		const value = floor + ((ceiling - floor) * step) / 3;
		return `<line x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}" stroke="rgba(120,140,165,.18)"/>
			<text x="${left - 8}" y="${y(value) + 4}" text-anchor="end">${format_number(Math.round(value), null, 0)}</text>`;
	}).join("");
	const ticks = labels.map((label, i) => `<text x="${x(i)}" y="${height - 8}" text-anchor="middle">${frappe.utils.escape_html(label)}</text>`).join("");
	const dots = points.map(([px, py], i) => `<circle cx="${px}" cy="${py}" r="3" fill="#FFFFFF" stroke="${HRO_COLOURS.navy}" stroke-width="2">
			<title>${frappe.utils.escape_html(labels[i])}: ${format_number(values[i], null, 0)}</title></circle>`).join("");
	const [lx, ly] = points[points.length - 1];
	const callout = format_number(values[values.length - 1], null, 0);
	const pill = 16 + callout.length * 7;
	return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${__("Headcount")}">
		<defs><linearGradient id="hro-area" x1="0" y1="0" x2="0" y2="1">
			<stop offset="0" stop-color="${HRO_COLOURS.blue}" stop-opacity=".28"/><stop offset="1" stop-color="${HRO_COLOURS.blue}" stop-opacity="0"/>
		</linearGradient></defs>
		${grid}
		<path d="${area}" fill="url(#hro-area)"/>
		<path d="${path}" fill="none" stroke="${HRO_COLOURS.navy}" stroke-width="2.5" stroke-linecap="round"/>
		<line x1="${lx}" x2="${lx}" y1="${ly}" y2="${height - bottom}" stroke="${HRO_COLOURS.navy}" stroke-dasharray="3 3" opacity=".5"/>
		${dots}
		<rect x="${lx - pill / 2}" y="${ly - 30}" width="${pill}" height="20" rx="10" fill="${HRO_COLOURS.navy}"/>
		<text x="${lx}" y="${ly - 16}" text-anchor="middle" style="fill:#FFFFFF;font-weight:600">${callout}</text>
		${ticks}
	</svg>`;
}

// One stacked bar a day: on time at the bottom, then late, absent, on leave.
function hro_stack(days) {
	const width = 420, height = 230, left = 34, right = 8, top = 10, bottom = 26;
	const kinds = Object.keys(HRO_STACK);
	const totals = days.map((day) => kinds.reduce((sum, kind) => sum + (day[kind] || 0), 0));
	const most = Math.max(1, ...totals);
	const slot = (width - left - right) / days.length;
	const bar = Math.min(26, slot * 0.56);
	const scale = (height - top - bottom) / most;
	const grid = [0, 0.5, 1].map((share) => {
		const at = height - bottom - (height - top - bottom) * share;
		return `<line x1="${left}" x2="${width - right}" y1="${at}" y2="${at}" stroke="rgba(120,140,165,.18)"/>
			<text x="${left - 6}" y="${at + 4}" text-anchor="end">${format_number(Math.round(most * share), null, 0)}</text>`;
	}).join("");
	const bars = days.map((day, i) => {
		const x = left + slot * i + (slot - bar) / 2;
		let base = height - bottom;
		const parts = kinds.filter((kind) => day[kind]);
		const segments = parts.map((kind, index) => {
			const tall = day[kind] * scale;
			base -= tall;
			const fill = HRO_STACK[kind];
			const title = `<title>${frappe.utils.escape_html(__(kind))}: ${day[kind]}</title>`;
			// the top of the stack is rounded, the rest square
			return index === parts.length - 1
				? `<path d="${hro_top_rounded(x, base, bar, tall, Math.min(7, bar / 2, tall))}" fill="${fill}">${title}</path>`
				: `<rect x="${x}" y="${base}" width="${bar}" height="${tall}" fill="${fill}">${title}</rect>`;
		}).join("");
		return `${segments}<text x="${x + bar / 2}" y="${height - 8}" text-anchor="middle">${frappe.utils.escape_html(moment(day.date).format("D MMM"))}</text>`;
	}).join("");
	return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${__("Attendance")}">${grid}${bars}</svg>`;
}

// The outline of a bar with its top corners rounded.
function hro_top_rounded(x, y, w, h, r) {
	return `M${x},${y + h} L${x},${y + r} Q${x},${y} ${x + r},${y} L${x + w - r},${y} Q${x + w},${y} ${x + w},${y + r} L${x + w},${y + h} Z`;
}

// A half circle filled to `percent`, the figure in the middle.
function hro_gauge(percent, caption) {
	const radius = 80, width = 16, centre = 100;
	const length = Math.PI * radius;
	const filled = (length * Math.min(Math.max(percent || 0, 0), 100)) / 100;
	const arc = `M${centre - radius},${centre} A${radius},${radius} 0 0 1 ${centre + radius},${centre}`;
	return `<svg viewBox="0 0 200 118" role="img" aria-label="${frappe.utils.escape_html(caption)}">
		<path d="${arc}" fill="none" stroke="rgba(120,140,165,.22)" stroke-width="${width}" stroke-linecap="round"/>
		<path d="${arc}" fill="none" stroke="${HRO_COLOURS.navy}" stroke-width="${width}" stroke-linecap="round"
			stroke-dasharray="${filled} ${length}"/>
		<text x="${centre}" y="${centre - 12}" text-anchor="middle" style="font-size:30px;font-weight:600;fill:var(--hro-ink)">${format_number(percent || 0, null, 0)}%</text>
		<text x="${centre}" y="${centre + 8}" text-anchor="middle">${frappe.utils.escape_html(caption)}</text>
	</svg>`;
}

// A ring cut into one slice per kind, the total in the middle.
function hro_donut(parts, total) {
	const radius = 58, width = 20, centre = 75;
	const length = 2 * Math.PI * radius;
	const gap = parts.length > 1 ? 3 : 0;
	let offset = 0;
	const slices = parts.map(([kind, count], index) => {
		const share = (length * count) / total;
		const drawn = Math.max(share - gap, 0.5);
		const slice = `<circle cx="${centre}" cy="${centre}" r="${radius}" fill="none" stroke="${HRO_SLICES[index % HRO_SLICES.length]}"
			stroke-width="${width}" stroke-dasharray="${drawn} ${length - drawn}" stroke-dashoffset="${-offset}"
			transform="rotate(-90 ${centre} ${centre})"><title>${frappe.utils.escape_html(__(kind))}: ${count}</title></circle>`;
		offset += share;
		return slice;
	}).join("");
	return `<svg viewBox="0 0 150 150" role="img" aria-label="${__("Employment Type")}">
		${slices}
		<text x="${centre}" y="${centre + 2}" text-anchor="middle" style="font-size:24px;font-weight:600;fill:var(--hro-ink)">${format_number(total, null, 0)}</text>
		<text x="${centre}" y="${centre + 20}" text-anchor="middle">${__("Employees")}</text>
	</svg>`;
}
