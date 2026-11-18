// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

/* Manufacturing Excellence: the executive view of the plant's HR
 * Manufacturing Excellence workbook (excellence_page.py).
 *
 * One call draws it all, from the stored summaries: the twenty-three tiles,
 * the verdict, the plants side by side, the sections against the fourteen
 * indicators, the red flags, thirteen weeks and twelve months, the money and
 * the downtime, Day against Night, the labour cost flags and the lowest five
 * of each. Every row opens the record behind it.
 */

frappe.provide("hrms_addon");

const HRA_ME_STYLE = `
.hra-me { display: grid; gap: 14px; padding-bottom: 28px; }
.hra-me-bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.hra-me-bar select, .hra-me-bar input { max-width: 170px; }
.hra-me-band { border: 1px solid var(--hra-border, #C3D0E0); border-radius: 8px; background: var(--card-bg, #fff);
  overflow: hidden; }
.hra-me-head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; padding: 9px 14px;
  background: var(--hra-primary, #0A2540); }
.hra-me-head h4 { margin: 0; font-size: 13px; letter-spacing: .04em; text-transform: uppercase; color: #fff; }
.hra-me-head span { font-size: 12px; color: rgba(255,255,255,.75); }
.hra-me-body { padding: 14px; display: grid; gap: 12px; }
.hra-me-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.hra-me-tile { border: 1px solid var(--hra-border, #C3D0E0); border-left-width: 5px; border-radius: 8px;
  padding: 9px 11px; background: var(--hra-pale, #EEF3F9); }
.hra-me-tile b { display: block; font-size: 21px; line-height: 1.25; color: var(--hra-primary, #0A2540); }
.hra-me-tile small { display: block; color: var(--text-muted, #5B6B7F); font-size: 11.5px; }
.hra-me-green { border-left-color: #2E7D32; } .hra-me-amber { border-left-color: #C98A0B; }
.hra-me-red { border-left-color: #B3261E; } .hra-me-grey { border-left-color: #9AA5B1; }
.hra-me-verdict { font-size: 14px; font-weight: 600; }
.hra-me-cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 16px; }
.hra-me-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.hra-me-table th { text-align: left; font-weight: 600; color: var(--text-muted, #5B6B7F); padding: 4px 6px;
  border-bottom: 1px solid var(--hra-border, #C3D0E0); white-space: nowrap; }
.hra-me-table td { padding: 5px 6px; border-bottom: 1px solid var(--hra-readonly, #EDF1F7); }
.hra-me-table tr[data-route] { cursor: pointer; }
.hra-me-table .hra-me-num { text-align: right; white-space: nowrap; }
.hra-me-table td.hra-me-hot { background: #FBE3E1; color: #8E1F18; font-weight: 600; }
.hra-me-pill { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11.5px; color: #fff; }
.hra-me-pill.hra-me-green { background: #2E7D32; } .hra-me-pill.hra-me-amber { background: #C98A0B; }
.hra-me-pill.hra-me-red { background: #B3261E; } .hra-me-pill.hra-me-grey { background: #9AA5B1; }
.hra-me-flags { margin: 0; padding-left: 18px; font-size: 12.5px; }
.hra-me-flags li[data-route] { cursor: pointer; }
.hra-me-empty { color: var(--text-muted, #5B6B7F); font-size: 12.5px; margin: 0; }
.hra-me-chart { min-height: 220px; }
.hra-me-h5 { margin: 0 0 6px; font-size: 12.5px; font-weight: 600; }
`;
const HRA_ME_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
	"October", "November", "December"];
const HRA_ME_SIGNAL_COLUMNS = { attendance: "attendance", unauthorised: "unauthorised", overtime: "ot_share",
	ppe: "ppe", competency: "competency", grievances: "open_grievances", exits: "exits", overstaffed: "deployment" };
const HRA_ME_PERCENT = ["deployment", "attendance", "unauthorised", "ot_share", "budget_variance", "ppe", "competency"];
const HRA_ME_LIGHT = { "On Target": "green", Attention: "amber", Critical: "red", "Critical: Red Flag": "red",
	"No Data": "grey" };

