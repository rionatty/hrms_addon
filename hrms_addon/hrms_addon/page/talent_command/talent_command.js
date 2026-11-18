// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

/* Talent Command: talent for the executives on one page (talent_command.py).
 *
 * One cached call adds everything up in SQL: the tiles; each plant (or
 * department) on the nine boxes beside the others, against the
 * distribution guide and the review before; the succession heat map
 * (impact by probability of loss), the bench and the successors named for
 * several roles; top talent and flight risk; the movement from box to box
 * since the review before; the graduate funnel by cohort. Every figure
 * opens the list it counts.
 */

frappe.provide("hrms_addon");

const TC_ROWS = [[3, 6, 9], [2, 5, 8], [1, 4, 7]];
const TC_TINTS = {
	Red: ["#F8DADA", "#8C2323"],
	Orange: ["#FCE5D2", "#8A4A12"],
	Yellow: ["#FBF1D3", "#6B4F00"],
	Blue: ["#DCE8F7", "#14395E"],
	Green: ["#D7F0DC", "#1E6B34"],
};
const TC_TONES = { good: "#1E6B34", soon: "#8A4A12", overdue: "#A62B25", none: "var(--text-color)" };
const TC_HEAT = [
	["#FCE5D2", "#F8DADA", "#F3B8B8"],
	["#FBF1D3", "#FCE5D2", "#F8DADA"],
	["#D7F0DC", "#FBF1D3", "#FCE5D2"],
];
const TC_STAGES = ["Recruited", "In Induction", "In Rotation", "Under Assessment", "Confirmed", "Exited"];

const TC_STYLE = `
.tc { padding: 4px 0 28px; color: var(--text-color); }
.tc-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
.tc-title { font-size: 18px; font-weight: 600; }
.tc-pill { border-radius: 999px; padding: 2px 10px; font-size: 12px; background: var(--control-bg); color: var(--text-muted); }
.tc-tiles { display: grid; grid-template-columns: repeat(8, minmax(0, 1fr)); gap: 10px; margin-bottom: 16px; }
.tc-tile { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 10px 12px; cursor: pointer; }
.tc-tile:hover { border-color: #14395E; }
.tc-tile small { display: block; color: var(--text-muted); font-size: 11.5px; }
.tc-tile b { font-size: 20px; font-weight: 600; }
.tc-tile em { display: block; font-style: normal; color: var(--text-muted); font-size: 11px; margin-top: 2px; }
.tc-box { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 12px 14px; margin-bottom: 14px; }
.tc-box h6 { margin: 0 0 10px; font-size: 13px; font-weight: 600; display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.tc-switch { display: inline-flex; border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; }
.tc-switch button { border: 0; background: var(--card-bg); color: var(--text-color); padding: 3px 10px; font-size: 12px; }
.tc-switch button.tc-on { background: #14395E; color: #fff; }
.tc-groups { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.tc-group h5 { font-size: 12.5px; font-weight: 600; margin: 0 0 6px; display: flex; justify-content: space-between; }
.tc-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px; }
.tc-cell { border-radius: 8px; padding: 6px; min-height: 58px; cursor: pointer; border: 2px solid transparent; font-size: 11px; }
.tc-cell:hover { border-color: #14395E; }
.tc-cell b { display: block; font-size: 15px; }
.tc-cell.tc-over { border-color: #A62B25; }
.tc-cell.tc-under { border-style: dashed; border-color: #8A4A12; }
.tc-cell span { opacity: .85; }
.tc-two { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; }
.tc-heat { width: 100%; border-collapse: separate; border-spacing: 4px; font-size: 12px; }
.tc-heat td, .tc-heat th { text-align: center; padding: 8px 4px; border-radius: 6px; }
.tc-heat td { cursor: pointer; font-weight: 600; font-size: 15px; }
.tc-heat th { color: var(--text-muted); font-weight: 500; }
.tc-list { width: 100%; font-size: 12px; }
.tc-list td, .tc-list th { padding: 5px 4px; border-top: 1px solid var(--border-color); vertical-align: top; }
.tc-list th { color: var(--text-muted); font-weight: 500; border-top: 0; }
.tc-list tr.tc-go { cursor: pointer; }
.tc-list tr.tc-go:hover td { background: var(--control-bg); }
.tc-matrix { border-collapse: collapse; font-size: 11.5px; }
.tc-matrix td, .tc-matrix th { width: 40px; height: 28px; text-align: center; border: 1px solid var(--border-color); }
.tc-matrix th { color: var(--text-muted); font-weight: 500; background: var(--control-bg); }
.tc-matrix td.tc-n { cursor: pointer; }
.tc-matrix td.tc-same { background: var(--control-bg); }
.tc-flag { border-radius: 6px; padding: 0 5px; font-size: 10.5px; font-weight: 600; }
.tc-bad { background: #F8DADA; color: #8C2323; }
.tc-warn { background: #FBF1D3; color: #6B4F00; }
.tc-good { background: #D7F0DC; color: #1E6B34; }
.tc-empty { color: var(--text-muted); font-size: 12px; }
.tc-note { color: var(--text-muted); font-size: 11.5px; margin-top: 6px; }
@media (max-width: 1199px) { .tc-tiles { grid-template-columns: repeat(4, minmax(0, 1fr)); } .tc-groups { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 991px) { .tc-two { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 575px) { .tc-tiles, .tc-groups { grid-template-columns: minmax(0, 1fr); } }
`;

