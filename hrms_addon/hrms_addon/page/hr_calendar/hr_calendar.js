// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

/* The HR calendar.
 *
 * One month at a time. Leave is drawn as a roster: everybody down the
 * side, the days across, each cell coloured by what is true of that day
 * (approved leave, leave still applied for, leave only planned, a
 * holiday), with how many are off under each day. Training is drawn as
 * the wall calendar people are used to: the weeks down, the days across,
 * each session a chip on its day.
 *
 * One call fills it (hrms_addon.hrms_addon.calendar_board.month).
 * Everything here is a read; nothing on this page writes.
 */

frappe.provide("hrms_addon");

const HRC_MONTHS = [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
];
const HRC_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
// the letter in a leave cell
const HRC_MARKS = { approved: "L", applied: "A", planned: "P", holiday: "" };

// The page's own styles travel with it, for the reason attendance_board.js
// gives: hrms_addon.bundle.css only reaches a browser after `bench build`.
// Every --hrc-* it reads is declared here; the theme's --hra-* colours it
// borrows carry a fallback.
const HRC_STYLE = `
:root {
  --hrc-ink:          var(--hra-ink, #1A2733);
  --hrc-muted:        var(--hra-ink-muted, #546678);
  --hrc-border:       var(--hra-border, #C3D0E0);
  --hrc-border-soft:  #E3E9F1;
  --hrc-pale:         var(--hra-pale, #EEF3F9);
  --hrc-accent:       var(--hra-accent, #0A6ED1);
  --hrc-danger:       var(--hra-danger, #A62B25);
  --hrc-danger-soft:  #FBE7E6;
  --hrc-approved:     #D8EDD3;
  --hrc-approved-ink: #1E6B34;
  --hrc-applied:      #FCEBC9;
  --hrc-applied-ink:  #9A4A05;
  --hrc-planned:      #DCE9F8;
  --hrc-planned-ink:  #0B5CAD;
  --hrc-holiday:      #EDEFF2;
  --hrc-gold:         #A9791C;
  --hrc-gold-soft:    #FBF1D9;
  --hrc-cell:         30px;
}
.hrc { padding: 2px 0 24px; }
.hrc-band { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; margin: 4px 0 12px; }
.hrc-band-title { font-size: 20px; font-weight: 600; color: var(--hrc-ink); }
.hrc-band-sub { font-size: 12px; color: var(--hrc-muted); }
.hrc-legend { margin-left: auto; display: flex; gap: 10px; flex-wrap: wrap; font-size: 11px; color: var(--hrc-muted); }
.hrc-legend i { display: inline-block; width: 14px; height: 14px; border-radius: 3px; vertical-align: -3px;
                margin-right: 4px; border: 1px solid transparent; }
.hrc-legend i.hrc-approved { background: var(--hrc-approved); }
.hrc-legend i.hrc-applied { background: var(--hrc-applied); }
.hrc-legend i.hrc-planned { background: var(--hrc-planned); }
.hrc-legend i.hrc-holiday { background: var(--hrc-holiday); }
.hrc-legend i.hrc-chip-scheduled { background: var(--hrc-planned); border-left: 3px solid var(--hrc-accent); }
.hrc-legend i.hrc-chip-completed { background: var(--hrc-approved); border-left: 3px solid var(--hrc-approved-ink); }
.hrc-legend i.hrc-chip-planned { background: var(--hrc-gold-soft); border: 1px dashed var(--hrc-gold); }
.hrc-empty { padding: 28px; text-align: center; color: var(--hrc-muted); background: var(--hrc-pale);
             border-radius: 6px; margin-bottom: 12px; }
.hrc-note { font-size: 11px; color: var(--hrc-muted); margin: 8px 0 0; }

/* the roster */
.hrc-scroll { overflow: auto; max-height: 74vh; border: 1px solid var(--hrc-border); border-radius: 6px;
              background: #fff; }
.hrc-roster { border-collapse: separate; border-spacing: 0; font-size: 12px; min-width: 100%; }
.hrc-roster th, .hrc-roster td { border-bottom: 1px solid var(--hrc-border-soft);
                                 border-right: 1px solid var(--hrc-border-soft); padding: 0; text-align: center; }
.hrc-roster thead th { position: sticky; top: 0; z-index: 2; height: 42px; background: var(--hrc-pale);
                       font-weight: 500; color: var(--hrc-muted); border-bottom: 1px solid var(--hrc-border); }
.hrc-roster th.hrc-who, .hrc-roster td.hrc-who { position: sticky; left: 0; z-index: 1; background: #fff;
                                                 text-align: left; padding: 5px 10px; min-width: 200px; }
.hrc-roster thead th.hrc-who { z-index: 3; background: var(--hrc-pale); }
.hrc-day { min-width: var(--hrc-cell); width: var(--hrc-cell); }
.hrc-dow { display: block; font-size: 9px; text-transform: uppercase; letter-spacing: .3px; }
.hrc-num { display: block; font-size: 12px; color: var(--hrc-ink); }
.hrc-roster th.hrc-off, .hrc-roster td.hrc-off { background: var(--hrc-holiday); }
.hrc-roster th.hrc-today { box-shadow: inset 0 -3px 0 var(--hrc-accent); }
.hrc-name { display: block; font-weight: 500; color: var(--hrc-ink); white-space: nowrap; }
.hrc-sub { display: block; font-size: 10px; color: var(--hrc-muted); white-space: nowrap; }
.hrc-cell { height: 34px; }
.hrc-cell .hrc-mark { display: block; line-height: 34px; font-weight: 600; font-size: 11px; }
.hrc-roster td.hrc-approved { background: var(--hrc-approved); color: var(--hrc-approved-ink); cursor: pointer; }
.hrc-roster td.hrc-applied { background: var(--hrc-applied); color: var(--hrc-applied-ink); cursor: pointer; }
.hrc-roster td.hrc-planned { background: var(--hrc-planned); color: var(--hrc-planned-ink); cursor: pointer; }
.hrc-roster td.hrc-holiday { background: var(--hrc-holiday); }
.hrc-counts td { height: 26px; background: var(--hrc-pale); color: var(--hrc-muted); font-size: 11px; }
.hrc-counts td.hrc-who { font-weight: 500; background: var(--hrc-pale); }
.hrc-counts td.hrc-bad { background: var(--hrc-danger-soft); color: var(--hrc-danger); font-weight: 600; }

/* the wall */
.hrc-strip { margin: 0 0 12px; padding: 9px 12px; background: var(--hrc-pale); border-radius: 6px;
             font-size: 12px; color: var(--hrc-ink); }
.hrc-strip b { margin-right: 8px; }
.hrc-strip a { margin-right: 12px; white-space: nowrap; }
.hrc-wall { width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: 0;
            border: 1px solid var(--hrc-border); border-radius: 6px; background: #fff; font-size: 12px; }
.hrc-wall th { padding: 8px; text-align: left; font-weight: 500; color: var(--hrc-muted);
               background: var(--hrc-pale); border-bottom: 1px solid var(--hrc-border); }
.hrc-wall td { vertical-align: top; height: 104px; padding: 6px; border-bottom: 1px solid var(--hrc-border-soft);
               border-right: 1px solid var(--hrc-border-soft); }
.hrc-wall td.hrc-blank { background: #FAFBFD; }
.hrc-wall td.hrc-off { background: var(--hrc-holiday); }
.hrc-wall-num { font-weight: 600; color: var(--hrc-ink); margin-bottom: 4px; }
.hrc-wall td.hrc-today .hrc-wall-num { color: var(--hrc-accent); }
.hrc-wall-holiday { font-weight: 400; font-size: 10px; color: var(--hrc-muted); margin-left: 4px; }
.hrc-chip { display: block; margin: 0 0 4px; padding: 3px 6px; border-radius: 4px; cursor: pointer;
            border-left: 3px solid var(--hrc-accent); background: var(--hrc-planned); color: var(--hrc-ink);
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hrc-chip-completed { border-left-color: var(--hrc-approved-ink); background: var(--hrc-approved); }
.hrc-chip-planned { border: 1px dashed var(--hrc-gold); border-left: 3px solid var(--hrc-gold);
                    background: var(--hrc-gold-soft); }
.hrc-chip-time { color: var(--hrc-muted); margin-right: 4px; }
.hrc-chip-count { float: right; color: var(--hrc-muted); margin-left: 6px; }
.hrc-session dt { font-weight: 500; color: var(--hrc-muted); font-size: 11px; margin-top: 8px; }
.hrc-session dd { margin: 0; }
`;

