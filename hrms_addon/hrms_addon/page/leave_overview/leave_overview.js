// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

/* The Leave Overview.
 *
 * Four questions, one row each (leave_overview_rules.py says why):
 *
 *   1  Who is away, and are we covered?
 *   2  What is stuck?
 *   3  What will the year end cost?     (management)
 *   4  Is there a pattern?              (the sick-leave list: HR)
 *
 * Every figure opens the list behind it. The server decides whose leave
 * the person looking may see (leave_overview.py); this script draws what
 * it is given and asks for nothing else.
 */

frappe.provide("hrms_addon");

// The page's own styles, served with the page: a bundle only reaches the
// browser after `bench build`. Every var() carries the colour it falls
// back to, so a theme that does not declare one costs a colour and not
// the layout.
const HRA_LEAVE_STYLE = `
.hra-leave { display: grid; gap: 12px; padding-bottom: 24px; }
.hra-lv-band { border: 1px solid var(--hra-border, #C3D0E0); border-radius: 8px;
  background: var(--card-bg, #fff); overflow: hidden; }
.hra-lv-head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px;
  padding: 9px 14px; background: var(--hra-primary, #0A2540); }
.hra-lv-head h4 { margin: 0; font-size: 13px; letter-spacing: .04em; text-transform: uppercase; color: #fff; }
.hra-lv-head span { font-size: 12px; color: rgba(255,255,255,.72); }
.hra-lv-body { padding: 14px; display: grid; gap: 14px; }
.hra-lv-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.hra-lv-tile { border: 1px solid var(--hra-border, #C3D0E0); border-radius: 8px; padding: 10px 12px;
  background: var(--hra-pale, #EEF3F9); cursor: pointer; }
.hra-lv-tile b { display: block; font-size: 22px; line-height: 1.2; color: var(--hra-primary, #0A2540); }
.hra-lv-tile small { color: var(--text-muted, #5B6B7F); }
.hra-lv-tile.hra-lv-warn b { color: var(--hra-danger, #A62B25); }
.hra-lv-cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
.hra-lv-cols h5 { margin: 0 0 6px; font-size: 12.5px; font-weight: 600; }
.hra-lv-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.hra-lv-table th { text-align: left; font-weight: 600; color: var(--text-muted, #5B6B7F); padding: 4px 8px;
  border-bottom: 1px solid var(--hra-border, #C3D0E0); }
.hra-lv-table td { padding: 5px 8px; border-bottom: 1px solid var(--hra-readonly, #EDF1F7); }
.hra-lv-table tr[data-open] { cursor: pointer; }
.hra-lv-table .hra-lv-num { text-align: right; }
.hra-lv-table tr.hra-lv-over td { color: var(--hra-danger, #A62B25); font-weight: 600; }
.hra-lv-months { display: grid; grid-template-columns: repeat(12, 1fr); gap: 6px; height: 170px; }
.hra-lv-month { display: flex; flex-direction: column; justify-content: flex-end; cursor: pointer; }
.hra-lv-month em { text-align: center; font-size: 11px; font-style: normal; color: var(--text-muted, #5B6B7F); }
.hra-lv-bar { display: flex; flex-direction: column-reverse; border-radius: 4px 4px 0 0; overflow: hidden; }
.hra-lv-month span { text-align: center; font-size: 11px; padding-top: 3px;
  border-top: 1px solid var(--hra-border, #C3D0E0); }
.hra-lv-legend { display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; }
.hra-lv-legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; }
.hra-lv-empty { color: var(--text-muted, #5B6B7F); font-size: 12.5px; margin: 0; }
.hra-lv-foot { color: var(--text-muted, #5B6B7F); font-size: 12px; }
`;

// one colour a leave type, in the order the types are first met
const HRA_LEAVE_COLOURS = ["#0A2540", "#3B78B5", "#A9791C", "#7A8CA3", "#A62B25", "#5E8C61", "#C9A227", "#4B5563"];
const HRA_LEAVE_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const HRA_LEAVE_PENDING = ["Pending Supervisor", "Pending HOD", "Pending HR Officer"];

