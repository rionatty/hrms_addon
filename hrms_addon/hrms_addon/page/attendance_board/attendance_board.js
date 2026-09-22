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

frappe.pages["attendance-board"].on_page_load = function (wrapper) {
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

	// 3. what needs a person
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

	// 4. the register itself — LPL/HR/07, from the punches
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

	// 5. the machines
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