function hrc_style() {
	if (document.getElementById("hrc-style")) return;
	const sheet = document.createElement("style");
	sheet.id = "hrc-style";
	sheet.textContent = HRC_STYLE;
	document.head.appendChild(sheet);
}

frappe.pages["hr-calendar"].on_page_load = function (wrapper) {
	hrc_style();
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("HR Calendar"),
		single_column: true,
	});
	wrapper.calendar = new hrms_addon.HRCalendar(page);
};

frappe.pages["hr-calendar"].on_page_show = function (wrapper) {
	if (wrapper.calendar) wrapper.calendar.refresh();
};

hrms_addon.HRCalendar = class HRCalendar {
	constructor(page) {
		this.page = page;
		this.make_filters();
		this.body = $('<div class="hrc"></div>').appendTo(this.page.main);
		this.refresh();
	}

	// ── what the calendar is looking at ────────────────────────────
	make_filters() {
		this.view = this.page.add_field({
			fieldtype: "Select",
			label: __("Show"),
			fieldname: "view",
			options: [
				{ value: "leave", label: __("Leave") },
				{ value: "training", label: __("Training") },
			],
			default: "leave",
			change: () => this.refresh(),
		});
		this.month = this.page.add_field({
			fieldtype: "Select",
			label: __("Month"),
			fieldname: "month",
			options: this.months(),
			default: this.this_month(),
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
		this.everyone = this.page.add_field({
			fieldtype: "Check",
			label: __("Everyone"),
			fieldname: "everyone",
			change: () => this.refresh(),
		});
		this.page.add_inner_button(__("Previous"), () => this.move(-1));
		this.page.add_inner_button(__("Next"), () => this.move(1));
		this.page.add_inner_button(__("This Month"), () => this.set_month(this.this_month()));
	}

	// a year back and a year ahead of this month
	months() {
		const today = frappe.datetime.now_date(true);
		const options = [];
		for (let step = -12; step <= 12; step++) {
			const date = new Date(today.getFullYear(), today.getMonth() + step, 1);
			options.push({ value: hrc_key(date.getFullYear(), date.getMonth() + 1), label: hrc_label(date) });
		}
		return options;
	}

	this_month() {
		const today = frappe.datetime.now_date(true);
		return hrc_key(today.getFullYear(), today.getMonth() + 1);
	}

	move(step) {
		const [year, month] = String(this.month.get_value() || this.this_month()).split("-").map(Number);
		const date = new Date(year, month - 1 + step, 1);
		this.set_month(hrc_key(date.getFullYear(), date.getMonth() + 1));
	}

	set_month(value) {
		if (!this.months().some((option) => option.value === value)) {
			this.month.df.options = this.months().concat([{ value: value, label: value }]);
			this.month.refresh();
		}
		this.month.set_value(value);
		this.refresh();
	}

	values() {
		const [year, month] = String(this.month.get_value() || this.this_month()).split("-").map(Number);
		return {
			view: this.view.get_value() || "leave",
			year: year,
			month: month,
			branch: this.branch.get_value() || null,
			department: this.department.get_value() || null,
			everyone: this.everyone.get_value() ? 1 : 0,
		};
	}

	refresh() {
		const asked = JSON.stringify(this.values());
		if (this.asking === asked) return;
		this.asking = asked;
		frappe
			.xcall("hrms_addon.hrms_addon.calendar_board.month", this.values())
			.then((data) => {
				if (this.asking !== asked) return;
				this.draw(data);
			})
			.finally(() => {
				if (this.asking === asked) this.asking = null;
			});
	}

	// ── drawing ────────────────────────────────────────────────────
	draw(data) {
		this.body.empty();
		this.body.append(this.band(data));
		if (data.view === "training") {
			this.training(data);
		} else {
			this.leave(data);
		}
	}

	band(data) {
		const esc = frappe.utils.escape_html;
		const where = [data.branch, data.department].filter(Boolean).map(esc).join(" · ");
		const legend =
			data.view === "training"
				? [
						["hrc-chip-scheduled", __("Scheduled")],
						["hrc-chip-completed", __("Completed")],
						["hrc-chip-planned", __("Planned, not booked")],
				  ]
				: [
						["hrc-approved", __("Approved")],
						["hrc-applied", __("Applied for")],
						["hrc-planned", __("Planned")],
						["hrc-holiday", __("Holiday")],
				  ];
		return `
			<div class="hrc-band">
				<div class="hrc-band-title">${esc(data.title)}</div>
				<div class="hrc-band-sub">${where || esc(data.restricted ? __("Your plant and department") : __("All plants"))}</div>
				<div class="hrc-legend">${legend.map(([cls, text]) => `<span><i class="${cls}"></i>${text}</span>`).join("")}</div>
			</div>`;
	}

	// everybody down the side, the days across
	leave(data) {
		const esc = frappe.utils.escape_html;
		if (!data.people.length) {
			this.body.append(
				`<div class="hrc-empty">${
					data.everyone ? __("Nobody here.") : __("No leave this month. Tick Everyone to see the whole roster.")
				}</div>`
			);
			return;
		}
		const days = data.days;
		let html = `<div class="hrc-scroll"><table class="hrc-roster"><thead><tr><th class="hrc-who">${__("Employee")}</th>`;
		days.forEach((day) => {
			html += `<th class="hrc-day${day.holiday ? " hrc-off" : ""}${day.today ? " hrc-today" : ""}" title="${esc(
				day.holiday || ""
			)}"><span class="hrc-dow">${__(day.weekday)}</span><span class="hrc-num">${day.day}</span></th>`;
		});
		html += "</tr></thead><tbody>";
		data.people.forEach((person) => {
			html += `<tr><td class="hrc-who"><span class="hrc-name">${esc(person.employee_name)}</span><span class="hrc-sub">${esc(
				person.designation || person.department || ""
			)}</span></td>`;
			days.forEach((day) => {
				const cell = person.cells[day.date];
				if (!cell) {
					html += `<td class="hrc-cell${day.holiday ? " hrc-off" : ""}"></td>`;
					return;
				}
				const link = cell.link ? ` data-doctype="${esc(cell.link[0])}" data-name="${esc(cell.link[1])}"` : "";
				html += `<td class="hrc-cell hrc-${cell.kind}"${link} title="${esc(cell.label || "")}"><span class="hrc-mark">${
					HRC_MARKS[cell.kind] || ""
				}</span></td>`;
			});
			html += "</tr>";
		});
		html += `<tr class="hrc-counts"><td class="hrc-who">${__("Off")}</td>`;
		days.forEach((day) => {
			const count = data.counts.off[day.date] || 0;
			const bad = data.most_off && count > data.most_off;
			html += `<td class="hrc-count${bad ? " hrc-bad" : ""}" title="${
				bad ? esc(__("More than {0} off at once", [data.most_off])) : ""
			}">${count || ""}</td>`;
		});
		html += `</tr><tr class="hrc-counts"><td class="hrc-who">${__("Planned")}</td>`;
		days.forEach((day) => {
			const count = data.counts.planned[day.date] || 0;
			html += `<td class="hrc-count">${count || ""}</td>`;
		});
		html += "</tr></tbody></table></div>";
		if (data.capped) {
			html += `<div class="hrc-note">${__("The first {0} employees are shown. Narrow it down by plant or department.", [
				data.in_all,
			])}</div>`;
		}
		const $grid = $(html).appendTo(this.body);
		$grid.on("click", "td[data-doctype]", (event) => {
			const cell = $(event.currentTarget);
			frappe.set_route("Form", cell.data("doctype"), cell.data("name"));
		});
	}

	// the weeks down, the days across, each session a chip on its day
	training(data) {
		const esc = frappe.utils.escape_html;
		if (data.planned && data.planned.length) {
			const chips = data.planned
				.map(
					(entry) =>
						`<a href="/app/${frappe.router.slug(entry.link[0])}/${encodeURIComponent(entry.link[1])}">${esc(
							entry.course
						)}${entry.target ? " · " + esc(entry.target) : ""}</a>`
				)
				.join("");
			this.body.append(`<div class="hrc-strip"><b>${__("Planned this month, no date yet")}</b>${chips}</div>`);
		}
		if (!data.sessions.length) {
			this.body.append(`<div class="hrc-empty">${__("Nothing scheduled this month.")}</div>`);
		}
		const by_day = {};
		data.sessions.forEach((session, index) => {
			session.index = index;
			(by_day[session.date] = by_day[session.date] || []).push(session);
		});
		let html = `<table class="hrc-wall"><thead><tr>${HRC_WEEKDAYS.map((day) => `<th>${__(day)}</th>`).join("")}</tr></thead><tbody>`;
		data.weeks.forEach((week) => {
			html += "<tr>";
			week.forEach((day) => {
				if (!day) {
					html += '<td class="hrc-blank"></td>';
					return;
				}
				const chips = (by_day[day.date] || [])
					.map(
						(session) =>
							`<span class="hrc-chip hrc-chip-${session.status}" data-index="${session.index}" title="${esc(
								[session.course, session.venue, session.trainer].filter(Boolean).join(" · ")
							)}"><span class="hrc-chip-time">${esc(session.start)}</span>${esc(session.course || "")}${
								session.people ? `<span class="hrc-chip-count">${session.people}</span>` : ""
							}</span>`
					)
					.join("");
				html += `<td class="hrc-wall-day${day.holiday ? " hrc-off" : ""}${day.today ? " hrc-today" : ""}"><div class="hrc-wall-num">${
					day.day
				}${day.holiday ? `<span class="hrc-wall-holiday">${esc(day.holiday)}</span>` : ""}</div>${chips}</td>`;
			});
			html += "</tr>";
		});
		html += "</tbody></table>";
		const $wall = $(html).appendTo(this.body);
		$wall.on("click", ".hrc-chip", (event) => this.session(data.sessions[$(event.currentTarget).data("index")]));
	}

	session(session) {
		const esc = frappe.utils.escape_html;
		const rows = [
			[__("When"), `${esc(frappe.datetime.str_to_user(session.date))} ${esc(session.start)}${session.end ? " to " + esc(session.end) : ""}`],
			[__("Venue"), esc(session.venue || "")],
			[__("Trainer"), esc(session.trainer || "")],
			[__("For"), esc(session.target || "")],
			[__("Participants"), session.people ? `${session.people}: ${session.names.map(esc).join(", ")}` : ""],
		].filter(([, value]) => value);
		const dialog = new frappe.ui.Dialog({
			title: session.course,
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "body",
					options: `<dl class="hrc-session">${rows.map(([label, value]) => `<dt>${label}</dt><dd>${value}</dd>`).join("")}</dl>`,
				},
			],
			primary_action_label: __("Open"),
			primary_action: () => {
				dialog.hide();
				frappe.set_route("Form", session.link[0], session.link[1]);
			},
		});
		dialog.show();
	}
};

function hrc_key(year, month) {
	return `${year}-${String(month).padStart(2, "0")}`;
}

function hrc_label(date) {
	return `${__(HRC_MONTHS[date.getMonth()])} ${date.getFullYear()}`;
}
