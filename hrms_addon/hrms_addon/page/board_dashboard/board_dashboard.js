// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

/* The Board Dashboard (board_dashboard.py).
 *
 * The quarter's figures as the board reads them: a card per KPI with its
 * traffic light, its change on the quarter before and the eight quarters
 * behind it; the plants' scorecard; and what keeps the figures from adding
 * up. Every figure opens the report listing its records. The server decides
 * what the person looking may see; this script draws what it is given.
 * The styles live in this file, so the page never waits on `bench build`.
 */

frappe.provide("hrms_addon");

const HRA_BD_STYLE = `
.hra-bd { display: grid; gap: 14px; padding-bottom: 24px; }
.hra-bd-band { border: 1px solid var(--hra-border, #C3D0E0); border-radius: 8px; background: var(--card-bg, #fff);
  overflow: hidden; }
.hra-bd-head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; padding: 9px 14px;
  background: var(--hra-primary, #0A2540); }
.hra-bd-head h4 { margin: 0; font-size: 13px; letter-spacing: .04em; text-transform: uppercase; color: #fff; }
.hra-bd-head span { font-size: 12px; color: rgba(255,255,255,.72); }
.hra-bd-body { padding: 14px; }
.hra-bd-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 10px; }
.hra-bd-card { border: 1px solid var(--hra-border, #C3D0E0); border-radius: 8px; padding: 10px 12px;
  background: var(--hra-pale, #EEF3F9); cursor: pointer; position: relative; }
.hra-bd-card.hra-bd-off { cursor: default; }
.hra-bd-card small { display: block; color: var(--text-muted, #5B6B7F); font-size: 11.5px; padding-right: 16px; }
.hra-bd-card b { display: block; font-size: 22px; line-height: 1.25; color: var(--hra-primary, #0A2540); }
.hra-bd-card em { font-style: normal; font-size: 12px; }
.hra-bd-card svg { display: block; margin-top: 6px; }
.hra-bd-light { position: absolute; top: 10px; right: 10px; width: 11px; height: 11px; border-radius: 50%;
  background: #D1D5DB; }
.hra-bd-on-track { background: #1F7A4D; }
.hra-bd-watch { background: #B7791F; }
.hra-bd-action-needed { background: #A62B25; }
.hra-bd-good { color: #1F7A4D; }
.hra-bd-bad { color: #A62B25; }
.hra-bd-flat { color: var(--text-muted, #5B6B7F); }
.hra-bd-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.hra-bd-table th { text-align: left; font-weight: 600; color: var(--text-muted, #5B6B7F); padding: 5px 8px;
  border-bottom: 1px solid var(--hra-border, #C3D0E0); }
.hra-bd-table td { padding: 6px 8px; border-bottom: 1px solid var(--hra-readonly, #EDF1F7); }
.hra-bd-table td[data-route] { cursor: pointer; }
.hra-bd-cell { display: inline-flex; align-items: center; gap: 6px; }
.hra-bd-cell i { width: 9px; height: 9px; border-radius: 50%; display: inline-block; background: #D1D5DB; }
.hra-bd-quality { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
.hra-bd-issue { border: 1px solid var(--hra-border, #C3D0E0); border-radius: 8px; padding: 10px 12px; cursor: pointer; }
.hra-bd-issue b { display: block; font-size: 20px; }
.hra-bd-issue.hra-bd-none b { color: #1F7A4D; }
.hra-bd-issue.hra-bd-some b { color: #A62B25; }
.hra-bd-note { color: var(--text-muted, #5B6B7F); font-size: 12px; margin: 0; }
.hra-bd-missing { color: #A62B25; font-size: 12.5px; margin: 0; }
`;
const HRA_BD_LIGHTS = { "On Track": "hra-bd-on-track", Watch: "hra-bd-watch", "Action Needed": "hra-bd-action-needed" };
const HRA_BD_COLOURS = { "On Track": "#1F7A4D", Watch: "#B7791F", "Action Needed": "#A62B25" };