frappe.pages["talent-command"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Talent Command"), single_column: true });
	wrapper.talent_command = new hrms_addon.TalentCommand(page);
};

frappe.pages["talent-command"].on_page_show = function (wrapper) {
	if (wrapper.talent_command) wrapper.talent_command.refresh();
};

hrms_addon.TalentCommand = class TalentCommand {
	constructor(page) {
		this.page = page;
		if (!document.getElementById("tc-style")) $('<style id="tc-style"></style>').text(TC_STYLE).appendTo("head");
		this.review = page.add_field({
			fieldname: "review", fieldtype: "Link", options: "Talent Review", label: __("Talent Review"),
			change: () => this.refresh(),
		});
		this.company = page.add_field({
			fieldname: "company", fieldtype: "Link", options: "Company", label: __("Company"),
			change: () => this.refresh(),
		});
		page.set_secondary_action(__("Refresh"), () => this.refresh(1), "refresh");
		this.body = $('<div class="tc"></div>').appendTo(page.main);
		this.split = "by_plant";
	}

	refresh(fresh) {
		const args = { fresh: fresh ? 1 : 0 };
		if (this.review.get_value()) args.review = this.review.get_value();
		if (this.company.get_value()) args.company = this.company.get_value();
		return frappe.xcall("hrms_addon.hrms_addon.talent_command.get_command", args).then((data) => {
			this.data = data || {};
			this.render();
		});
	}

	go(doctype, filters) {
		frappe.set_route("List", doctype, filters || {});
	}

	report(name, filters) {
		frappe.set_route("query-report", name, filters || {});
	}

	render() {
		const esc = frappe.utils.escape_html;
		const data = this.data;
		if (!data.review) {
			this.body.html(`<div class="tc-empty" style="padding:60px 10px;text-align:center">${esc(__("No talent review yet."))}</div>`);
			return;
		}
		const review = data.review;
		this.body.html(`
			<div class="tc-head">
				<span class="tc-title">${esc(review.title || review.name)}</span>
				<span class="tc-pill">${esc(__(review.status || ""))}</span>
				${data.before ? `<span class="tc-pill">${esc(__("Compared with {0}", [data.before]))}</span>` : ""}
				${(data.plants || []).length ? `<span class="tc-pill">${esc((data.plants || []).join(", "))}</span>` : ""}
			</div>
			<div class="tc-tiles">${(data.kpis || []).map((tile) => this.tile(tile)).join("")}</div>
			<div class="tc-box"><h6><span>${esc(__("The Nine Boxes Side by Side"))}</span>
				<span class="tc-switch"><button data-split="by_plant" class="${this.split === "by_plant" ? "tc-on" : ""}">${esc(__("Plants"))}</button><button data-split="by_department" class="${this.split === "by_department" ? "tc-on" : ""}">${esc(__("Departments"))}</button></span></h6>
				<div class="tc-groups">${(data[this.split] || []).map((group) => this.group(group)).join("")}</div>
				<div class="tc-note">${esc(__("A red border is a box more than 5 points above the guide, a dashed one more than 5 below. Hover a box for the guide and the review before."))}</div>
			</div>
			<div class="tc-two">
				<div class="tc-box"><h6><span>${esc(__("Succession: Impact by Probability of Loss"))}</span></h6>${this.heat()}</div>
				<div class="tc-box"><h6><span>${esc(__("Roles Most at Risk"))}</span></h6>${this.roles()}</div>
			</div>
			<div class="tc-two">
				<div class="tc-box"><h6><span>${esc(__("Top Talent"))}</span></h6>${this.people(data.top || [], false)}</div>
				<div class="tc-box"><h6><span>${esc(__("Top Talent at Flight Risk"))}</span></h6>${this.people(data.risk || [], true)}</div>
			</div>
			<div class="tc-two">
				<div class="tc-box"><h6><span>${esc(__("Movement Since the Review Before"))}</span></h6>${this.matrix()}</div>
				<div class="tc-box"><h6><span>${esc(__("Successors Named for Several Roles"))}</span></h6>${this.overlap()}</div>
			</div>
			<div class="tc-box"><h6><span>${esc(__("Graduate Pipeline by Cohort"))}</span>
				<span class="tc-pill" data-invest="1" style="cursor:pointer">${esc(__("Development plans: {0} approved, {1} spent", [
					format_currency((data.investment || {}).approved || 0), format_currency((data.investment || {}).actual || 0)]))}</span></h6>
				${this.funnel()}</div>`);
		this.bind();
	}

	tile(tile) {
		const esc = frappe.utils.escape_html;
		return `<div class="tc-tile" data-tile="${esc(tile.key)}"><small>${esc(__(tile.label))}</small>
			<b style="color:${TC_TONES[tile.tone] || "inherit"}">${esc(String(tile.value))}</b><em>${esc(__(tile.note || ""))}</em></div>`;
	}

	group(group) {
		const esc = frappe.utils.escape_html;
		const boxes = {};
		(group.boxes || []).forEach((row) => (boxes[row.box] = row));
		const names = this.data.names || {};
		const colours = this.data.colours || {};
		const cells = TC_ROWS.map((line) => line.map((box) => {
			const row = boxes[box] || {};
			const tint = TC_TINTS[colours[box]] || ["var(--control-bg)", "var(--text-color)"];
			const off = row.variance === null || row.variance === undefined ? "" : row.variance > 5 ? "tc-over" : row.variance < -5 ? "tc-under" : "";
			const title = [`${box} ${names[box] || ""}`, __("{0} people, {1}%", [row.n || 0, row.share || 0]),
				row.guide !== null && row.guide !== undefined ? __("Guide {0}%", [row.guide]) : "",
				row.last_share !== null && row.last_share !== undefined ? __("Review before {0}%", [row.last_share]) : ""].filter(Boolean).join(" · ");
			return `<div class="tc-cell ${off}" data-group="${esc(group.group)}" data-box="${box}" title="${esc(title)}"
				style="background:${tint[0]};color:${tint[1]}"><b>${row.n || 0}</b><span>${row.share || 0}%</span></div>`;
		}).join("")).join("");
		return `<div class="tc-group"><h5><span>${esc(__(group.group))}</span><span class="text-muted">${group.total} · ${esc(__("top {0}%", [group.top_share]))}</span></h5>
			<div class="tc-grid">${cells}</div></div>`;
	}

	heat() {
		const esc = frappe.utils.escape_html;
		const heat = this.data.heat || { rows: [] };
		const bench = this.data.bench || {};
		const rows = (heat.rows || []).map((row, r) => `<tr><th>${esc(__(row.impact))}</th>${row.cells.map((cell, c) =>
			`<td data-heat="${r}-${c}" style="background:${TC_HEAT[r][c]}">${cell.count}</td>`).join("")}</tr>`).join("");
		return `<table class="tc-heat"><tr><th>${esc(__("Impact"))}</th><th>${esc(__("Low"))}</th><th>${esc(__("Medium"))}</th><th>${esc(__("High"))}</th></tr>${rows}
			<tr><th></th><th colspan="3">${esc(__("Probability of loss"))}</th></tr></table>
			<div class="tc-note">${esc(__("{0} critical roles: {1}% have a successor ready now, {2}% two or more named, {3} nobody. {4} not scored for impact yet.", [
				bench.roles || 0, Math.round(bench.ready_now_share || 0), Math.round(bench.two_share || 0), bench.none || 0, heat.unscored || 0]))}</div>`;
	}

	roles() {
		const esc = frappe.utils.escape_html;
		const rows = (this.data.roles || []).slice(0, 10);
		if (!rows.length) return `<div class="tc-empty">${esc(__("No critical roles yet."))}</div>`;
		return `<table class="tc-list"><tr><th>${esc(__("Role"))}</th><th>${esc(__("Holder"))}</th><th>${esc(__("Risk"))}</th><th>${esc(__("Cover"))}</th></tr>
			${rows.map((row) => `<tr class="tc-go" data-position="${esc(row.name)}"><td>${esc(row.designation || row.name)}<div class="text-muted">${esc(row.branch || "")}</div></td>
			<td>${esc(row.incumbent_name || __("Nobody"))}</td>
			<td><span class="tc-flag ${row.risk_level === "High" ? "tc-bad" : row.risk_level === "Medium" ? "tc-warn" : "tc-good"}">${row.role_risk === null || row.role_risk === undefined ? esc(__(row.risk_level || "")) : format_number(row.role_risk, null, 0)}</span></td>
			<td>${esc(__(row.coverage || ""))}</td></tr>`).join("")}</table>`;
	}

	people(rows, risk) {
		const esc = frappe.utils.escape_html;
		if (!rows.length) return `<div class="tc-empty">${esc(risk ? __("Nobody at a watched flight risk.") : __("No top talent placed yet."))}</div>`;
		return `<table class="tc-list"><tr><th>${esc(__("Name"))}</th><th>${esc(__("Plant"))}</th><th>${esc(__("Box"))}</th><th>${esc(risk ? __("Risk") : __("Performance"))}</th>${risk ? `<th>${esc(__("Actions"))}</th>` : ""}</tr>
			${rows.slice(0, 12).map((row) => `<tr class="tc-go" data-placement="${esc(row.name)}"><td>${esc(row.employee_name || row.employee)}<div class="text-muted">${esc(row.designation || "")}</div></td>
			<td>${esc(row.branch || "")}</td><td>${row.box || ""} ${esc(__(row.box_name || ""))}</td>
			<td>${risk ? `<span class="tc-flag ${row.flight_risk === "High" ? "tc-bad" : "tc-warn"}">${esc(__(row.flight_risk || ""))}</span>` : format_number(row.performance_score || 0, null, 0)}</td>
			${risk ? `<td>${row.actions ? row.actions : `<span class="tc-flag tc-bad">${esc(__("None"))}</span>`}</td>` : ""}</tr>`).join("")}</table>`;
	}

	matrix() {
		const esc = frappe.utils.escape_html;
		if (!this.data.before) return `<div class="tc-empty">${esc(__("There is no earlier review to compare with."))}</div>`;
		const head = `<tr><th>${esc(__("From"))}</th>${[1, 2, 3, 4, 5, 6, 7, 8, 9].map((box) => `<th>${box}</th>`).join("")}<th>${esc(__("Left"))}</th></tr>`;
		const rows = (this.data.matrix || []).map((row) => `<tr><th>${esc(row.from ? String(row.from) : __("New"))}</th>${row.cells.map((n, index) =>
			`<td class="${n ? "tc-n" : ""} ${row.from === index + 1 ? "tc-same" : ""}" data-from="${row.from}" data-to="${index + 1}">${n || ""}</td>`).join("")}
			<td class="${row.gone ? "tc-n" : ""}" data-from="${row.from}" data-to="0">${row.gone || ""}</td></tr>`).join("");
		const moved = this.data.movement || {};
		return `<table class="tc-matrix">${head}${rows}</table><div class="tc-note">${esc(__("Stayed {0}, up {1}, down {2}, across {3}, new {4}, left {5}.", [
			moved.same || 0, moved.up || 0, moved.down || 0, moved.across || 0, moved.new || 0, moved.gone || 0]))}</div>`;
	}

	overlap() {
		const esc = frappe.utils.escape_html;
		const rows = this.data.overlap || [];
		if (!rows.length) return `<div class="tc-empty">${esc(__("Nobody is named for more than one role."))}</div>`;
		return `<table class="tc-list"><tr><th>${esc(__("Successor"))}</th><th>${esc(__("Named For"))}</th></tr>
			${rows.map((row) => `<tr class="tc-go" data-employee="${esc(row.employee)}"><td>${esc(row.employee_name || row.employee)}</td><td>${esc(row.roles.join(", "))}</td></tr>`).join("")}</table>`;
	}

	funnel() {
		const esc = frappe.utils.escape_html;
		const rows = this.data.funnel || [];
		if (!rows.length) return `<div class="tc-empty">${esc(__("No graduate trainees yet."))}</div>`;
		return `<table class="tc-list"><tr><th>${esc(__("Cohort"))}</th><th>${esc(__("Trainees"))}</th>${TC_STAGES.map((stage) => `<th>${esc(__(stage))}</th>`).join("")}<th>${esc(__("Confirmed %"))}</th></tr>
			${rows.map((row) => `<tr><td>${esc(row.cohort)}</td><td>${row.total}</td>${TC_STAGES.map((stage) =>
				`<td class="${row.stages[stage] ? "tc-n" : ""}" data-cohort="${esc(row.cohort)}" data-stage="${esc(stage)}" style="${row.stages[stage] ? "cursor:pointer;font-weight:600" : ""}">${row.stages[stage] || ""}</td>`).join("")}
				<td>${row.confirmed_share}%</td></tr>`).join("")}</table>`;
	}

	bind() {
		const data = this.data;
		const review = data.review.name;
		const field = this.split === "by_plant" ? "branch" : "department";
		this.body.find("[data-split]").on("click", (event) => {
			this.split = $(event.currentTarget).attr("data-split");
			this.render();
		});
		this.body.find(".tc-cell").on("click", (event) => {
			const cell = $(event.currentTarget);
			const filters = { talent_review: review, box: parseInt(cell.attr("data-box"), 10) };
			if (cell.attr("data-group") !== "Company") filters[field] = cell.attr("data-group");
			this.go("Talent Placement", filters);
		});
		const routes = {
			placed: () => this.go("Talent Placement", { talent_review: review }),
			top: () => this.go("Talent Placement", { talent_review: review, top_talent: 1 }),
			at_risk: () => this.report("Top Talent and Flight Risk", { talent_review: review }),
			bench: () => this.report("Succession Coverage", {}),
			depth: () => this.report("Succession Coverage", {}),
			high_risk: () => this.go("Succession Position", { risk_level: "High" }),
			overlap: () => this.report("Succession Coverage", {}),
			trainees: () => this.report("Graduate Trainee Progress", {}),
		};
		this.body.find("[data-tile]").on("click", (event) => {
			const go = routes[$(event.currentTarget).attr("data-tile")];
			if (go) go();
		});
		this.body.find("[data-heat]").on("click", (event) => {
			const [r, c] = $(event.currentTarget).attr("data-heat").split("-").map((n) => parseInt(n, 10));
			const roles = ((((data.heat || {}).rows || [])[r] || {}).cells || [])[c] || {};
			if ((roles.roles || []).length) this.go("Succession Position", { name: ["in", roles.roles] });
		});
		this.body.find("[data-position]").on("click", (event) =>
			frappe.set_route("Form", "Succession Position", $(event.currentTarget).attr("data-position")));
		this.body.find("[data-placement]").on("click", (event) =>
			frappe.set_route("Form", "Talent Placement", $(event.currentTarget).attr("data-placement")));
		this.body.find("[data-employee]").on("click", (event) => {
			const row = (data.overlap || []).find((item) => item.employee === $(event.currentTarget).attr("data-employee"));
			if (row) this.go("Succession Position", { designation: ["in", row.roles] });
		});
		this.body.find("td.tc-n[data-from]").on("click", (event) => {
			const cell = $(event.currentTarget);
			const filters = { talent_review: review, compared_with: data.before };
			const from = parseInt(cell.attr("data-from"), 10);
			const to = parseInt(cell.attr("data-to"), 10);
			filters.from_box = from;
			filters.to_box = to;
			this.report("Talent Movement", filters);
		});
		this.body.find("td.tc-n[data-cohort]").on("click", (event) => {
			const cell = $(event.currentTarget);
			this.go("Graduate Trainee Program", { cohort: cell.attr("data-cohort"), workflow_state: cell.attr("data-stage") });
		});
		this.body.find("[data-invest]").on("click", () => this.report("Development Plan Tracker", {}));
	}
};