frappe.pages["leave-overview"].on_page_load = function (wrapper) {
	if (!document.getElementById("hra-leave-style")) {
		const sheet = document.createElement("style");
		sheet.id = "hra-leave-style";
		sheet.textContent = HRA_LEAVE_STYLE;
		document.head.appendChild(sheet);
	}
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Leave Overview"),
		single_column: true,
	});
	wrapper.overview = new hrms_addon.LeaveOverview(page);
};

frappe.pages["leave-overview"].on_page_show = function (wrapper) {
	if (wrapper.overview) wrapper.overview.refresh();
};

hrms_addon.LeaveOverview = class LeaveOverview {
	constructor(page) {
		this.page = page;
		this.make_filters();
		this.body = $('<div class="hra-leave"></div>').appendTo(this.page.main);
		this.refresh();
	}

	make_filters() {
		const year = new Date().getFullYear();
		this.year = this.page.add_field({
			fieldtype: "Select",
			label: __("Year"),
			fieldname: "year",
			options: [year + 1, year, year - 1, year - 2].map(String),
			default: String(year),
			change: () => this.refresh(),
		});
		this.branch = this.page.add_field({
			fieldtype: "Link",
			label: __("Plant"),
			fieldname: "branch",
			options: "Branch",
			change: () => this.refresh(),
		});
		this.department = this.page.add_field({
			fieldtype: "Link",
			label: __("Department"),
			fieldname: "department",
			options: "Department",
			change: () => this.refresh(),
		});
		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
	}

	asked() {
		return {
			year: (this.year && this.year.get_value()) || String(new Date().getFullYear()),
			branch: (this.branch && this.branch.get_value()) || "",
			department: (this.department && this.department.get_value()) || "",
		};
	}

	refresh() {
		if (this.asking) return;
		this.asking = true;
		const asked = this.asked();
		frappe
			.xcall("hrms_addon.hrms_addon.leave_overview.overview", asked)
			.then((found) => {
				this.draw(found);
				// what leave is worth takes longer, and is not everybody's
				if (found.sees.money) {
					frappe
						.xcall("hrms_addon.hrms_addon.leave_overview.year_end", asked)
						.then((cost) => this.year_end(found, cost));
				}
			})
			.finally(() => {
				this.asking = false;
			});
	}

	// ── drawing ───────────────────────────────────────────────────
	draw(found) {
		this.found = found;
		this.body.empty();
		this.away(found);
		this.stuck(found);
		if (found.sees.money) this.cost_band = this.band(__("What the year end will cost"), __("Working it out"));
		this.pattern(found);
		this.body.append(
			`<div class="hra-lv-foot">${__("{0} people in view, as of {1}", [
				found.people,
				frappe.datetime.str_to_user(found.today),
			])}</div>`
		);
		this.body.find("[data-open]").on("click", (event) => {
			const row = $(event.currentTarget);
			frappe.set_route("Form", row.attr("data-doctype") || "Leave Application", row.attr("data-open"));
		});
	}

	band(title, subtitle) {
		return $(`
			<section class="hra-lv-band">
				<header class="hra-lv-head">
					<h4>${frappe.utils.escape_html(title)}</h4>
					<span>${subtitle ? frappe.utils.escape_html(subtitle) : ""}</span>
				</header>
				<div class="hra-lv-body"></div>
			</section>
		`).appendTo(this.body);
	}

	tile(figure, label, warn) {
		return `<div class="hra-lv-tile${warn ? " hra-lv-warn" : ""}"><b>${frappe.utils.escape_html(
			String(figure)
		)}</b><small>${frappe.utils.escape_html(label)}</small></div>`;
	}

	// the leave list behind a figure, held to what the page is filtered to
	leaves(filters) {
		const asked = this.asked();
		if (asked.department) filters.department = asked.department;
		if (asked.branch) filters.custom_branch = asked.branch;
		frappe.set_route("List", "Leave Application", filters);
	}

	day(value) {
		return value ? frappe.utils.escape_html(frappe.datetime.str_to_user(value)) : "";
	}

	// 1. who is away, and are we covered
	away(found) {
		const esc = frappe.utils.escape_html;
		const band = this.band(
			__("Who is away, and are we covered"),
			found.cover.limit
				? __("At most {0} of a department off at once", [found.cover.limit])
				: __("No limit set")
		);
		const today = found.today;
		const soon = frappe.datetime.add_days(today, found.away.soon_days);
		const short = found.cover.departments.filter((row) => row.over).length;
		const people = (rows) =>
			rows.length
				? `<table class="hra-lv-table"><thead><tr><th>${__("Name")}</th><th>${__("Department")}</th>
					<th>${__("From")}</th><th>${__("Back On")}</th><th>${__("Reliever")}</th></tr></thead><tbody>${rows
						.map(
							(row) =>
								`<tr data-open="${esc(row.name)}"><td>${esc(row.employee_name || row.employee)}${
									row.leave_type ? ` <small class="text-muted">${esc(__(row.leave_type))}</small>` : ""
								}</td><td>${esc(row.department || "")}</td><td>${this.day(row.from_date)}</td><td>${this.day(
									row.back_on
								)}</td><td>${esc(row.reliever || "")}</td></tr>`
						)
						.join("")}</tbody></table>`
				: `<p class="hra-lv-empty">${__("Nobody.")}</p>`;
		const departments = found.cover.departments.length
			? `<table class="hra-lv-table"><thead><tr><th>${__("Department")}</th>
				<th class="hra-lv-num">${__("People")}</th><th class="hra-lv-num">${__("Off Today")}</th>
				<th class="hra-lv-num">${__("Most Off, Next {0} Days", [found.cover.days])}</th><th>${__("On")}</th>
				</tr></thead><tbody>${found.cover.departments
					.map(
						(row) =>
							`<tr class="${row.over ? "hra-lv-over" : ""}" data-department="${esc(row.department)}">
							<td>${esc(row.department || __("No department"))}</td><td class="hra-lv-num">${row.people}</td>
							<td class="hra-lv-num">${row.off_today}</td><td class="hra-lv-num">${row.peak}</td>
							<td>${this.day(row.peak_on)}</td></tr>`
					)
					.join("")}</tbody></table>`
			: `<p class="hra-lv-empty">${__("Nobody in view.")}</p>`;
		band.find(".hra-lv-body").html(`
			<div class="hra-lv-tiles">
				<div data-tile="today">${this.tile(found.away.today_count, __("On leave today"))}</div>
				<div data-tile="soon">${this.tile(found.away.soon_count, __("Starting this week"))}</div>
				<div data-tile="short">${this.tile(short, __("Departments over the limit"), short > 0)}</div>
			</div>
			<div class="hra-lv-cols">
				<div><h5>${__("On leave today")}</h5>${people(found.away.today)}
					<h5 style="margin-top:12px">${__("Starting this week")}</h5>${people(found.away.soon)}</div>
				<div><h5>${__("Cover by department")}</h5>${departments}</div>
			</div>
		`);
		const approved = { docstatus: 1, status: "Approved" };
		band.find('[data-tile="today"]').on("click", () =>
			this.leaves(Object.assign({ from_date: ["<=", today], to_date: [">=", today] }, approved))
		);
		band.find('[data-tile="soon"]').on("click", () =>
			this.leaves(
				Object.assign({ from_date: ["between", [frappe.datetime.add_days(today, 1), soon]] }, approved)
			)
		);
		band.find("[data-department]").css("cursor", "pointer").on("click", (event) =>
			frappe.set_route(
				"List",
				"Leave Application",
				Object.assign(
					{
						department: $(event.currentTarget).attr("data-department"),
						from_date: ["<=", frappe.datetime.add_days(today, found.cover.days)],
						to_date: [">=", today],
					},
					approved
				)
			)
		);
	}

	// 2. what is stuck
	stuck(found) {
		const esc = frappe.utils.escape_html;
		const stuck = found.stuck;
		const band = this.band(__("What is stuck"), __("Leave waiting on a desk, and people not back"));
		const waiting = stuck.waiting.length
			? `<table class="hra-lv-table"><thead><tr><th>${__("Name")}</th><th>${__("Leave")}</th>
				<th>${__("Waiting For")}</th><th class="hra-lv-num">${__("Days")}</th></tr></thead><tbody>${stuck.waiting
					.map(
						(row) =>
							`<tr data-open="${esc(row.name)}" class="${row.custom_chased === "Escalated" ? "hra-lv-over" : ""}">
							<td>${esc(row.employee_name || row.employee)}</td>
							<td>${this.day(row.from_date)} ${__("to")} ${this.day(row.to_date)}</td>
							<td>${esc(row.desk)}</td><td class="hra-lv-num">${row.days}</td></tr>`
					)
					.join("")}</tbody></table>`
			: `<p class="hra-lv-empty">${__("Nothing is waiting.")}</p>`;
		const changes = stuck.changes.length
			? `<h5 style="margin-top:12px">${__("Plan changes waiting")}</h5><table class="hra-lv-table"><tbody>${stuck.changes
					.map(
						(row) =>
							`<tr data-open="${esc(row.name)}" data-doctype="Leave Plan Change"><td>${esc(
								row.employee_name || row.employee
							)}</td><td>${esc(__(row.state))}</td><td class="hra-lv-num">${row.days}</td></tr>`
					)
					.join("")}</tbody></table>`
			: "";
		const back = stuck.not_back.length
			? `<table class="hra-lv-table"><thead><tr><th>${__("Name")}</th><th>${__("Leave Ended")}</th>
				<th class="hra-lv-num">${__("Days Overdue")}</th></tr></thead><tbody>${stuck.not_back
					.map(
						(row) =>
							`<tr data-open="${esc(row.name)}" class="${row.overdue ? "hra-lv-over" : ""}">
							<td>${esc(row.employee_name || row.employee)}</td><td>${this.day(row.to_date)}</td>
							<td class="hra-lv-num">${row.overdue || ""}</td></tr>`
					)
					.join("")}</tbody></table>`
			: `<p class="hra-lv-empty">${__("Everybody is back.")}</p>`;
		band.find(".hra-lv-body").html(`
			<div class="hra-lv-tiles">
				<div data-tile="waiting">${this.tile(stuck.waiting_count, __("Leave waiting"))}</div>
				<div data-tile="waiting">${this.tile(stuck.longest, __("Longest wait, days"), stuck.longest > 3)}</div>
				<div data-tile="changes">${this.tile(stuck.changes_count, __("Plan changes waiting"))}</div>
				<div data-tile="back">${this.tile(stuck.not_back_count, __("Not marked back"))}</div>
				<div data-tile="back">${this.tile(stuck.overdue_count, __("Overdue"), stuck.overdue_count > 0)}</div>
			</div>
			<div class="hra-lv-cols">
				<div><h5>${__("Leave waiting")}</h5>${waiting}${changes}</div>
				<div><h5>${__("Not back from leave")}</h5>${back}</div>
			</div>
		`);
		band.find('[data-tile="waiting"]').on("click", () =>
			this.leaves({ docstatus: 0, workflow_state: ["in", HRA_LEAVE_PENDING] })
		);
		band.find('[data-tile="changes"]').on("click", () =>
			frappe.set_route("List", "Leave Plan Change", { docstatus: 0 })
		);
		band.find('[data-tile="back"]').on("click", () =>
			this.leaves({
				docstatus: 1,
				status: "Approved",
				custom_reported_back: 0,
				to_date: ["<", found.today],
			})
		);
	}

	// 3. what the year end will cost, when it has been worked out
	year_end(found, cost) {
		if (!this.cost_band || this.found !== found) return;
		const kept = found.plan_kept;
		this.cost_band
			.find(".hra-lv-head span")
			.text(
				__("{0}, as of {1}. A day is the monthly gross over {2}.", [
					__(cost.leave_type),
					frappe.datetime.str_to_user(cost.as_of),
					cost.working_days,
				])
			);
		this.cost_band.find(".hra-lv-body").html(`
			<div class="hra-lv-tiles">
				<div data-tile="accrual">${this.tile(cost.earned, __("Days earned and not taken"))}</div>
				<div data-tile="accrual">${this.tile(format_currency(cost.value), __("What they are worth"))}</div>
				<div data-tile="accrual">${this.tile(
					cost.at_risk,
					__("Days the year end would lose"),
					cost.at_risk > 0
				)}</div>
				<div data-tile="plan">${this.tile(
					kept === null || kept === undefined ? "–" : `${Math.round(kept * 100)}%`,
					__("Of the plan kept to")
				)}</div>
			</div>
			${
				cost.unpriced
					? `<p class="hra-lv-empty">${__("{0} with leave earned have no salary on record, and are not priced.", [
							cost.unpriced,
					  ])}</p>`
					: ""
			}
		`);
		this.cost_band.find('[data-tile="accrual"]').on("click", () =>
			frappe.set_route("query-report", "Leave Accrual")
		);
		this.cost_band.find('[data-tile="plan"]').on("click", () =>
			frappe.set_route("query-report", "Leave Plan Adherence")
		);
	}

	// 4. is there a pattern
	pattern(found) {
		const esc = frappe.utils.escape_html;
		const band = this.band(__("Is there a pattern"), __("Leave days taken in {0}", [found.year]));
		const kinds = [];
		found.months.forEach((month) =>
			Object.keys(month.days).forEach((kind) => {
				if (!kinds.includes(kind)) kinds.push(kind);
			})
		);
		const colour = (kind) => HRA_LEAVE_COLOURS[kinds.indexOf(kind) % HRA_LEAVE_COLOURS.length];
		const most = Math.max(1, ...found.months.map((month) => month.total));
		const bars = found.months
			.map(
				(month) =>
					`<div class="hra-lv-month" data-month="${month.month}"><em>${
						month.total ? Math.round(month.total * 10) / 10 : ""
					}</em><div class="hra-lv-bar" style="height:${Math.round((month.total / most) * 120)}px">${kinds
						.map((kind) =>
							month.days[kind]
								? `<i style="flex:${month.days[kind]};background:${colour(kind)}" title="${esc(
										__(kind)
								  )}: ${month.days[kind]}"></i>`
								: ""
						)
						.join("")}</div><span>${__(HRA_LEAVE_MONTHS[month.month - 1])}</span></div>`
			)
			.join("");
		const legend = kinds
			.map((kind) => `<span><i style="background:${colour(kind)}"></i>${esc(__(kind))}</span>`)
			.join("");
		const sick =
			found.sick === null || found.sick === undefined
				? ""
				: `<div><h5>${__("Sick leave worth a conversation")}</h5>${
						found.sick.length
							? `<table class="hra-lv-table"><thead><tr><th>${__("Name")}</th><th>${__("Department")}</th>
								<th class="hra-lv-num">${__("Spells")}</th><th class="hra-lv-num">${__("Days")}</th>
								<th class="hra-lv-num">${__("Beside the Rest Day")}</th></tr></thead><tbody>${found.sick
									.map(
										(row) =>
											`<tr data-employee="${esc(row.employee)}"><td>${esc(row.employee_name)}</td>
											<td>${esc(row.department || "")}</td><td class="hra-lv-num">${row.spells}</td>
											<td class="hra-lv-num">${row.days}</td><td class="hra-lv-num">${row.beside_rest}</td></tr>`
									)
									.join("")}</tbody></table>`
							: `<p class="hra-lv-empty">${__("Nothing stands out.")}</p>`
				  }</div>`;
		band.find(".hra-lv-body").html(`
			<div class="hra-lv-cols">
				<div><div class="hra-lv-months">${bars}</div><div class="hra-lv-legend" style="margin-top:8px">${legend}</div></div>
				${sick}
			</div>
		`);
		band.find("[data-month]").on("click", (event) => {
			const month = parseInt($(event.currentTarget).attr("data-month"), 10);
			const stem = `${found.year}-${String(month).padStart(2, "0")}`;
			// day 0 of the month after is the last day of this one
			const last = `${stem}-${String(new Date(found.year, month, 0).getDate()).padStart(2, "0")}`;
			this.leaves({
				docstatus: 1,
				status: "Approved",
				from_date: ["<=", last],
				to_date: [">=", `${stem}-01`],
			});
		});
		band.find("[data-employee]").css("cursor", "pointer").on("click", (event) =>
			frappe.set_route("List", "Leave Application", {
				employee: $(event.currentTarget).attr("data-employee"),
				leave_type: ["like", "%Sick%"],
				docstatus: 1,
			})
		);
	}
};
