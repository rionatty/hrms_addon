// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

/* The HR calendar view.
 *
 * Leave and training drawn the way Frappe HR's shift roster is: the
 * people (or the departments) down the side, the days across, each day's
 * leave or session a block in its cell. It is worked the same way too:
 * click an empty day to add, drag a block to another day to move it,
 * click a block to change it.
 *
 * The HR Calendar page, the Annual Leave Plan and the Monthly Training
 * Schedule all draw it. hrms_addon.hrms_addon.calendar_board fills it
 * (month) and takes every change, each through the rules and approvals
 * that stand: a move on an approved plan is asked for, not made.
 *
 * Loaded on every desk page (hooks.app_include_js) as a plain asset, so
 * it needs no `bench build`; its styles travel with it for the same
 * reason (see attendance_board.js).
 */

frappe.provide("hrms_addon");

(function () {
	if (hrms_addon.HRCalendarView) return;

	const METHOD = "hrms_addon.hrms_addon.calendar_board.";
	const MONTHS = [
		"January", "February", "March", "April", "May", "June",
		"July", "August", "September", "October", "November", "December",
	];
	const DAY_MS = 86400000;
	const CLOCK =
		'<svg class="hrv-clock" viewBox="0 0 16 16" aria-hidden="true">' +
		'<circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" stroke-width="1.4"></circle>' +
		'<path d="M8 4.6V8l2.3 1.4" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"></path>' +
		"</svg>";

	// Every --hrv-* read here is declared here; the theme's --hra-* colours
	// it borrows carry a fallback, so a theme that has not loaded costs a
	// colour and never the layout.
	const HRV_STYLE = `
.hrv {
  --hrv-navy:          #0A2540;
  --hrv-ink:           var(--hra-ink, #1A2733);
  --hrv-muted:         var(--hra-ink-muted, #546678);
  --hrv-accent:        var(--hra-accent, #0A6ED1);
  --hrv-line:          #E3E8EF;
  --hrv-line-strong:   var(--hra-border, #C3D0E0);
  --hrv-head:          #F7F9FC;
  --hrv-hover:         #F4F8FD;
  --hrv-gold:          #A9791C;
  --hrv-gold-soft:     #FBF1D9;
  --hrv-gold-ink:      #6B4A0E;
  --hrv-danger:        var(--hra-danger, #A62B25);
  --hrv-danger-soft:   #FBE7E6;
  --hrv-approved:      #E7F4EA;
  --hrv-approved-line: #9FD1AE;
  --hrv-approved-ink:  #1E6B34;
  --hrv-applied:       #FDF3E1;
  --hrv-applied-line:  #EFC77E;
  --hrv-applied-ink:   #8A4A06;
  --hrv-planned:       #EAF2FD;
  --hrv-planned-line:  #A9C8EE;
  --hrv-planned-ink:   #0B4A8B;
  --hrv-holiday:       #F1F3F6;
  --hrv-cell-w:        116px;
  --hrv-row-h:         74px;
  color: var(--hrv-ink);
}
.hrv-bar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin: 2px 0 10px; }
.hrv-nav { display: flex; align-items: center; gap: 6px; }
.hrv-arrow { width: 28px; height: 28px; border: 1px solid var(--hrv-line); border-radius: 6px; background: #fff;
             color: var(--hrv-ink); font-size: 16px; line-height: 1; cursor: pointer; }
.hrv-arrow:disabled { opacity: .35; cursor: default; }
.hrv-title { min-width: 124px; text-align: center; font-weight: 600; font-size: 14px; }
.hrv-today-btn { height: 28px; padding: 0 10px; border: 1px solid var(--hrv-line); border-radius: 6px; background: #fff;
                 font-size: 12px; color: var(--hrv-ink); cursor: pointer; }
.hrv-switch { display: inline-flex; border: 1px solid var(--hrv-line); border-radius: 6px; overflow: hidden; }
.hrv-switch button { border: 0; background: #fff; padding: 5px 14px; font-size: 12px; color: var(--hrv-ink); cursor: pointer; }
.hrv-switch button.hrv-on { background: var(--hrv-navy); color: #fff; }
.hrv-where { font-size: 12px; color: var(--hrv-muted); }
.hrv-legend { margin-left: auto; display: flex; gap: 12px; flex-wrap: wrap; font-size: 11px; color: var(--hrv-muted); }
.hrv-legend i { display: inline-block; width: 12px; height: 12px; border-radius: 3px; border: 1px solid transparent;
                vertical-align: -2px; margin-right: 4px; }
.hrv-hint { font-size: 11px; color: var(--hrv-muted); margin: -4px 0 10px; }
.hrv-empty { padding: 30px; text-align: center; color: var(--hrv-muted); background: var(--hrv-head);
             border: 1px dashed var(--hrv-line-strong); border-radius: 8px; }
.hrv-note { font-size: 11px; color: var(--hrv-muted); margin-top: 8px; }
.hrv-loading .hrv-scroll { opacity: .55; pointer-events: none; }

.hrv-scroll { overflow: auto; max-height: 72vh; border: 1px solid var(--hrv-line); border-radius: 8px; background: #fff; }
.hrv-roster { border-collapse: separate; border-spacing: 0; font-size: 12px; }
.hrv-roster th, .hrv-roster td { border-right: 1px solid var(--hrv-line); border-bottom: 1px solid var(--hrv-line); }
.hrv-roster thead th { position: sticky; top: 0; z-index: 3; height: 42px; padding: 0 6px; background: #fff;
                       font-weight: 500; text-align: center; white-space: nowrap; min-width: var(--hrv-cell-w); }
.hrv-roster th.hrv-holiday { background: var(--hrv-holiday); color: var(--hrv-muted); }
.hrv-roster th.hrv-today { color: var(--hrv-accent); box-shadow: inset 0 -2px 0 var(--hrv-accent); }
.hrv-roster .hrv-who { position: sticky; left: 0; z-index: 2; min-width: 214px; max-width: 214px; padding: 8px 10px;
                       background: #fff; text-align: left; }
.hrv-roster thead .hrv-who { z-index: 4; }
.hrv-search { width: 100%; height: 28px; padding: 0 8px; border: 1px solid var(--hrv-line); border-radius: 6px;
              background: var(--hrv-head); font-size: 12px; color: var(--hrv-ink); }
.hrv-person { display: flex; align-items: center; gap: 10px; }
.hrv-avatar { flex: none; width: 32px; height: 32px; border-radius: 50%; background: #E9EDF2; color: var(--hrv-muted);
              display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 13px; }
.hrv-names { min-width: 0; display: flex; flex-direction: column; }
.hrv-name { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hrv-role { font-size: 11px; color: var(--hrv-accent); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hrv-cell { position: relative; vertical-align: top; height: var(--hrv-row-h); min-width: var(--hrv-cell-w);
            max-width: var(--hrv-cell-w); padding: 5px; }
.hrv-roster td.hrv-holiday { background: var(--hrv-holiday); }
.hrv-roster td.hrv-can-add { cursor: pointer; }
.hrv-roster td.hrv-can-add:hover { background: var(--hrv-hover); }
.hrv-roster td.hrv-can-add:empty:hover::after { content: "+"; position: absolute; inset: 0; display: flex;
  align-items: center; justify-content: center; font-size: 20px; color: var(--hrv-accent); }
.hrv-roster td.hrv-drop { background: var(--hrv-hover); box-shadow: inset 0 0 0 2px var(--hrv-accent); }
.hrv-blocked { height: 100%; display: flex; align-items: center; justify-content: center; text-align: center;
               font-size: 11px; color: var(--hrv-muted); }

.hrv-chip { display: block; margin: 0 0 4px; padding: 5px 7px; border: 1px solid var(--hrv-planned-line);
            border-radius: 6px; background: var(--hrv-planned); color: var(--hrv-planned-ink); line-height: 1.3;
            cursor: pointer; user-select: none; overflow: hidden; }
.hrv-chip-title { display: block; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hrv-chip-sub { display: flex; align-items: center; gap: 4px; font-size: 11px; opacity: .85; white-space: nowrap;
                overflow: hidden; text-overflow: ellipsis; }
.hrv-chip-count { float: right; margin-left: 4px; padding: 0 5px; border-radius: 8px; background: rgba(255,255,255,.7);
                  font-size: 10px; font-weight: 600; }
.hrv-clock { flex: none; width: 11px; height: 11px; }
.hrv-chip.hrv-movable { cursor: grab; }
.hrv-chip.hrv-dragging { opacity: .4; }
.hrv-chip.hrv-k-approved { background: var(--hrv-approved); border-color: var(--hrv-approved-line); color: var(--hrv-approved-ink); }
.hrv-chip.hrv-k-applied { background: var(--hrv-applied); border-color: var(--hrv-applied-line); color: var(--hrv-applied-ink); }
.hrv-chip.hrv-k-planned { background: var(--hrv-planned); border-color: var(--hrv-planned-line); color: var(--hrv-planned-ink); }
.hrv-chip.hrv-k-moving { background: var(--hrv-gold-soft); border: 1px dashed var(--hrv-gold); color: var(--hrv-gold-ink); }
.hrv-chip.hrv-k-scheduled { background: var(--hrv-planned); border-color: var(--hrv-planned-line); color: var(--hrv-planned-ink); }
.hrv-chip.hrv-k-completed { background: var(--hrv-approved); border-color: var(--hrv-approved-line); color: var(--hrv-approved-ink); }
.hrv-training .hrv-chip.hrv-k-planned { background: var(--hrv-gold-soft); border: 1px dashed var(--hrv-gold); color: var(--hrv-gold-ink); }
.hrv-legend i.hrv-key-approved, .hrv-legend i.hrv-key-completed { background: var(--hrv-approved); border-color: var(--hrv-approved-line); }
.hrv-legend i.hrv-key-applied { background: var(--hrv-applied); border-color: var(--hrv-applied-line); }
.hrv-legend i.hrv-key-planned, .hrv-legend i.hrv-key-scheduled { background: var(--hrv-planned); border-color: var(--hrv-planned-line); }
.hrv-legend i.hrv-key-moving, .hrv-legend i.hrv-key-unbooked { background: var(--hrv-gold-soft); border: 1px dashed var(--hrv-gold); }
.hrv-legend i.hrv-key-holiday { background: var(--hrv-holiday); border-color: var(--hrv-line-strong); }

.hrv-roster tfoot td { height: 28px; background: var(--hrv-head); color: var(--hrv-muted); font-size: 11px; text-align: center; }
.hrv-roster tfoot td.hrv-who { font-weight: 500; text-align: left; background: var(--hrv-head); }
.hrv-roster tfoot td.hrv-bad { background: var(--hrv-danger-soft); color: var(--hrv-danger); font-weight: 600; }

.hrv-strip { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 0 0 10px; padding: 8px 10px;
             background: var(--hrv-head); border-radius: 8px; font-size: 12px; }
.hrv-strip-label { font-weight: 500; margin-right: 4px; }
.hrv-entry { padding: 3px 8px; border: 1px dashed var(--hrv-gold); border-radius: 6px; background: var(--hrv-gold-soft);
             color: var(--hrv-gold-ink); cursor: grab; }
.hrv-entry small { margin-left: 6px; opacity: .8; }
.hrv-info { font-size: 12px; color: var(--hrv-muted); }
.hrv-info b { color: var(--hrv-ink); }
.hrv-facts dt { margin-top: 8px; font-size: 11px; font-weight: 500; color: var(--hrv-muted); }
.hrv-facts dd { margin: 0; }
`;

	function hrv_style() {
		if (document.getElementById("hrv-style")) return;
		const sheet = document.createElement("style");
		sheet.id = "hrv-style";
		sheet.textContent = HRV_STYLE;
		document.head.appendChild(sheet);
	}

	function esc(value) {
		return frappe.utils.escape_html(value === undefined || value === null ? "" : String(value));
	}

	// dates as the server sends them, "2027-03-10"; worked in UTC so no
	// change of clocks can move a day (frappe.datetime.add_days returns a
	// whole timestamp, which is why it is not used)
	function day_ms(date) {
		const parts = String(date).slice(0, 10).split("-").map(Number);
		return Date.UTC(parts[0], parts[1] - 1, parts[2]);
	}
	function add_days(date, days) {
		return new Date(day_ms(date) + days * DAY_MS).toISOString().slice(0, 10);
	}
	function days_between(later, earlier) {
		return Math.round((day_ms(later) - day_ms(earlier)) / DAY_MS);
	}
	function user_date(date) {
		return date ? frappe.datetime.str_to_user(date) : "";
	}
	function span(first, last) {
		return first === last ? user_date(first) : __("{0} to {1}", [user_date(first), user_date(last)]);
	}

	function legend(view) {
		return view === "training"
			? [
					["scheduled", __("Scheduled")],
					["completed", __("Completed")],
					["unbooked", __("On a draft schedule")],
					["holiday", __("Holiday")],
			  ]
			: [
					["approved", __("Approved")],
					["applied", __("Applied for")],
					["planned", __("Planned")],
					["moving", __("Move asked")],
					["holiday", __("Holiday")],
			  ];
	}

	hrms_addon.HRCalendarView = class HRCalendarView {
		constructor(opts) {
			this.opts = Object.assign({ view: "leave", switchable: false }, opts || {});
			this.view = this.opts.view === "training" ? "training" : "leave";
			const today = frappe.datetime.now_date(true);
			this.year = cint(this.opts.year) || today.getFullYear();
			this.month =
				cint(this.opts.month) || (this.year === today.getFullYear() ? today.getMonth() + 1 : 1);
			this.filters = {
				branch: this.opts.branch || null,
				department: this.opts.department || null,
				everyone: this.opts.everyone ? 1 : 0,
			};
			this.search = "";
			this.data = null;
			hrv_style();
			this.$root = $('<div class="hrv"></div>').appendTo($(this.opts.parent).empty());
			this.bind();
			this.refresh();
		}

		// ── what it is looking at ──────────────────────────────────
		set_filters(filters) {
			Object.assign(this.filters, filters);
			this.refresh();
		}

		go(step) {
			if (this.opts.schedule) return;
			let month = this.month + step;
			let year = this.year;
			if (month < 1) {
				month = 12;
				year -= 1;
			} else if (month > 12) {
				month = 1;
				year += 1;
			}
			if (this.opts.plan && year !== this.year) return; // a plan is one year
			this.year = year;
			this.month = month;
			this.scrolled = false;
			this.refresh();
		}

		go_today() {
			const today = frappe.datetime.now_date(true);
			if (this.opts.plan && today.getFullYear() !== this.year) return;
			this.year = today.getFullYear();
			this.month = today.getMonth() + 1;
			this.scrolled = false;
			this.refresh();
		}

		args() {
			return {
				view: this.view,
				year: this.year,
				month: this.month,
				branch: this.filters.branch || null,
				department: this.filters.department || null,
				everyone: this.filters.everyone ? 1 : 0,
				plan: this.opts.plan || null,
				schedule: this.opts.schedule || null,
			};
		}

		refresh() {
			const args = this.args();
			const asked = JSON.stringify(args);
			this.asked = asked;
			this.$root.addClass("hrv-loading");
			return frappe
				.xcall(METHOD + "month", args)
				.then((data) => {
					if (this.asked !== asked) return;
					this.data = data;
					this.year = data.year;
					this.month = data.month;
					this.draw();
				})
				.finally(() => {
					if (this.asked === asked) this.$root.removeClass("hrv-loading");
				});
		}

		// ── drawing ────────────────────────────────────────────────
		draw() {
			const data = this.data;
			this.rows = {};
			(data.rows || []).forEach((row) => (this.rows[row.key] = row));
			this.$root.toggleClass("hrv-training", data.view === "training");
			let html = this.bar(data);
			if (data.view === "training" && (data.undated || []).length) html += this.strip(data);
			html += (data.rows || []).length
				? this.table(data)
				: `<div class="hrv-empty">${esc(this.empty_text(data))}</div>`;
			this.$root.html(html);
			this.$root.find(".hrv-search").val(this.search);
			this.filter_rows();
			this.scroll_to_today();
		}

		empty_text(data) {
			if (data.view === "training") return __("Nothing scheduled this month.");
			if (data.plan) return __("Nobody is on the plan yet. Get Employees first.");
			return data.everyone
				? __("Nobody here.")
				: __("No leave this month. Tick Everyone to see the whole roster.");
		}

		bar(data) {
			const month = `${esc(__(MONTHS[data.month - 1]))}, ${data.year}`;
			let nav = `<span class="hrv-title">${month}</span>`;
			if (!this.opts.schedule) {
				const first = this.opts.plan && data.month === 1 ? " disabled" : "";
				const last = this.opts.plan && data.month === 12 ? " disabled" : "";
				nav =
					`<button class="hrv-arrow" data-go="-1" title="${esc(__("Previous Month"))}"${first}>&lsaquo;</button>` +
					nav +
					`<button class="hrv-arrow" data-go="1" title="${esc(__("Next Month"))}"${last}>&rsaquo;</button>` +
					`<button class="hrv-today-btn">${esc(__("Today"))}</button>`;
			}
			const views = this.opts.switchable
				? `<div class="hrv-switch">${[
						["leave", __("Leave")],
						["training", __("Training")],
				  ]
						.map(
							([view, label]) =>
								`<button data-view="${view}" class="${view === data.view ? "hrv-on" : ""}">${esc(label)}</button>`
						)
						.join("")}</div>`
				: "";
			const where =
				[data.branch, data.department].filter(Boolean).join(" · ") ||
				(data.restricted ? __("Your plant and department") : "");
			const keys = legend(data.view)
				.map(([kind, text]) => `<span><i class="hrv-key-${kind}"></i>${esc(text)}</span>`)
				.join("");
			const works =
				(data.rows || []).some((row) => row.add) ||
				Object.values(data.blocks || {}).some((block) => block.move);
			return (
				`<div class="hrv-bar"><div class="hrv-nav">${nav}</div>${views}` +
				(where ? `<span class="hrv-where">${esc(where)}</span>` : "") +
				`<div class="hrv-legend">${keys}</div></div>` +
				(works
					? `<div class="hrv-hint">${esc(
							__("Click a day to add. Drag a block to move it. Click a block to change it.")
					  )}</div>`
					: "")
			);
		}

		strip(data) {
			return (
				`<div class="hrv-strip"><span class="hrv-strip-label">${esc(
					__("On the year's calendar, no date yet")
				)}</span>` +
				data.undated
					.map(
						(entry, index) =>
							`<span class="hrv-entry" draggable="true" data-entry="${index}" title="${esc(
								[entry.course, entry.target, entry.trainer].filter(Boolean).join(" · ")
							)}">${esc(entry.course)}${entry.target ? `<small>${esc(entry.target)}</small>` : ""}</span>`
					)
					.join("") +
				"</div>"
			);
		}

		table(data) {
			const training = data.view === "training";
			let html = '<div class="hrv-scroll"><table class="hrv-roster"><thead><tr>';
			html += `<th class="hrv-who"><input class="hrv-search" type="search" placeholder="${esc(
				training ? __("Search Department") : __("Search Employee")
			)}"></th>`;
			data.days.forEach((day) => {
				const classes = ["hrv-day"];
				if (day.holiday) classes.push("hrv-holiday");
				if (day.today) classes.push("hrv-today");
				html += `<th class="${classes.join(" ")}" data-date="${day.date}" title="${esc(day.holiday || "")}">${esc(
					__(day.weekday)
				)} ${String(day.day).padStart(2, "0")}</th>`;
			});
			html += "</tr></thead><tbody>";
			data.rows.forEach((row) => {
				html += `<tr data-row="${esc(row.key)}" data-title="${esc(String(row.title || "").toLowerCase())}">`;
				html += `<td class="hrv-who">${this.who(row)}</td>`;
				data.days.forEach((day) => (html += this.cell(data, row, day)));
				html += "</tr>";
			});
			html += "</tbody>";
			if (!training) html += this.footer(data);
			html += "</table></div>";
			if (data.capped) {
				html += `<div class="hrv-note">${esc(
					__("The first {0} employees are shown. Narrow it down by plant or department.", [data.in_all])
				)}</div>`;
			}
			return html;
		}

		who(row) {
			const initial = String(row.title || "?").trim().charAt(0).toUpperCase();
			return (
				`<div class="hrv-person"><span class="hrv-avatar">${esc(initial)}</span>` +
				`<span class="hrv-names"><span class="hrv-name">${esc(row.title)}</span>` +
				`<span class="hrv-role">${esc(row.subtitle || "")}</span></span></div>`
			);
		}

		cell(data, row, day) {
			const here = ((data.cells || {})[row.key] || {})[day.date] || { blocks: [], holiday: null };
			const leave = data.view !== "training";
			const classes = ["hrv-cell"];
			if (here.holiday) classes.push("hrv-holiday");
			let inner = "";
			if (leave && here.holiday) {
				inner = `<div class="hrv-blocked">${esc(here.holiday)}</div>`;
			} else {
				inner = here.blocks.map((key) => this.chip(data, data.blocks[key], day.date)).join("");
			}
			// a leave day takes one block; a department's day takes as many sessions as it has
			if (row.add && !(leave && (here.holiday || here.blocks.length))) classes.push("hrv-can-add");
			return `<td class="${classes.join(" ")}" data-row="${esc(row.key)}" data-date="${day.date}">${inner}</td>`;
		}

		chip(data, block, date) {
			if (!block) return "";
			const movable = !!block.move;
			const classes = ["hrv-chip", "hrv-k-" + block.kind];
			if (movable) classes.push("hrv-movable");
			const clock = data.view === "training" ? CLOCK : "";
			const count = block.people
				? `<span class="hrv-chip-count" title="${esc(__("Participants"))}">${cint(block.people)}</span>`
				: "";
			return (
				`<div class="${classes.join(" ")}" draggable="${movable ? "true" : "false"}" data-key="${esc(
					block.key
				)}" data-date="${date}" title="${esc(this.tip(block))}">` +
				`<span class="hrv-chip-title">${count}${esc(block.title || "")}</span>` +
				(block.subtitle ? `<span class="hrv-chip-sub">${clock}${esc(block.subtitle)}</span>` : "") +
				"</div>"
			);
		}

		tip(block) {
			return [block.title, span(block.from, block.to), block.subtitle, block.venue, block.trainer]
				.filter(Boolean)
				.join(" · ");
		}

		footer(data) {
			const line = (label, values, mark) =>
				`<tr><td class="hrv-who">${esc(label)}</td>` +
				data.days
					.map((day) => {
						const count = (values || {})[day.date] || 0;
						const bad = mark && data.most_off && count > data.most_off;
						return `<td class="hrv-count${bad ? " hrv-bad" : ""}"${
							bad ? ` title="${esc(__("More than {0} off at once", [data.most_off]))}"` : ""
						}>${count || ""}</td>`;
					})
					.join("") +
				"</tr>";
			return `<tfoot>${line(__("Off"), data.counts.off, true)}${line(__("Planned"), data.counts.planned, false)}</tfoot>`;
		}

		filter_rows() {
			const wanted = this.search.trim().toLowerCase();
			this.$root.find("tbody tr").each((_index, tr) => {
				tr.style.display = !wanted || (tr.dataset.title || "").indexOf(wanted) !== -1 ? "" : "none";
			});
		}

		scroll_to_today() {
			if (this.scrolled) return;
			const scroll = this.$root.find(".hrv-scroll")[0];
			const today = this.$root.find("th.hrv-today")[0];
			if (!scroll || !today) return;
			const who = this.$root.find("thead .hrv-who")[0];
			scroll.scrollLeft = Math.max(today.offsetLeft - (who ? who.offsetWidth : 0) - 24, 0);
			this.scrolled = true;
		}

		// ── working it ─────────────────────────────────────────────
		bind() {
			const root = this.$root;
			root.on("click", "[data-go]", (event) => this.go(cint(event.currentTarget.dataset.go)));
			root.on("click", ".hrv-today-btn", () => this.go_today());
			root.on("click", "[data-view]", (event) => {
				const view = event.currentTarget.dataset.view;
				if (view === this.view) return;
				this.view = view;
				this.scrolled = false;
				this.refresh();
				if (this.opts.on_view) this.opts.on_view(view);
			});
			root.on("input", ".hrv-search", (event) => {
				this.search = event.currentTarget.value || "";
				this.filter_rows();
			});
			root.on("click", ".hrv-chip", (event) => {
				event.stopPropagation();
				const block = this.data && this.data.blocks[event.currentTarget.dataset.key];
				if (block) this.open_block(block);
			});
			root.on("click", "td.hrv-can-add", (event) => {
				const row = this.rows[event.currentTarget.dataset.row];
				if (row) this.open_day(row, event.currentTarget.dataset.date);
			});
			root.on("click", ".hrv-entry", (event) => {
				const entry = this.data.undated[cint(event.currentTarget.dataset.entry)];
				if (entry) this.session_dialog({ entry: entry });
			});
			root.on("dragstart", ".hrv-chip, .hrv-entry", (event) => {
				const element = event.currentTarget;
				if (element.getAttribute("draggable") !== "true") return;
				this.drag =
					element.dataset.entry !== undefined
						? { entry: this.data.undated[cint(element.dataset.entry)] }
						: { key: element.dataset.key, grabbed: element.dataset.date };
				const transfer = event.originalEvent && event.originalEvent.dataTransfer;
				if (transfer) {
					transfer.effectAllowed = "move";
					transfer.setData("text/plain", element.dataset.key || "entry");
				}
				if (this.drag.key) {
					root.find(".hrv-chip")
						.filter((_index, chip) => chip.dataset.key === this.drag.key)
						.addClass("hrv-dragging");
				}
			});
			root.on("dragend", () => this.end_drag());
			root.on("dragover", "td.hrv-cell", (event) => {
				const target = this.target_of(event.currentTarget);
				if (!target) {
					this.clear_drop();
					return;
				}
				event.preventDefault();
				if (event.originalEvent && event.originalEvent.dataTransfer) {
					event.originalEvent.dataTransfer.dropEffect = "move";
				}
				this.show_drop(target);
			});
			root.on("drop", "td.hrv-cell", (event) => {
				event.preventDefault();
				const target = this.target_of(event.currentTarget);
				this.end_drag();
				if (target) this.dropped(target);
			});
		}

		// Where a block dragged over this cell would land: the day it is
		// held by lands on the cell, the rest of it follows. Leave stays on
		// its own row; a session on a draft schedule may go to another
		// department's row, a booked one keeps its row.
		target_of(cell) {
			const drag = this.drag;
			if (!drag || !cell || !this.data) return null;
			const row = cell.dataset.row;
			const date = cell.dataset.date;
			const training = this.data.view === "training";
			if (drag.entry) return training ? { row: row, first: date, last: date, entry: drag.entry } : null;
			const block = this.data.blocks[drag.key];
			if (!block || !block.move) return null;
			if ((!training || block.key.indexOf("evt:") === 0) && row !== block.row) return null;
			const first = add_days(date, -days_between(drag.grabbed, block.from));
			const last = add_days(first, days_between(block.to, block.from));
			if (first === block.from && row === block.row) return null;
			return { row: row, first: first, last: last, block: block };
		}

		show_drop(target) {
			const key = [target.row, target.first, target.last].join("|");
			if (this.drop_key === key) return;
			this.clear_drop();
			this.drop_key = key;
			this.$root
				.find("td.hrv-cell")
				.filter(
					(_index, cell) =>
						cell.dataset.row === target.row &&
						cell.dataset.date >= target.first &&
						cell.dataset.date <= target.last
				)
				.addClass("hrv-drop");
		}

		clear_drop() {
			this.drop_key = null;
			this.$root.find("td.hrv-drop").removeClass("hrv-drop");
		}

		end_drag() {
			this.clear_drop();
			this.$root.find(".hrv-dragging").removeClass("hrv-dragging");
			this.drag = null;
		}

		dropped(target) {
			if (target.entry) {
				this.session_dialog({ entry: target.entry, date: target.first, department: target.row });
				return;
			}
			const block = target.block;
			if (this.data.view === "training") {
				if (block.key.indexOf("evt:") === 0) {
					frappe.confirm(
						esc(__("Move {0} to {1}? Its people are told.", [block.title, user_date(target.first)])),
						() =>
							this.change("move_session", { key: block.key, date: target.first }, __("Moved. Its people are told."))
					);
					return;
				}
				this.change("move_session", { key: block.key, date: target.first, department: target.row }, __("Moved"));
				return;
			}
			if (block.move === "direct") {
				this.change("save_leave", { plan_row: block.plan_row, from_date: target.first }, __("Moved"));
			} else if (block.move === "ask") {
				this.ask_move(block, target.first, target.last);
			}
		}

		// before_change: the form saves its own edits first; after_change:
		// the form reloads (and redraws this with it), else this redraws
		change(method, args, message) {
			return Promise.resolve(this.opts.before_change ? this.opts.before_change() : null)
				.then(() => frappe.xcall(METHOD + method, args))
				.then((result) => {
					if (message) frappe.show_alert({ message: message, indicator: "green" });
					if (this.opts.after_change) this.opts.after_change(result);
					else this.refresh();
					return result;
				});
		}

		open_day(row, date) {
			if (this.data.view === "training") {
				this.session_dialog({ date: date, department: row.key });
			} else if (row.add === "plan") {
				this.plan_dialog(row, date);
			} else if (row.add === "apply") {
				this.apply_dialog(row, date);
			}
		}

		open_block(block) {
			if (this.data.view === "training") this.session_block(block);
			else this.leave_block(block);
		}

		// ── leave ──────────────────────────────────────────────────
		plan_dialog(row, date) {
			const dialog = new frappe.ui.Dialog({
				title: __("Plan Leave: {0}", [row.title]),
				fields: [
					{ fieldtype: "Date", fieldname: "from_date", label: __("From"), reqd: 1, default: date },
					{ fieldtype: "Column Break", fieldname: "column_1" },
					{ fieldtype: "Date", fieldname: "to_date", label: __("To"), reqd: 1, default: date },
					{ fieldtype: "Section Break", fieldname: "section_1" },
					{ fieldtype: "HTML", fieldname: "info" },
				],
				primary_action_label: __("Save"),
				primary_action: (values) =>
					this.change(
						"save_leave",
						{
							employee: row.key,
							from_date: values.from_date,
							to_date: values.to_date,
							plan: this.opts.plan || null,
						},
						__("Leave planned")
					).then(() => dialog.hide()),
			});
			dialog.show();
			frappe
				.xcall(METHOD + "leave_info", { employee: row.key, year: this.year })
				.then((info) =>
					dialog.fields_dict.info.$wrapper.html(
						`<div class="hrv-info">${esc(__("Available"))} <b>${info.available}</b> · ${esc(
							__("Planned")
						)} <b>${info.planned}</b> · ${esc(__("Left"))} <b>${info.left}</b></div>`
					)
				)
				.catch(() => null);
		}

		apply_dialog(row, date) {
			const dialog = new frappe.ui.Dialog({
				title: __("Apply for Leave: {0}", [row.title]),
				fields: [
					{
						fieldtype: "Link",
						fieldname: "leave_type",
						label: __("Leave Type"),
						options: "Leave Type",
						reqd: 1,
						default: "Annual Leave",
					},
					{ fieldtype: "Section Break", fieldname: "section_1" },
					{ fieldtype: "Date", fieldname: "from_date", label: __("From"), reqd: 1, default: date },
					{ fieldtype: "Column Break", fieldname: "column_1" },
					{ fieldtype: "Date", fieldname: "to_date", label: __("To"), reqd: 1, default: date },
				],
				primary_action_label: __("Continue"),
				primary_action: (values) =>
					frappe
						.xcall(METHOD + "apply_leave", {
							employee: row.key,
							from_date: values.from_date,
							to_date: values.to_date,
							leave_type: values.leave_type,
						})
						.then((name) => {
							dialog.hide();
							frappe.set_route("Form", "Leave Application", name);
						}),
			});
			dialog.show();
		}

		leave_block(block) {
			const facts = `<dl class="hrv-facts"><dt>${esc(block.title)}</dt><dd>${esc(span(block.from, block.to))}${
				block.subtitle ? " · " + esc(block.subtitle) : ""
			}</dd></dl>`;
			if (block.kind === "planned" && block.move === "direct") {
				const dialog = new frappe.ui.Dialog({
					title: __("Planned Leave"),
					fields: [
						{ fieldtype: "Date", fieldname: "from_date", label: __("From"), reqd: 1, default: block.from },
						{ fieldtype: "Column Break", fieldname: "column_1" },
						{ fieldtype: "Date", fieldname: "to_date", label: __("To"), reqd: 1, default: block.to },
					],
					primary_action_label: __("Save"),
					primary_action: (values) =>
						this.change(
							"save_leave",
							{ plan_row: block.plan_row, from_date: values.from_date, to_date: values.to_date },
							__("Saved")
						).then(() => dialog.hide()),
					secondary_action_label: __("Remove"),
					secondary_action: () =>
						frappe.confirm(esc(__("Take this leave off the plan?")), () =>
							this.change("remove_leave", { plan_row: block.plan_row }, __("Removed")).then(() =>
								dialog.hide()
							)
						),
				});
				dialog.show();
				return;
			}
			if (block.kind === "planned" && block.move === "ask") {
				this.ask_move(block, block.from, block.to);
				return;
			}
			const dialog = new frappe.ui.Dialog({
				title: block.kind === "planned" ? __("Planned Leave") : block.title,
				fields: [{ fieldtype: "HTML", fieldname: "facts", options: facts }],
				primary_action_label: __("Open"),
				primary_action: () => {
					dialog.hide();
					frappe.set_route("Form", block.link[0], block.link[1]);
				},
			});
			if (block.apply) this.offer_apply(dialog, block);
			dialog.show();
		}

		offer_apply(dialog, block) {
			dialog.set_secondary_action_label(__("Apply for This Leave"));
			dialog.set_secondary_action(() =>
				frappe
					.xcall("hrms_addon.hrms_addon.leave.apply_from_plan", { row: block.plan_row })
					.then((name) => {
						dialog.hide();
						frappe.set_route("Form", "Leave Application", name);
					})
			);
		}

		// on an approved plan a move is asked for: the supervisor and then
		// the head of department approve it (Leave Plan Change)
		ask_move(block, first, last) {
			const dialog = new frappe.ui.Dialog({
				title: __("Ask to Move Leave"),
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "now",
						options: `<div class="hrv-info">${esc(__("Planned now"))}: <b>${esc(span(block.from, block.to))}</b></div>`,
					},
					{ fieldtype: "Date", fieldname: "from_date", label: __("New From"), reqd: 1, default: first },
					{ fieldtype: "Column Break", fieldname: "column_1" },
					{ fieldtype: "Date", fieldname: "to_date", label: __("New To"), reqd: 1, default: last },
					{ fieldtype: "Section Break", fieldname: "section_1" },
					{ fieldtype: "Small Text", fieldname: "reason", label: __("Reason"), reqd: 1 },
				],
				primary_action_label: __("Ask to Move"),
				primary_action: (values) =>
					this.change(
						"save_leave",
						{
							plan_row: block.plan_row,
							from_date: values.from_date,
							to_date: values.to_date,
							reason: values.reason,
						},
						__("Sent to the supervisor")
					).then(() => dialog.hide()),
			});
			if (block.apply) this.offer_apply(dialog, block);
			dialog.show();
		}

		// ── training ───────────────────────────────────────────────
		session_dialog(given) {
			const line = given.block || null;
			const undated = (this.data && this.data.undated) || [];
			const entry = given.entry || null;
			const choices = [{ value: "", label: "" }].concat(
				undated.map((item) => ({
					value: item.entry,
					label: [item.course, item.target].filter(Boolean).join(" · "),
				}))
			);
			const dialog = new frappe.ui.Dialog({
				title: line ? __("Training") : __("Add Training"),
				fields: [
					{
						fieldtype: "Select",
						fieldname: "calendar_entry",
						label: __("From the Year's Calendar"),
						options: choices,
						default: entry ? entry.entry : "",
						hidden: line || !undated.length ? 1 : 0,
						change: () => {
							const picked = undated.find(
								(item) => item.entry === dialog.get_value("calendar_entry")
							);
							if (!picked) return;
							dialog.set_value("course", picked.course || "");
							dialog.set_value("trainer", picked.trainer || "");
							dialog.set_value("target_group", picked.target || "");
						},
					},
					{
						fieldtype: "Data",
						fieldname: "course",
						label: __("Course"),
						reqd: 1,
						default: line ? line.title : entry ? entry.course : "",
					},
					{
						fieldtype: "Date",
						fieldname: "date",
						label: __("Date"),
						reqd: 1,
						default: line ? line.from : given.date || "",
					},
					{
						fieldtype: "Link",
						fieldname: "department",
						label: __("Department"),
						options: "Department",
						default: line ? line.department || "" : given.department || "",
					},
					{ fieldtype: "Column Break", fieldname: "column_1" },
					{
						fieldtype: "Time",
						fieldname: "start_time",
						label: __("Start"),
						default: (line && line.start_time ? line.start_time : "07:00") + ":00",
					},
					{
						fieldtype: "Time",
						fieldname: "end_time",
						label: __("End"),
						default: (line && line.end_time ? line.end_time : "09:00") + ":00",
					},
					{ fieldtype: "Data", fieldname: "venue", label: __("Venue"), default: line ? line.venue || "" : "" },
					{
						fieldtype: "Data",
						fieldname: "trainer",
						label: __("Trainer"),
						default: line ? line.trainer || "" : entry ? entry.trainer || "" : "",
					},
					{
						fieldtype: "Data",
						fieldname: "target_group",
						label: __("Target Group"),
						default: line ? line.target || "" : entry ? entry.target || "" : "",
					},
				],
				primary_action_label: __("Save"),
				primary_action: (values) =>
					this.change(
						"save_session",
						Object.assign({}, values, {
							line: line ? line.key.slice(5) : null,
							schedule: line ? null : this.opts.schedule || null,
							branch: this.filters.branch || null,
						}),
						line ? __("Saved") : __("Training added")
					).then(() => dialog.hide()),
			});
			if (line) {
				dialog.set_secondary_action_label(__("Remove"));
				dialog.set_secondary_action(() =>
					frappe.confirm(esc(__("Take {0} off the schedule?", [line.title])), () =>
						this.change("remove_session", { line: line.key.slice(5) }, __("Removed")).then(() =>
							dialog.hide()
						)
					)
				);
			}
			dialog.show();
		}

		session_block(block) {
			if (block.key.indexOf("line:") === 0 && block.move) {
				this.session_dialog({ block: block });
				return;
			}
			const rows = [
				[__("When"), `${span(block.from, block.to)} ${block.subtitle || ""}`],
				[__("Venue"), block.venue],
				[__("Trainer"), block.trainer],
				[__("For"), block.target],
				[
					__("Participants"),
					block.people ? `${block.people}: ${(block.names || []).join(", ")}` : "",
				],
			].filter(([, value]) => value);
			const dialog = new frappe.ui.Dialog({
				title: block.title,
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "facts",
						options: `<dl class="hrv-facts">${rows
							.map(([label, value]) => `<dt>${esc(label)}</dt><dd>${esc(value)}</dd>`)
							.join("")}</dl>`,
					},
				],
				primary_action_label: __("Open"),
				primary_action: () => {
					dialog.hide();
					frappe.set_route("Form", block.link[0], block.link[1]);
				},
			});
			dialog.show();
		}
	};
})();
