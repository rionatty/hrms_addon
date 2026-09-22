// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

/* The attendance board.
 *
 * Luuka's attendance question is not "how many were present last
 * quarter". It is "who is on the floor this minute, is the night shift
 * covered, whose hours have turned into overtime, and what do I have to
 * put right before the register closes on the 25th".
 *
 * So the middle of this page is LPL/HR/07 itself — the register they
 * already read, ruled 26th to 25th, drawn from the punches — with the
 * state of the floor above it and the things that need somebody below.
 *
 * One call fills all of it (hrms_addon.hrms_addon.attendance_board.board).
 * Everything here is a read; nothing on this page writes.
 */

frappe.provide("hrms_addon");

// frappe's JS has no month-name helper, and the register's columns are
// read as "26 Aug", so the names are kept here and translated
const HRA_MONTHS = [
	"Jan", "Feb", "Mar", "Apr", "May", "Jun",
	"Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

// The board's own styles.
//
// They live here rather than in hrms_addon.bundle.css because that file
// only reaches the browser after `bench build`, and a page whose entire
// layout waits on a build step ships looking like a list of words when
// the build is skipped or an old bundle is still cached. A page script
// is served as it is, so these arrive with the page that needs them.
//
// Everything is scoped under .hra-board or its own hra- classes. The
// --hra-* colours it reads are the theme's, declared in the bundle, and
// a missing one only costs a colour rather than the layout.
const HRA_BOARD_STYLE = `
/* ── The attendance board ────────────────────────────────────────
   page/attendance_board. The middle of it is LPL/HR/07 — the
   register Luuka already reads, ruled 26th to 25th — so the letters
   get the colours, and everything else stays out of their way.

   Every custom property below is declared in this block: a var()
   that resolves to nothing takes its whole declaration with it
   (rule 2 at the top of this file).
   ──────────────────────────────────────────────────────────────── */
:root {
  --hra-board-gold:       #A9791C;   /* CyveTech gold — off duty     */
  --hra-board-gold-soft:  #FBF1D9;
  --hra-board-danger-soft:#FBE7E6;
  --hra-board-amber-soft: #FCF0DC;
  --hra-board-grey-soft:  #EDEFF2;
  --hra-board-night:      #0A2540;   /* the night shift reads dark   */
  --hra-board-day:        #D6E4F7;
  --hra-board-gap:        12px;
  --hra-board-cell:       26px;      /* one day of the register      */
}

.hra-board { padding: 4px 0 40px; }

.hra-band {
  background: var(--card-bg, #fff);
  border: 1px solid var(--hra-border, #C3D0E0);
  border-radius: 8px;
  margin-bottom: var(--hra-board-gap);
  overflow: hidden;
}
.hra-band-head {
  display: flex; align-items: baseline; gap: 10px;
  padding: 10px 14px;
  background: var(--hra-primary, #14395E);
  color: #fff;
}
.hra-band-head h4 { margin: 0; font-size: 13px; letter-spacing: .04em;
  text-transform: uppercase; color: #fff; }
.hra-band-head .text-muted { color: rgba(255,255,255,.72) !important; font-size: 12px; }
.hra-band-body { padding: 14px; }

/* the big counts */
.hra-figures { display: flex; flex-wrap: wrap; gap: 10px; }
.hra-figure {
  min-width: 104px; padding: 10px 14px;
  border: 1px solid var(--hra-border, #C3D0E0); border-radius: 6px;
  background: var(--hra-wash, #F5F8FC);
}
.hra-figure-value { font-size: 26px; line-height: 1.1; font-weight: 600; color: var(--hra-ink, #1A2733); }
.hra-figure-label { font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
  color: var(--hra-ink-muted, #546678); }
.hra-tone-day   .hra-figure-value { color: var(--hra-primary-mid, #2A5A8C); }
.hra-tone-night .hra-figure-value { color: var(--hra-board-night); }
.hra-tone-warn  .hra-figure-value { color: var(--hra-amber-text, #B45309); }
.hra-tone-bad   .hra-figure-value { color: var(--hra-danger, #A62B25); }
.hra-tone-soft  .hra-figure-value { color: var(--hra-ink-muted, #546678); }

.hra-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.hra-chip {
  padding: 3px 10px; border-radius: 12px; font-size: 12px;
  background: var(--hra-pale, #EEF3F9); border: 1px solid var(--hra-border, #C3D0E0);
}

/* how far through the cycle */
.hra-progress {
  position: relative; height: 22px; margin-bottom: 12px;
  background: var(--hra-board-grey-soft); border-radius: 11px; overflow: hidden;
}
.hra-progress-fill { height: 100%; background: var(--hra-primary-light, #3B78B5); }
.hra-progress span {
  position: absolute; inset: 0; display: flex; align-items: center;
  justify-content: center; font-size: 11px; color: var(--hra-ink, #1A2733);
}

/* one column per day of the cycle */
.hra-strip {
  display: flex; align-items: flex-end; gap: 2px;
  height: 92px; margin-top: 14px; padding-bottom: 14px;
  border-bottom: 1px solid var(--hra-border, #C3D0E0);
}
.hra-day { position: relative; flex: 1 1 0; height: 100%; min-width: 10px; }
.hra-day-bar {
  position: absolute; bottom: 0; left: 0; right: 0;
  background: var(--hra-primary-light, #3B78B5); border-radius: 2px 2px 0 0;
}
.hra-day-night {
  position: absolute; bottom: 0; left: 25%; right: 25%;
  background: var(--hra-board-night); border-radius: 2px 2px 0 0; opacity: .85;
}
.hra-band-full .hra-day-bar, .hra-day-bar.hra-band-full { background: var(--hra-primary-light, #3B78B5); }
.hra-day-bar.hra-band-thin { background: var(--hra-amber-text, #B45309); }
.hra-day-bar.hra-band-short { background: var(--hra-danger, #A62B25); }
.hra-day-bar.hra-band-none { background: var(--hra-border, #C3D0E0); }
.hra-day-label {
  position: absolute; bottom: -14px; left: 0; right: 0;
  text-align: center; font-size: 9px; color: var(--hra-ink-muted, #546678);
}
.hra-day.hra-today .hra-day-label { color: var(--hra-primary, #14395E); font-weight: 700; }
.hra-warn { margin-top: 18px; font-size: 12px; color: var(--hra-amber-text, #B45309); }
.hra-clear { color: var(--hra-success, #256F3A); }

/* what needs a person */
.hra-exceptions { display: flex; flex-wrap: wrap; gap: 10px; }
.hra-exception {
  display: grid; grid-template-columns: auto 1fr; gap: 0 10px;
  align-items: center; text-align: left;
  min-width: 260px; max-width: 360px; padding: 10px 12px;
  border: 1px solid var(--hra-border, #C3D0E0); border-left-width: 4px;
  border-radius: 6px; background: var(--hra-wash, #F5F8FC); cursor: pointer;
}
.hra-exception:hover { background: var(--hra-selected, #D6E4F7); }
.hra-severity-high { border-left-color: var(--hra-danger, #A62B25); }
.hra-severity-medium { border-left-color: var(--hra-amber-text, #B45309); }
.hra-exception-count { grid-row: span 2; font-size: 24px; font-weight: 600;
  color: var(--hra-ink, #1A2733); }
.hra-exception-label { font-size: 13px; color: var(--hra-ink, #1A2733); }
.hra-exception-why { font-size: 11px; color: var(--hra-ink-muted, #546678); }

/* the register */
.hra-legends { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 10px;
  font-size: 11px; color: var(--hra-ink-muted, #546678); }
.hra-legend i { display: inline-block; width: 20px; text-align: center;
  font-style: normal; font-weight: 700; border-radius: 3px; margin-right: 4px; }
.hra-register-scroll { overflow: auto; max-height: 62vh; border: 1px solid var(--hra-border, #C3D0E0); }
.hra-register { border-collapse: separate; border-spacing: 0; font-size: 11px;
  width: 100%; }
.hra-register th, .hra-register td {
  border-bottom: 1px solid var(--hra-border, #C3D0E0); padding: 0; text-align: center;
  height: var(--hra-board-cell); min-width: var(--hra-board-cell);
}
.hra-register thead th {
  position: sticky; top: 0; z-index: 3;
  background: var(--hra-primary-dark, #0A2540); color: #fff; font-weight: 600;
}
.hra-register th.hra-who {
  position: sticky; left: 0; z-index: 4;
  min-width: 190px; max-width: 190px; padding: 2px 8px;
  text-align: left; background: var(--card-bg, #fff);
}
.hra-register thead th.hra-who {
  position: sticky; top: 0; left: 0; z-index: 5;
  background: var(--hra-primary-dark, #0A2540);
}
.hra-register th.hra-who small { display: block; font-weight: 400; font-size: 10px; }
.hra-register tbody tr:nth-child(even) th.hra-who { background: var(--hra-pale, #EEF3F9); }
.hra-register tbody tr:nth-child(even) td { background: var(--hra-pale, #EEF3F9); }
.hra-day-col.hra-today { background: var(--hra-primary-light, #3B78B5); }
.hra-cell { cursor: pointer; font-weight: 600; }
.hra-cell:hover { outline: 2px solid var(--hra-accent, #0A6ED1); outline-offset: -2px; }
.hra-sum { font-weight: 600; background: var(--hra-readonly, #EDF1F7); min-width: 40px; }
.hra-tally th.hra-who { font-size: 10px; text-transform: uppercase;
  letter-spacing: .03em; color: var(--hra-ink-muted, #546678); }
.hra-register tfoot td { background: var(--hra-readonly, #EDF1F7); font-weight: 600; }

/* the letters of LPL/HR/07.

   Written as 'table td.hra-code-X' on purpose: the zebra rule above is
   '.hra-register tbody tr:nth-child(even) td', which is just as specific
   and comes first, so a plain '.hra-code-N' lost every second row and
   the night shift disappeared into the stripe. */
.hra-register tbody tr td.hra-code-M, .hra-legend i.hra-code-M {
  background: var(--hra-board-day); color: var(--hra-primary-dark, #0A2540); }
.hra-register tbody tr td.hra-code-N, .hra-legend i.hra-code-N {
  background: var(--hra-board-night); color: #fff; }
.hra-register tbody tr td.hra-code-A, .hra-legend i.hra-code-A {
  background: var(--hra-board-danger-soft); color: var(--hra-danger, #A62B25); }
.hra-register tbody tr td.hra-code-S, .hra-legend i.hra-code-S {
  background: var(--hra-board-amber-soft); color: var(--hra-amber-text, #B45309); }
.hra-register tbody tr td.hra-code-L, .hra-legend i.hra-code-L {
  background: var(--hra-pale, #EEF3F9); color: var(--hra-ink-muted, #546678); }
.hra-register tbody tr td.hra-code-WO, .hra-legend i.hra-code-WO {
  background: var(--hra-board-grey-soft); color: var(--hra-ink-muted, #546678); }
.hra-register tbody tr td.hra-code-O, .hra-legend i.hra-code-O {
  background: var(--hra-board-gold-soft); color: var(--hra-board-gold); }

/* the plants, side by side */
.hra-plants tbody tr { cursor: pointer; }
.hra-plants tbody tr:hover td { background: var(--hra-selected, #D6E4F7); }
.hra-plants small { display: block; font-size: 10px; }
.hra-meter-cell { display: flex; align-items: center; gap: 8px; }
.hra-meter { flex: 1 1 auto; min-width: 90px; height: 8px; border-radius: 4px;
  background: var(--hra-board-grey-soft); overflow: hidden; }
.hra-meter-fill { height: 100%; background: var(--hra-primary-light, #3B78B5); }
.hra-meter-fill.hra-band-thin { background: var(--hra-amber-text, #B45309); }
.hra-meter-fill.hra-band-short { background: var(--hra-danger, #A62B25); }
.hra-meter-fill.hra-band-none { background: var(--hra-border, #C3D0E0); }
.hra-plants-note { font-size: 11px; margin-top: 8px; }

/* the machines, and the plain tables */
.hra-table { width: 100%; font-size: 12px; }
.hra-table th { font-size: 11px; text-transform: uppercase; letter-spacing: .03em;
  color: var(--hra-ink-muted, #546678); font-weight: 600; padding: 4px 6px; }
.hra-table td { padding: 4px 6px; border-top: 1px solid var(--hra-border, #C3D0E0); }
.hra-dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%;
  margin-right: 6px; }
.hra-health-healthy { background: var(--hra-success, #256F3A); }
.hra-health-quiet { background: var(--hra-amber-text, #B45309); }
.hra-health-silent { background: var(--hra-danger, #A62B25); }
.hra-health-never-heard-from { background: var(--hra-border-strong, #7E93AD); }
.hra-standing-into-overtime td { background: var(--hra-board-amber-soft); }
.hra-standing-over-a-full-shift td { background: var(--hra-board-danger-soft); }
.hra-board-foot { font-size: 11px; text-align: right; }

/* dark mode: the surfaces come from Frappe, the letters keep their meaning */
html[data-theme="dark"] .hra-band { background: var(--card-bg); }
html[data-theme="dark"] .hra-figure,
html[data-theme="dark"] .hra-exception { background: transparent; }
html[data-theme="dark"] .hra-register th.hra-who { background: var(--card-bg); }
`;

function hra_board_style() {
	if (document.getElementById("hra-board-style")) return;
	const sheet = document.createElement("style");
	sheet.id = "hra-board-style";
	sheet.textContent = HRA_BOARD_STYLE;
	document.head.appendChild(sheet);
}

frappe.pages["attendance-board"].on_page_load = function (wrapper) {
	hra_board_style();
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Attendance Board"),
		single_column: true,
	});
	wrapper.board = new hrms_addon.AttendanceBoard(page);
};