frappe.pages["board-dashboard"].on_page_load = function (wrapper) {
	if (!document.getElementById("hra-board-style")) {
		const sheet = document.createElement("style");
		sheet.id = "hra-board-style";
		sheet.textContent = HRA_BD_STYLE;
		document.head.appendChild(sheet);
	}
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Board Dashboard"), single_column: true });
	wrapper.board = new hrms_addon.BoardDashboard(page);
};

frappe.pages["board-dashboard"].on_page_show = function (wrapper) {
	if (wrapper.board) wrapper.board.refresh();
};

hrms_addon.BoardDashboard = class BoardDashboard {
	constructor(page) {
		this.page = page;
		this.make_filters();
		this.body = $('<div class="hra-bd"></div>').appendTo(this.page.main);
		this.refresh();
	}

	make_filters() {
		const now = new Date();
		const year = now.getFullYear();
		this.company = this.page.add_field({
			fieldtype: "Link", label: __("Company"), fieldname: "company", options: "Company",
			default: frappe.defaults.get_user_default("Company"), change: () => this.refresh(),
		});
		this.year = this.page.add_field({
			fieldtype: "Select", label: __("Year"), fieldname: "year",
			options: [year, year - 1, year - 2].map(String), default: String(year), change: () => this.refresh(),
		});
		this.quarter = this.page.add_field({
			fieldtype: "Select", label: __("Quarter"), fieldname: "quarter", options: ["Q1", "Q2", "Q3", "Q4"],
			default: "Q" + (Math.floor(now.getMonth() / 3) + 1), change: () => this.refresh(),
		});
		this.branch = this.page.add_field({
			fieldtype: "Link", label: __("Plant"), fieldname: "branch", options: "Branch", change: () => this.refresh(),
		});
		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
	}

	asked() {
		return {
			company: this.company.get_value() || "",
			year: this.year.get_value() || "",
			quarter: this.quarter.get_value() || "",
			branch: this.branch.get_value() || "",
		};
	}

	refresh() {
		if (this.asking) return;
		this.asking = true;
		const asked = this.asked();
		Object.keys(asked).forEach((key) => !asked[key] && delete asked[key]);
		frappe
			.xcall("hrms_addon.hrms_addon.board_dashboard.overview", asked)
			.then((found) => this.draw(found))
			.finally(() => {
				this.asking = false;
			});
	}

	band(title, subtitle) {
		const esc = frappe.utils.escape_html;
		return $(`<section class="hra-bd-band"><header class="hra-bd-head"><h4>${esc(title)}</h4>
			<span>${subtitle ? esc(subtitle) : ""}</span></header><div class="hra-bd-body"></div></section>`)
			.appendTo(this.body)
			.find(".hra-bd-body");
	}

	open(route) {
		if (route) frappe.set_route(route[0], route[1], route[2] || {});
	}

	draw(found) {
		this.found = found;
		this.body.empty();
		if (found.missing && found.missing.length) {
			this.body.append(
				`<p class="hra-bd-missing">${__("Not built yet: {0}. Build them in HR Monthly Snapshot.", [
					frappe.utils.escape_html(found.missing.join(", ")),
				])}</p>`
			);
		}
		this.cards(found);
		this.scorecard(found);
		this.quality(found);
		this.body.find("[data-route]").on("click", (event) => {
			const index = $(event.currentTarget).attr("data-route");
			this.open(this.routes[index]);
		});
	}

	route(route) {
		this.routes = this.routes || [];
		if (!route) return "";
		this.routes.push(route);
		return ` data-route="${this.routes.length - 1}"`;
	}

	cards(found) {
		const esc = frappe.utils.escape_html;
		const body = this.band(__("The Quarter"), `${found.label}${found.branch ? " · " + found.branch : ""}`);
		const grid = $('<div class="hra-bd-cards"></div>').appendTo(body);
		this.routes = [];
		(found.cards || []).forEach((card) => {
			const moved = this.moved(card);
			grid.append(`
				<div class="hra-bd-card${card.route ? "" : " hra-bd-off"}"${this.route(card.route)}>
					<span class="hra-bd-light ${HRA_BD_LIGHTS[card.light] || ""}" title="${esc(card.light || "")}"></span>
					<small>${esc(__(card.metric))}</small>
					<b>${esc(card.display)}</b>
					<em class="${moved.css}">${esc(moved.text)}</em>
					${this.sparkline(card.series, found.quarters)}
				</div>`);
		});
	}

	moved(card) {
		if (card.change === null || card.change === undefined) return { text: __("No quarter before"), css: "hra-bd-flat" };
		const up = card.change > 0;
		const good = card.direction ? (card.direction === "Lower is Better" ? !up : up) : null;
		const css = card.change === 0 || good === null ? "hra-bd-flat" : good ? "hra-bd-good" : "hra-bd-bad";
		return { text: `${up ? "▲" : card.change < 0 ? "▼" : "—"} ${Math.abs(card.change).toFixed(1)}% ${__("on the quarter")}`, css };
	}

	sparkline(series, labels) {
		const values = (series || []).map((value) => (value === null || value === undefined ? null : Number(value)));
		const known = values.filter((value) => value !== null);
		if (known.length < 2) return "";
		const width = 180, height = 34, low = Math.min(...known), high = Math.max(...known);
		const span = high - low || 1;
		const step = width / (values.length - 1);
		const points = values
			.map((value, index) => (value === null ? null : [index * step, height - 3 - ((value - low) / span) * (height - 6)]))
			.filter(Boolean);
		const path = points.map((point, index) => `${index ? "L" : "M"}${point[0].toFixed(1)},${point[1].toFixed(1)}`).join(" ");
		const last = points[points.length - 1];
		const title = frappe.utils.escape_html((labels || []).map((label, index) => `${label}: ${values[index] === null ? "–" : values[index]}`).join("  "));
		return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><title>${title}</title>
			<path d="${path}" fill="none" stroke="#3B78B5" stroke-width="1.6"/>
			<circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2.6" fill="#0A2540"/></svg>`;
	}

	scorecard(found) {
		const esc = frappe.utils.escape_html;
		const card = found.scorecard || {};
		if (!(card.rows || []).length) return;
		const body = this.band(__("The Plants' Scorecard"), __("Against each plant's target, else against the company"));
		const head = `<tr><th>${__("Plant")}</th>${(card.metrics || []).map((metric) => `<th>${esc(__(metric))}</th>`).join("")}</tr>`;
		const rows = card.rows
			.map(
				(row) => `<tr><td><b>${esc(row.plant)}</b></td>${row.cells
					.map(
						(cell) => `<td${this.route(cell.route)}><span class="hra-bd-cell"><i style="background:${
							HRA_BD_COLOURS[cell.light] || "#D1D5DB"
						}"></i>${esc(cell.display)}</span></td>`
					)
					.join("")}</tr>`
			)
			.join("");
		body.append(`<table class="hra-bd-table"><thead>${head}</thead><tbody>${rows}</tbody></table>`);
	}

	quality(found) {
		const esc = frappe.utils.escape_html;
		const body = this.band(__("Data Quality"), found.issues ? __("{0} to put right", [found.issues]) : __("Nothing to put right"));
		const grid = $('<div class="hra-bd-quality"></div>').appendTo(body);
		(found.quality || []).forEach((row) => {
			grid.append(`<div class="hra-bd-issue ${row.count ? "hra-bd-some" : "hra-bd-none"}"${this.route(row.route)}>
				<b>${esc(String(row.count))}</b><small>${esc(__(row.label))}</small></div>`);
		});
		body.append(`<p class="hra-bd-note">${__("As of {0}", [esc(frappe.datetime.str_to_user(found.today))])}</p>`);
	}
};