frappe.pages["manufacturing-excellence"].on_page_load = function (wrapper) {
	if (!document.getElementById("hra-me-style")) {
		const sheet = document.createElement("style");
		sheet.id = "hra-me-style";
		sheet.textContent = HRA_ME_STYLE;
		document.head.appendChild(sheet);
	}
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Manufacturing Excellence"), single_column: true });
	wrapper.excellence = new hrms_addon.ManufacturingExcellence(page);
};

frappe.pages["manufacturing-excellence"].on_page_show = function (wrapper) {
	if (wrapper.excellence) wrapper.excellence.load();
};

hrms_addon.ManufacturingExcellence = class ManufacturingExcellence {
	constructor(page) {
		this.page = page;
		this.asked = { period_type: "Week" };
		this.$body = $('<div class="hra-me"></div>').appendTo(page.main);
		page.set_primary_action(__("Refresh"), () => this.load(true), "refresh");
		page.add_inner_button(__("Guide"), () => this.guide());
		this.loaded = false;
	}

	load(refresh) {
		if (this.loaded && !refresh) return;
		this.loaded = true;
		this.$body.html(`<p class="hra-me-empty">${__("Loading")}</p>`);
		frappe
			.xcall("hrms_addon.hrms_addon.excellence_page.data", Object.assign({}, this.asked, { refresh: refresh ? 1 : 0 }))
			.then((data) => this.draw(data));
	}

	esc(text) {
		return frappe.utils.escape_html(text === null || text === undefined ? "" : String(text));
	}

	value(kind, value) {
		if (value === null || value === undefined || value === "") return __("No Data");
		if (kind === "percent") return `${(value * 100).toFixed(1)}%`;
		if (kind === "money") return format_number(value, null, 0);
		if (kind === "score") return Number(value).toFixed(1);
		if (kind === "count") return format_number(value, null, 0);
		return this.esc(value);
	}

	band(title, note, body) {
		return `<div class="hra-me-band"><div class="hra-me-head"><h4>${this.esc(title)}</h4><span>${this.esc(
			note || ""
		)}</span></div><div class="hra-me-body">${body}</div></div>`;
	}

	tiles(tiles) {
		return `<div class="hra-me-tiles">${tiles
			.map(
				(tile) =>
					`<div class="hra-me-tile hra-me-${tile.light}"><small>${this.esc(__(tile.label))}</small><b>${this.value(
						tile.kind,
						tile.value
					)}</b><small>${this.esc(tile.note || "")}${
						tile.target !== null && tile.target !== undefined && tile.kind !== "text"
							? `${tile.note ? " · " : ""}${__("Target")} ${this.value(tile.kind, tile.target)}`
							: ""
					}</small></div>`
			)
			.join("")}</div>`;
	}

	bar(data) {
		const plants = [`<option value="">${__("All Plants")}</option>`]
			.concat(data.plants.map((plant) => `<option ${plant === data.branch ? "selected" : ""}>${this.esc(plant)}</option>`))
			.join("");
		const types = ["Week", "Month", "Quarter"]
			.map((kind) => `<option ${kind === data.period.type ? "selected" : ""} value="${kind}">${__(kind)}</option>`)
			.join("");
		let values;
		if (data.period.type === "Week") {
			values = Array.from({ length: 53 }, (_unused, index) => index + 1)
				.map((week) => `<option ${week === Number(data.period.value) ? "selected" : ""}>${week}</option>`)
				.join("");
		} else if (data.period.type === "Month") {
			values = HRA_ME_MONTHS.map((month) => `<option ${month === data.period.value ? "selected" : ""}>${month}</option>`).join("");
		} else {
			values = ["Q1", "Q2", "Q3", "Q4"].map((q) => `<option ${q === data.period.value ? "selected" : ""}>${q}</option>`).join("");
		}
		return `<div class="hra-me-bar">
			<select class="form-control input-xs" data-ask="branch">${plants}</select>
			<select class="form-control input-xs" data-ask="period_type">${types}</select>
			<input class="form-control input-xs" type="number" data-ask="year" value="${data.period.year}">
			<select class="form-control input-xs" data-ask="value">${values}</select>
			<span class="text-muted small">${this.esc(data.period.start)} ${__("to")} ${this.esc(data.period.end)}</span>
		</div>`;
	}

	table(heads, rows, numeric) {
		if (!rows.length) return `<p class="hra-me-empty">${__("Nothing in the period.")}</p>`;
		return `<table class="hra-me-table"><thead><tr>${heads
			.map((head, index) => `<th class="${(numeric || []).includes(index) ? "hra-me-num" : ""}">${this.esc(__(head))}</th>`)
			.join("")}</tr></thead><tbody>${rows.join("")}</tbody></table>`;
	}

	route_attr(route) {
		return route ? `data-route='${this.esc(JSON.stringify(route))}'` : "";
	}

	draw(data) {
		this.data = data;
		const pill = (status) => `<span class="hra-me-pill hra-me-${HRA_ME_LIGHT[status] || "grey"}">${this.esc(__(status || "No Data"))}</span>`;
		const parts = [this.bar(data)];
		parts.push(
			this.band(
				__("Production"),
				data.period.label,
				`<div class="hra-me-verdict">${this.esc(data.verdict)}</div>${this.tiles(data.production)}`
			)
		);
		parts.push(
			this.band(
				__("HR Excellence"),
				`${__("Score")} ${this.value("score", data.composite)}`,
				`<div>${pill(data.status)}</div>${this.tiles(data.hr)}${this.table(
					["Pillar", "Weight", "Score", "Status"],
					data.pillars.map(
						(row) =>
							`<tr><td>${this.esc(__(row.label))}</td><td class="hra-me-num">${row.weight}</td><td class="hra-me-num">${this.value(
								"score",
								row.score
							)}</td><td>${pill(row.status)}</td></tr>`
					),
					[1, 2]
				)}`
			)
		);
		parts.push(this.band(__("Plants"), "", this.comparison(data, pill)));
		parts.push(this.band(__("Sections and Workforce Signals"), __("Signals that occur together call for a look, not a conclusion"), this.heat(data)));
		parts.push(
			this.band(
				__("Red Flags"),
				"",
				data.red_flags.length
					? `<ul class="hra-me-flags">${data.red_flags
							.map((flag) => `<li ${this.route_attr(flag.route)}>${this.esc(flag.text)}</li>`)
							.join("")}</ul>`
					: `<p class="hra-me-empty">${__("None in the period.")}</p>`
			)
		);
		parts.push(
			this.band(
				__("Trends"),
				"",
				`<div class="hra-me-cols"><div><h5 class="hra-me-h5">${__("Thirteen Weeks")}</h5><div class="hra-me-chart" data-chart="weeks"></div></div>
				<div><h5 class="hra-me-h5">${__("Twelve Months")}</h5><div class="hra-me-chart" data-chart="months"></div></div></div>`
			)
		);
		parts.push(this.band(__("Money Lost and Downtime"), "", this.money(data)));
		parts.push(this.band(__("Day and Night"), "", this.shifts(data)));
		parts.push(this.band(__("Labour Cost Flags"), __("Against the period before of the same length"), this.labour(data)));
		parts.push(this.band(__("The Lowest Five"), "", this.top(data)));
		this.$body.html(parts.join(""));
		this.charts(data);
		this.bind();
	}

	comparison(data, pill) {
		return this.table(
			["Plant", "Score", "Status", "Money Lost", "Attendance", "PPE", "Overtime %", "Incidents", "Machine Hours Lost", "Verdict"],
			data.comparison.map(
				(row) =>
					`<tr><td>${this.esc(row.branch)}</td><td class="hra-me-num">${this.value("score", row.score)}</td><td>${pill(
						row.status
					)}</td><td class="hra-me-num">${this.value("money", row.money_lost)}</td><td class="hra-me-num">${this.value(
						"percent",
						row.attendance
					)}</td><td class="hra-me-num">${this.value("percent", row.ppe)}</td><td class="hra-me-num">${this.value(
						"percent",
						row.ot_share
					)}</td><td class="hra-me-num">${this.value("count", row.incidents)}</td><td class="hra-me-num">${this.value(
						"count",
						row.hours_lost
					)}</td><td>${this.esc(row.verdict)}</td></tr>`
			),
			[1, 3, 4, 5, 6, 7, 8]
		);
	}

	heat(data) {
		const heads = ["Section"].concat(data.heat_columns.map((column) => column[1])).concat(["Signals", "HR Alert", ""]);
		const rows = data.heat.map((row, index) => {
			const hot = new Set((row.keys || []).map((key) => HRA_ME_SIGNAL_COLUMNS[key]));
			const cells = data.heat_columns
				.map(([key]) => {
					const kind = HRA_ME_PERCENT.includes(key) ? "percent" : key === "output_per_person" ? "score" : "count";
					return `<td class="hra-me-num ${hot.has(key) ? "hra-me-hot" : ""}">${this.value(kind, row[key])}</td>`;
				})
				.join("");
			const raise = row.count
				? `<button class="btn btn-xs btn-default" data-raise="${index}">${__("Raise HR Intervention")}</button>`
				: "";
			return `<tr><td>${this.esc(row.label)}</td>${cells}<td class="hra-me-num">${row.count}</td><td>${this.esc(
				row.alert
			)}</td><td>${raise}</td></tr>`;
		});
		return `<div style="overflow-x:auto">${this.table(heads, rows, data.heat_columns.map((_column, index) => index + 1))}</div>`;
	}

	money(data) {
		const downtime = this.table(
			["Reason", "Category", "Hours Lost", "Share of Hours Lost", "Shifts Hit"],
			data.downtime.map(
				(row) =>
					`<tr><td>${this.esc(row.reason)}</td><td>${this.esc(row.category)}</td><td class="hra-me-num">${row.hours.toFixed(
						1
					)}</td><td class="hra-me-num">${(row.share * 100).toFixed(1)}%</td><td class="hra-me-num">${row.shifts}</td></tr>`
			),
			[2, 3, 4]
		);
		return `<div class="hra-me-cols"><div><h5 class="hra-me-h5">${__("Waste and Complaints by Section")}</h5><div class="hra-me-chart" data-chart="money"></div></div>
			<div><h5 class="hra-me-h5">${__("Downtime by Reason")}</h5>${downtime}</div></div>`;
	}

	shifts(data) {
		return this.table(
			["Shift", "Score", "Person-Shifts", "Labour", "Overtime %", "Attendance", "Unauthorised Absent", "PPE", "Kg per Person-Shift", "Money Lost", "Incidents"],
			data.shifts.map(
				(row) =>
					`<tr><td>${this.esc(__(row.shift))}</td><td class="hra-me-num">${this.value("score", row.score)}</td><td class="hra-me-num">${this.value(
						"count",
						row.person_shifts
					)}</td><td class="hra-me-num">${this.value("money", row.labour)}</td><td class="hra-me-num">${this.value(
						"percent",
						row.ot_share
					)}</td><td class="hra-me-num">${this.value("percent", row.attendance)}</td><td class="hra-me-num">${this.value(
						"count",
						row.unauthorised
					)}</td><td class="hra-me-num">${this.value("percent", row.ppe)}</td><td class="hra-me-num">${this.value(
						"score",
						row.kg_per_person
					)}</td><td class="hra-me-num">${this.value("money", row.money_lost)}</td><td class="hra-me-num">${this.value(
						"count",
						row.incidents
					)}</td></tr>`
			),
			[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
		);
	}

	labour(data) {
		const flagged = data.labour.filter((row) => row.flags.length);
		return this.table(
			["Section", "Labour", "Overtime Cost", "Overtime %", "Flags", "Suggested HR Intervention"],
			flagged.map(
				(row) =>
					`<tr ${this.route_attr(["Form", "Work Section", row.section])}><td>${this.esc(row.label)}</td><td class="hra-me-num">${this.value(
						"money",
						row.labour
					)}</td><td class="hra-me-num">${this.value("money", row.ot_cost)}</td><td class="hra-me-num">${this.value(
						"percent",
						row.ot_share
					)}</td><td>${this.esc(row.flags.join(", "))}</td><td>${this.esc(row.intervention)}</td></tr>`
			),
			[1, 2, 3]
		);
	}

	top(data) {
		const list = (title, rows, kind) =>
			`<div><h5 class="hra-me-h5">${this.esc(title)}</h5>${this.table(
				["", ""],
				rows.map(
					(row) =>
						`<tr ${this.route_attr(row.route)}><td>${this.esc(row.label)}<br><small class="text-muted">${this.esc(
							row.note || ""
						)}</small></td><td class="hra-me-num">${kind ? this.value(kind, row.value) : this.esc(row.value)}</td></tr>`
				),
				[1]
			)}</div>`;
		const parts = [
			list(__("Sections"), data.top.sections, "score"),
			list(__("Supervisors"), data.top.supervisors, "score"),
			list(__("Costliest Shifts"), data.top.shifts, "money"),
			list(__("Interventions Overdue"), data.top.interventions, null),
		];
		if (data.can_cases) parts.push(list(__("Cases to Act On"), data.top.cases, null));
		return `<div class="hra-me-cols">${parts.join("")}</div>`;
	}

	charts(data) {
		const make = (name, spec) => {
			const element = this.$body.find(`[data-chart="${name}"]`)[0];
			if (element && spec.data.labels.length) new frappe.Chart(element, Object.assign({ height: 220 }, spec));
		};
		make("weeks", {
			type: "line",
			colors: ["#0A2540", "#C9A227", "#5E8C61"],
			lineOptions: { regionFill: 0, dotSize: 3 },
			data: {
				labels: data.weeks.map((row) => row.week.slice(5)),
				datasets: [
					{ name: __("Plant Score"), values: data.weeks.map((row) => row.score || 0) },
					{ name: __("Attendance %"), values: data.weeks.map((row) => (row.attendance || 0) * 100) },
					{ name: __("PPE %"), values: data.weeks.map((row) => (row.ppe || 0) * 100) },
				],
			},
		});
		make("months", {
			type: "line",
			colors: ["#0A2540", "#C9A227"],
			lineOptions: { regionFill: 0, dotSize: 3 },
			data: {
				labels: data.months.map((row) => row.month),
				datasets: [
					{ name: __("Attendance %"), values: data.months.map((row) => (row.attendance || 0) * 100) },
					{ name: __("Overtime % of Labour"), values: data.months.map((row) => (row.ot_share || 0) * 100) },
				],
			},
		});
		make("money", {
			type: "bar",
			colors: ["#0A2540", "#C9A227"],
			barOptions: { stacked: 1 },
			data: {
				labels: data.money.map((row) => row.label),
				datasets: [
					{ name: __("Waste"), values: data.money.map((row) => row.waste) },
					{ name: __("Complaints"), values: data.money.map((row) => row.complaints) },
				],
			},
		});
	}

	bind() {
		this.$body.find("[data-ask]").on("change", (event) => {
			const field = $(event.currentTarget).attr("data-ask");
			this.asked[field] = $(event.currentTarget).val();
			if (field === "period_type") {
				this.asked.value = null;
			}
			this.load(true);
		});
		this.$body.find("[data-route]").on("click", (event) => {
			frappe.set_route(...JSON.parse($(event.currentTarget).attr("data-route")));
		});
		this.$body.find("[data-raise]").on("click", (event) => {
			event.stopPropagation();
			const row = this.data.heat[Number($(event.currentTarget).attr("data-raise"))];
			frappe.new_doc("HR Intervention", {
				work_section: row.section,
				pillar: row.pillar || undefined,
				intervention: row.intervention || "Other",
				kpi: row.kpi || undefined,
				signal_source: "Section Signals",
				signal: `${row.alert}: ${(row.signals || []).join(", ")}`,
				signal_period: this.data.period.label,
				section_week: row.week_record || undefined,
				observation: (row.signals || []).join(", "),
			});
		});
	}

	guide() {
		frappe.xcall("hrms_addon.hrms_addon.excellence.guide").then((guide) => {
			const dialog = new frappe.ui.Dialog({ title: __("Guide"), size: "extra-large", fields: [{ fieldtype: "HTML", fieldname: "body" }] });
			dialog.fields_dict.body.$wrapper.html(this.guide_html(guide));
			dialog.show();
		});
	}

	guide_html(guide) {
		const table = (heads, rows) => this.table(heads, rows.map((row) => `<tr>${row.map((cell) => `<td>${this.esc(cell)}</td>`).join("")}</tr>`));
		return [
			`<h5 class="hra-me-h5">${__("Indicators")}</h5>`,
			table(["Indicator", "Pillar", "How It Is Worked Out", "Source", "Owner", "Target"], guide.kpis),
			`<h5 class="hra-me-h5">${__("Who Enters What")}</h5>`,
			table(["Document", "Entered By", "What", "When", "Checked By", "Used For"], guide.guide),
			`<h5 class="hra-me-h5">${__("Rules")}</h5>`,
			table(["Rule", "What Happens"], guide.governance),
		].join("");
	}
};