frappe.pages["attendance-board"].on_page_show = function (wrapper) {
	if (wrapper.board) wrapper.board.refresh();
};

hrms_addon.AttendanceBoard = class AttendanceBoard {
	constructor(page) {
		this.page = page;
		this.every_minute = null;
		this.make_filters();
		this.make_menu();
		this.body = $('<div class="hra-board"></div>').appendTo(this.page.main);
		this.refresh();
	}

	// ── what the board is looking at ──────────────────────────────
	make_filters() {
		this.cycle = this.page.add_field({
			fieldtype: "Select",
			label: __("Cycle"),
			fieldname: "cycle",
			options: this.cycles(),
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

	// The cycle is named after the month it ENDS in, the way the
	// register is: the one running now, and the year behind it.
	cycles() {
		const today = frappe.datetime.now_date(true);
		let year = today.getFullYear();
		let month = today.getMonth() + 1;
		// from the 26th the days belong to the month after
		if (today.getDate() >= 26) {
			month += 1;
			if (month > 12) {
				month = 1;
				year += 1;
			}
		}
		const options = [];
		for (let back = 0; back < 13; back++) {
			let m = month - back;
			let y = year;
			while (m < 1) {
				m += 12;
				y -= 1;
			}
			const value = `${y}-${String(m).padStart(2, "0")}`;
			options.push({ value: value, label: this.cycle_label(y, m) });
		}
		return options;
	}

	cycle_label(year, month) {
		const ends = new Date(year, month - 1, 25);
		const opens = new Date(year, month - 2, 26);
		const short = (date) => `${date.getDate()} ${__(HRA_MONTHS[date.getMonth()])}`;
		return `${short(opens)} – ${short(ends)} ${ends.getFullYear()}`;
	}

	make_menu() {
		this.page.add_menu_item(__("Stop refreshing"), () => this.set_ticking(false));
		this.page.add_menu_item(__("Refresh every minute"), () => this.set_ticking(true));
		this.page.add_menu_item(__("Punches"), () =>
			frappe.set_route("List", "Attendance Device Log")
		);
		this.page.add_menu_item(__("Clocking machines"), () =>
			frappe.set_route("List", "Attendance Device")
		);
	}

	set_ticking(on) {
		if (this.every_minute) clearInterval(this.every_minute);
		this.every_minute = null;
		if (on) {
			this.every_minute = setInterval(() => {
				if (frappe.get_route()[1] === "attendance-board") this.refresh();
			}, 60000);
			frappe.show_alert({ message: __("Refreshing every minute"), indicator: "blue" });
		} else {
			frappe.show_alert({ message: __("Stopped refreshing"), indicator: "orange" });
		}
	}

	refresh() {
		if (this.asking) return;
		this.asking = true;
		frappe
			.xcall("hrms_addon.hrms_addon.attendance_board.board", {
				cycle: this.cycle ? this.cycle.get_value() : null,
				branch: this.branch ? this.branch.get_value() : null,
				department: this.department ? this.department.get_value() : null,
			})
			.then((board) => this.draw(board))
			.finally(() => {
				this.asking = false;
			});
	}

	// ── drawing ───────────────────────────────────────────────────
	draw(board) {
		this.board = board;
		this.body.empty();
		this.floor(board);
		this.cycle_so_far(board);
		this.plants(board);
		this.needs_a_person(board);
		this.register(board);
		this.machines(board);
		this.body.append(
			`<div class="hra-board-foot text-muted">${__("Read at {0}", [
				frappe.datetime.str_to_user(board.read_at),
			])}</div>`
		);
	}

	band(title, subtitle) {
		return $(`
			<section class="hra-band">
				<header class="hra-band-head">
					<h4>${frappe.utils.escape_html(title)}</h4>
					<span class="text-muted">${subtitle ? frappe.utils.escape_html(subtitle) : ""}</span>
				</header>
				<div class="hra-band-body"></div>
			</section>
		`).appendTo(this.body);
	}

	// 1. the floor, this minute
	floor(board) {
		const tally = board.floor.tally;
		const band = this.band(
			__("On the floor now"),
			__("{0} inside", [tally.inside])
		);
		const counts = [
			{ label: __("Inside"), value: tally.inside, tone: "ink" },
			{ label: __("Day"), value: tally.day, tone: "day" },
			{ label: __("Night"), value: tally.night, tone: "night" },
			{ label: __("Into overtime"), value: tally.into_overtime, tone: "warn" },
			{ label: __("Over a full shift"), value: tally.over_a_shift, tone: "bad" },
		];
		const figures = counts
			.map(
				(one) => `
					<div class="hra-figure hra-tone-${one.tone}">
						<div class="hra-figure-value">${one.value}</div>
						<div class="hra-figure-label">${frappe.utils.escape_html(one.label)}</div>
					</div>`
			)
			.join("");
		const plants = (board.floor.branches || [])
			.map(
				(seat) => `
					<span class="hra-chip">
						<b>${frappe.utils.escape_html(seat.branch)}</b>
						${seat.inside}
						<span class="text-muted">(${seat.day}${__("d")}/${seat.night}${__("n")})</span>
					</span>`
			)
			.join("");
		const longest = (board.floor.people || [])
			.slice(0, 8)
			.map(
				(one) => `
					<tr class="hra-standing-${one.standing.replace(/ /g, "-").toLowerCase()}">
						<td><a href="/app/employee/${encodeURIComponent(one.employee)}">${frappe.utils.escape_html(
							one.employee_name || one.employee
						)}</a></td>
						<td class="text-muted">${frappe.utils.escape_html(one.branch || "")}</td>
						<td>${one.night ? __("Night") : __("Day")}</td>
						<td class="text-right"><b>${one.hours.toFixed(1)}</b> ${__("h")}</td>
						<td>${frappe.utils.escape_html(__(one.standing))}</td>
					</tr>`
			)
			.join("");
		band.find(".hra-band-body").html(`
			<div class="hra-figures">${figures}</div>
			${plants ? `<div class="hra-chips">${plants}</div>` : ""}
			${
				longest
					? `<table class="hra-table hra-longest">
						<thead><tr>
							<th>${__("Longest inside")}</th><th>${__("Plant")}</th>
							<th>${__("Shift")}</th><th class="text-right">${__("Hours")}</th><th></th>
						</tr></thead>
						<tbody>${longest}</tbody>
					</table>`
					: `<div class="text-muted">${__("Nobody is clocked in.")}</div>`
			}
		`);
	}

	// 2. the cycle so far
	cycle_so_far(board) {
		const cycle = board.cycle;
		const totals = board.cycle_totals;
		const band = this.band(__("The cycle"), cycle.label);
		const through = Math.round((cycle.progress.through || 0) * 100);
		const strip = (board.per_day || [])
			.map((day) => {
				const height = day.rate === null ? 4 : Math.max(Math.round(day.rate * 100), 4);
				const today = day.date === cycle.today ? " hra-today" : "";
				const title = __("{0}: {1} worked, {2} absent, {3} on nights", [
					frappe.datetime.str_to_user(day.date),
					day.worked,
					day.absent,
					day.night,
				]);
				return `<div class="hra-day${today}" title="${frappe.utils.escape_html(title)}">
					<div class="hra-day-bar hra-band-${day.band || "none"}" style="height:${height}%"></div>
					<div class="hra-day-night" style="height:${
						day.worked ? Math.round((day.night / day.worked) * 100) : 0
					}%"></div>
					<span class="hra-day-label">${day.date.slice(8)}</span>
				</div>`;
			})
			.join("");
		const short = board.register.nights_short || [];
		band.find(".hra-band-body").html(`
			<div class="hra-progress" title="${__("Day {0} of {1}", [
				cycle.progress.day,
				cycle.progress.of,
			])}">
				<div class="hra-progress-fill" style="width:${through}%"></div>
				<span>${__("Day {0} of {1}", [cycle.progress.day, cycle.progress.of])}</span>
			</div>
			<div class="hra-figures">
				<div class="hra-figure hra-tone-ink">
					<div class="hra-figure-value">${totals.M + totals.N}</div>
					<div class="hra-figure-label">${__("Shifts worked")}</div>
				</div>
				<div class="hra-figure hra-tone-night">
					<div class="hra-figure-value">${totals.N}</div>
					<div class="hra-figure-label">${__("On nights")}</div>
				</div>
				<div class="hra-figure hra-tone-bad">
					<div class="hra-figure-value">${totals.A}</div>
					<div class="hra-figure-label">${__("Absent")}</div>
				</div>
				<div class="hra-figure hra-tone-soft">
					<div class="hra-figure-value">${totals.L + totals.S}</div>
					<div class="hra-figure-label">${__("On leave")}</div>
				</div>
				<div class="hra-figure hra-tone-soft">
					<div class="hra-figure-value">${totals.O}</div>
					<div class="hra-figure-label">${__("Off duty")}</div>
				</div>
				<div class="hra-figure hra-tone-ink">
					<div class="hra-figure-value">${
						totals.rate === null ? "—" : Math.round(totals.rate * 100) + "%"
					}</div>
					<div class="hra-figure-label">${__("Turned up")}</div>
				</div>
			</div>
			<div class="hra-strip">${strip}</div>
			${
				short.length
					? `<div class="hra-warn">${__("{0} day(s) of this cycle had nobody on nights.", [
							short.length,
					  ])}</div>`
					: ""
			}
		`);
	}

	// 3. the plants, side by side
	//
	// Only when the board is showing all of them: comparing one plant
	// with itself is a row, not a comparison. Each plant is run by its
	// own people, so this is the band that says which of them needs
	// somebody today — and clicking one takes the whole board there.
	plants(board) {
		const rows = board.plants || [];
		if (this.branch && this.branch.get_value()) return;
		if (rows.length < 2) return;
		const watching = rows.filter((seat) => seat.machines_watch > 0).length;
		const band = this.band(
			__("The plants"),
			watching
				? __("{0} plant(s) with a machine to look at", [watching])
				: __("{0} plants", [rows.length])
		);
		const lines = rows
			.map(
				(seat) => `
				<tr class="hra-plant" data-branch="${frappe.utils.escape_html(seat.branch)}">
					<td><b>${frappe.utils.escape_html(seat.branch)}</b>
						<small class="text-muted">${__("{0} on the register", [seat.people])}</small></td>
					<td class="text-right">${seat.inside}
						<small class="text-muted">${seat.inside_night ? __("{0} on nights", [
							seat.inside_night,
						]) : ""}</small></td>
					<td class="text-right">${seat.worked}</td>
					<td class="text-right">${seat.night}</td>
					<td class="text-right">${seat.absent || ""}</td>
					<td class="hra-meter-cell">
						<div class="hra-meter">
							<div class="hra-meter-fill hra-band-${seat.band || "none"}"
								style="width:${seat.rate === null ? 0 : Math.round(seat.rate * 100)}%"></div>
						</div>
						<span>${seat.rate === null ? "—" : Math.round(seat.rate * 100) + "%"}</span>
					</td>
					<td class="text-right">${
						seat.machines_watch
							? `<span class="hra-dot hra-health-silent"></span>${seat.machines_watch} ${__(
									"of"
							  )} ${seat.machines}`
							: `<span class="text-muted">${seat.machines}</span>`
					}</td>
				</tr>`
			)
			.join("");
		band.find(".hra-band-body").html(`
			<table class="hra-table hra-plants">
				<thead><tr>
					<th>${__("Plant")}</th>
					<th class="text-right">${__("Inside now")}</th>
					<th class="text-right">${__("Shifts")}</th>
					<th class="text-right">${__("Nights")}</th>
					<th class="text-right">${__("Absent")}</th>
					<th>${__("Turned up")}</th>
					<th class="text-right">${__("Machines")}</th>
				</tr></thead>
				<tbody>${lines}</tbody>
			</table>
			<div class="text-muted hra-plants-note">${__(
				"Worst turnout first. Click a plant to take the whole board there."
			)}</div>
		`);
		band.find(".hra-plant").on("click", (event) => {
			const plant = $(event.currentTarget).attr("data-branch");
			if (plant && plant !== "Unplaced") this.branch.set_value(plant);
		});
	}

	// 4. what needs a person
	needs_a_person(board) {
		const rows = (board.exceptions || []).filter((row) => row.count > 0);
		const band = this.band(
			__("Needs a person"),
			rows.length ? __("{0} kind(s)", [rows.length]) : __("nothing waiting")
		);
		if (!rows.length) {
			band.find(".hra-band-body").html(
				`<div class="hra-clear">${__("Nothing is waiting. The register is clean.")}</div>`
			);
			return;
		}
		const chips = rows
			.map(
				(row, index) => `
				<button class="hra-exception hra-severity-${row.severity}" data-exception="${index}">
					<span class="hra-exception-count">${row.count}</span>
					<span class="hra-exception-label">${frappe.utils.escape_html(__(row.label))}</span>
					<span class="hra-exception-why">${frappe.utils.escape_html(__(row.why))}</span>
				</button>`
			)
			.join("");
		band.find(".hra-band-body").html(`<div class="hra-exceptions">${chips}</div>`);
		band.find("[data-exception]").on("click", (event) => {
			const row = rows[parseInt($(event.currentTarget).attr("data-exception"), 10)];
			if (row && row.route) {
				frappe.set_route("List", row.route.doctype, row.route.filters || {});
			}
		});
	}

	// 5. the register itself — LPL/HR/07, from the punches
	register(board) {
		const days = board.cycle.days || [];
		const band = this.band(
			__("The register"),
			board.register.shown < board.register.of
				? __("{0} of {1} people — narrow by plant or department to see the rest", [
						board.register.shown,
						board.register.of,
				  ])
				: __("{0} people", [board.register.shown])
		);
		const head = days
			.map((day) => {
				const today = day === board.cycle.today ? " hra-today" : "";
				return `<th class="hra-day-col${today}" title="${frappe.utils.escape_html(
					frappe.datetime.str_to_user(day)
				)}">${day.slice(8)}</th>`;
			})
			.join("");
		const body = (board.register.rows || [])
			.map(
				(row) => `
				<tr>
					<th class="hra-who">
						<a href="/app/employee/${encodeURIComponent(row.employee)}">${frappe.utils.escape_html(
							row.employee_name || row.employee
						)}</a>
						<small class="text-muted">${frappe.utils.escape_html(
							[row.department, row.employment].filter(Boolean).join(" · ")
						)}</small>
					</th>
					${row.codes
						.map(
							(code, index) =>
								`<td class="hra-cell hra-code-${code || "none"}" data-employee="${
									row.employee
								}" data-date="${days[index]}">${code}</td>`
						)
						.join("")}
					<td class="hra-sum">${row.worked}</td>
					<td class="hra-sum">${row.overtime}</td>
				</tr>`
			)
			.join("");
		const feet = (board.register.tallies || [])
			.map(
				(line) => `
				<tr class="hra-tally">
					<th class="hra-who">${frappe.utils.escape_html(__(line.label))}</th>
					${line.counts.map((count) => `<td>${count || ""}</td>`).join("")}
					<td class="hra-sum"></td><td class="hra-sum"></td>
				</tr>`
			)
			.join("");
		const legend = (board.codes || [])
			.map(
				(one) =>
					`<span class="hra-legend"><i class="hra-code-${one.code}">${one.code}</i> ${frappe.utils.escape_html(
						__(one.meaning)
					)}</span>`
			)
			.join("");
		band.find(".hra-band-body").html(`
			<div class="hra-legends">${legend}</div>
			<div class="hra-register-scroll">
				<table class="hra-register">
					<thead><tr>
						<th class="hra-who">${__("Name")}</th>
						${head}
						<th class="hra-sum">${__("Days")}</th>
						<th class="hra-sum">${__("OT")}</th>
					</tr></thead>
					<tbody>${body}</tbody>
					<tfoot>${feet}</tfoot>
				</table>
			</div>
		`);
		band.find(".hra-cell").on("click", (event) => {
			const cell = $(event.currentTarget);
			frappe.set_route("List", "Attendance", {
				employee: cell.attr("data-employee"),
				attendance_date: cell.attr("data-date"),
			});
		});
	}

	// 6. the machines
	machines(board) {
		const machines = board.machines || [];
		const band = this.band(__("The machines"), __("{0} on the wall", [machines.length]));
		if (!machines.length) {
			band.find(".hra-band-body").html(
				`<div class="text-muted">${__("No clocking machine has been set up yet.")}</div>`
			);
			return;
		}
		const rows = machines
			.map(
				(one) => `
				<tr>
					<td><span class="hra-dot hra-health-${one.health
						.replace(/ /g, "-")
						.toLowerCase()}"></span>
						<a href="/app/attendance-device/${encodeURIComponent(one.device)}">${frappe.utils.escape_html(
							one.device_name
						)}</a></td>
					<td class="text-muted">${frappe.utils.escape_html(one.branch || __("no plant set"))}</td>
					<td class="text-muted">${frappe.utils.escape_html(one.direction || __("no direction set"))}</td>
					<td class="text-muted">${frappe.utils.escape_html(one.source || "")}</td>
					<td>${
						one.last_seen
							? frappe.datetime.comment_when(one.last_seen)
							: `<span class="text-muted">${__("never")}</span>`
					}</td>
					<td class="text-right">${one.punches_today}</td>
				</tr>`
			)
			.join("");
		band.find(".hra-band-body").html(`
			<table class="hra-table">
				<thead><tr>
					<th>${__("Machine")}</th><th>${__("Plant")}</th><th>${__("Direction")}</th>
					<th>${__("Fed by")}</th><th>${__("Last punch")}</th>
					<th class="text-right">${__("Today")}</th>
				</tr></thead>
				<tbody>${rows}</tbody>
			</table>
		`);
	}
};
