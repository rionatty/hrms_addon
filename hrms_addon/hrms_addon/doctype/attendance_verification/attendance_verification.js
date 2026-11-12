// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// A branch's attendance for a payroll, signed off by its General Manager before payroll pays it
// (attendance_verification.py). The figures are read again on every save while the sheet is with HR: Get Attendance
// saves. A monthly sheet's Month is picked from the company's open payroll months and its dates follow it; a weekly
// sheet's days run on from the branch's last weekly sheet.
const HA_VERIFY_MONTHS = "hrms_addon.hrms_addon.payroll_months.open_months";
const HA_VERIFY_WEEKLY = "hrms_addon.hrms_addon.attendance_verification.weekly_dates";
const HA_VERIFY_HEADER = ["company", "branch", "pay_kind", "pay_period", "from_date", "to_date"];
// the company's open months once they are here, false if they could not be had; and whose they are
let ha_verify_months = null;
let ha_verify_months_of = null;

frappe.ui.form.on("Attendance Verification", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
	},
	refresh(frm) {
		ha_verify_months_load(frm);
		ha_verify_header(frm);
		ha_verify_intro(frm);
		ha_verify_pages(frm);
		ha_verify_hours_column(frm);
		// whoever may save it now: HR while it is a draft, the General Manager while it waits
		if (frm.doc.docstatus === 0 && !frappe.workflow.is_read_only(frm.doctype, frm.docname)) {
			frm.add_custom_button(__("Get Attendance"), () => frm.save());
		}
		ha_verify_mark_button(frm);
	},
	company(frm) {
		ha_verify_months_load(frm);
		ha_verify_weekly(frm);
	},
	branch: ha_verify_weekly,
	pay_kind(frm) {
		ha_verify_header(frm);
		ha_verify_hours_column(frm);
		if (frm.doc.pay_kind === "Monthly") ha_verify_month_dates(frm, true);
		else ha_verify_weekly(frm);
	},
	pay_period(frm) {
		ha_verify_month_dates(frm, false);
	},
	from_date(frm) {
		ha_verify_week_end(frm);
	},
});

// The page buttons of both tables, shown whenever a table has rows, one page or many (Luuka, 8 Nov 2026). Frappe draws
// them in a table's footer only past one page (grid_pagination.js render_pagination), and hides the footer of a
// read-only table drawn with less than a page of rows, as a new sheet's are, then never shows it again (grid.js
// setup_toolbar). Each time a table is drawn (Frappe's grid says "change" when it is), its footer shows while it has
// rows, and a table of one page gets Frappe's own buttons, 1 of 1.
const HA_VERIFY_TABLES = ["employees", "issues"];

function ha_verify_pages(frm) {
	HA_VERIFY_TABLES.forEach((fieldname) => {
		const grid = frm.fields_dict[fieldname] && frm.fields_dict[fieldname].grid;
		if (!grid || !grid.wrapper) return;
		const show = () => {
			const pages = grid.grid_pagination;
			if (!pages || grid.is_editable()) return;
			const count = (grid.data || []).length;
			grid.wrapper.find(".grid-footer").toggleClass("hidden", !count);
			// drawn once: a change from inside the table (the page box) must not draw them again under the cursor
			if (count && count <= pages.page_length && !grid.wrapper.find(".grid-pagination").children().length) {
				ha_verify_one_page(pages);
			}
		};
		grid.wrapper.off("change.ha_verify_pages").on("change.ha_verify_pages", show);
		show();
	});
}

// Frappe's page buttons for a table of one page: render_pagination draws them once the rows pass a page
function ha_verify_one_page(pages) {
	const length = pages.page_length;
	pages.page_length = 0;
	try {
		pages.render_pagination();
	} finally {
		pages.page_length = length;
	}
}

function ha_verify_get(method, args) {
	// fetch, not frappe.call: a list that cannot be had leaves the dates to type, with no dialog
	const query = new URLSearchParams(args).toString();
	return fetch("/api/method/" + method + "?" + query, {
		credentials: "same-origin",
		cache: "no-store",
		headers: { Accept: "application/json" },
	})
		.then((response) => (response.ok ? response.json() : null))
		.catch(() => null)
		.then((body) => (body ? body.message : null));
}

function ha_verify_months_load(frm) {
	const company = frm.doc.company || "";
	// months close and open, so each sheet asks again
	const asked = company + "|" + frm.doc.name;
	if (ha_verify_months_of === asked && ha_verify_months !== null) {
		ha_verify_header(frm);
		return;
	}
	ha_verify_months_of = asked;
	ha_verify_months = null;
	if (!company) return;
	ha_verify_get(HA_VERIFY_MONTHS, { company }).then((months) => {
		// the company changed while it was on its way: the later answer counts
		if (ha_verify_months_of !== asked) return;
		ha_verify_months = Array.isArray(months) ? months : false;
		ha_verify_header(frm);
		if (frm.is_new() && frm.doc.pay_kind === "Monthly") ha_verify_month_dates(frm, true);
	});
}

// what can be changed: the header while the sheet is a draft with HR; a monthly sheet's dates follow its Month
function ha_verify_header(frm) {
	const open = frm.doc.docstatus === 0 && (frm.doc.workflow_state || "Draft") === "Draft";
	frm.toggle_enable(HA_VERIFY_HEADER, open);
	const monthly = frm.doc.pay_kind === "Monthly";
	const listed = Array.isArray(ha_verify_months);
	if (open) frm.toggle_enable(["from_date", "to_date"], !(monthly && listed));
	if (!monthly || !listed) return;
	const names = ha_verify_months.map((month) => month.name);
	const kept = frm.doc.pay_period;
	// a sheet of a month since closed keeps its month
	if (kept && !names.includes(kept)) names.push(kept);
	frm.set_df_property("pay_period", "options", ["", ...names].join("\n"));
	frm.set_df_property(
		"pay_period",
		"description",
		ha_verify_months.length ? "" : __("No open payroll month for this company. Open or add one in Payroll Period.")
	);
	frm.refresh_field("pay_period");
}

// the Month's dates; a new sheet starts on the first month still open
function ha_verify_month_dates(frm, pick_first) {
	if (frm.doc.docstatus !== 0 || frm.doc.pay_kind !== "Monthly" || !Array.isArray(ha_verify_months)) return;
	if (pick_first && !frm.doc.pay_period && ha_verify_months.length) {
		frm.set_value("pay_period", ha_verify_months[0].name);
		return;
	}
	const month = ha_verify_months.find((row) => row.name === frm.doc.pay_period);
	if (!month) return;
	if (frm.doc.from_date !== month.start) frm.set_value("from_date", month.start);
	if (frm.doc.to_date !== month.end) frm.set_value("to_date", month.end);
}

// a new weekly sheet runs on from the branch's last one
function ha_verify_weekly(frm) {
	if (!frm.is_new() || frm.doc.pay_kind !== "Weekly" || !frm.doc.company || !frm.doc.branch) return;
	if (frm.doc.pay_period) frm.set_value("pay_period", "");
	const asked = frm.doc.company + "|" + frm.doc.branch;
	ha_verify_get(HA_VERIFY_WEEKLY, { company: frm.doc.company, branch: frm.doc.branch }).then((dates) => {
		if (!dates || frm.doc.company + "|" + frm.doc.branch !== asked || frm.doc.pay_kind !== "Weekly") return;
		// From first: its handler fills a week, then the To handed over is written over it
		frm.set_value({ from_date: dates.from_date, to_date: dates.to_date });
	});
}

// Hours Worked is a weekly sheet's column (Luuka, 12 Nov 2026: "for weekly add no of hours worked"): the casuals are
// paid by the hour. Frappe's grid keeps the change to this form, and redraws only when it changes.
function ha_verify_hours_column(frm) {
	const grid = frm.fields_dict.employees && frm.fields_dict.employees.grid;
	if (!grid || !grid.set_column_disp_in_list_view) return;
	const hide = frm.doc.pay_kind === "Weekly" ? 0 : 1;
	if (((grid.column_disp_overrides || {}).hours_worked || 0) === hide) return;
	grid.set_column_disp_in_list_view("hours_worked", !hide);
}

// a weekly sheet's To follows the From picked: the week of seven days from it (Luuka, 11 Nov 2026: "the date should
// auto fill the week once the from date is selected"). To can still be changed after.
function ha_verify_week_end(frm) {
	if (frm.doc.docstatus !== 0 || frm.doc.pay_kind !== "Weekly" || !frm.doc.from_date) return;
	const to = frappe.datetime.add_days(frm.doc.from_date, 6);
	if (frm.doc.to_date !== to) frm.set_value("to_date", to);
}

// Mark Attendance (Luuka, 8 Nov 2026): the days on the sheet nobody marked, of the sheet's own people and on its own
// days only, marked as picked (attendance_verification.days_to_mark, mark_days). Days already marked stay as they are.
const HA_VERIFY_MARK = "hrms_addon.hrms_addon.attendance_verification.";
const HA_VERIFY_LEAVE = ["On Leave", "Half Day"];

function ha_verify_mark_button(frm) {
	const doc = frm.doc;
	const with_hr = doc.docstatus === 0 && (doc.workflow_state || "Draft") === "Draft";
	if (frm.is_new() || !with_hr || !cint(doc.total_not_marked)) return;
	if (frappe.workflow.is_read_only(frm.doctype, frm.docname)) return;
	frm.add_custom_button(__("Mark Attendance"), () => ha_verify_mark(frm));
}

function ha_verify_mark(frm) {
	// the days are read from the sheet as it is saved
	if (frm.is_dirty()) {
		frm.save().then(() => ha_verify_mark(frm));
		return;
	}
	frappe
		.call({ method: HA_VERIFY_MARK + "days_to_mark", args: { name: frm.doc.name }, freeze: true })
		.then((r) => {
			const found = r && r.message;
			if (!found || !(found.people || []).length) {
				frappe.msgprint(__("Every day on the sheet is marked. Press Get Attendance to read it again."));
				return;
			}
			ha_verify_mark_dialog(frm, found);
		});
}

function ha_verify_mark_dialog(frm, found) {
	const dialog = new frappe.ui.Dialog({
		title: __("Mark Attendance"),
		size: "large",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "about",
				options: `<p class="text-muted">${__("Only days nobody marked are marked. Marked days stay as they are.")}</p>`,
			},
			{
				fieldtype: "Select",
				fieldname: "status",
				label: __("Status"),
				options: (found.statuses || ["Present"]).join("\n"),
				default: "Present",
				reqd: 1,
			},
			{
				fieldtype: "Link",
				fieldname: "leave_type",
				label: __("Leave Type"),
				options: "Leave Type",
				depends_on: `eval:${JSON.stringify(HA_VERIFY_LEAVE)}.includes(doc.status)`,
				mandatory_depends_on: "eval:doc.status === 'On Leave'",
			},
			{
				fieldtype: "MultiCheck",
				fieldname: "employees",
				label: __("People"),
				select_all: 1,
				columns: 2,
				sort_options: false,
				// Frappe's MultiCheck writes a label in as HTML: a name is escaped
				options: found.people.map((person) => ({
					label: `${frappe.utils.escape_html(person.employee_name)} (${person.days.length})`,
					value: person.employee,
					checked: 1,
				})),
			},
			{
				fieldtype: "MultiCheck",
				fieldname: "days",
				label: __("Days"),
				select_all: 1,
				columns: 4,
				sort_options: false,
				options: found.days.map((day) => ({
					label: `${moment(day).format("ddd")} ${frappe.datetime.str_to_user(day)}`,
					value: day,
					checked: 1,
				})),
			},
		],
		primary_action_label: __("Mark"),
		primary_action(values) {
			const employees = values.employees || [];
			const days = values.days || [];
			if (!employees.length || !days.length) {
				frappe.msgprint(__("Pick the people and the days to mark."));
				return;
			}
			const args = { name: frm.doc.name, status: values.status, employees: employees, days: days };
			// an empty value is left out: Frappe refuses an empty string for a typed argument
			if (values.leave_type && HA_VERIFY_LEAVE.includes(values.status)) args.leave_type = values.leave_type;
			dialog.hide();
			frappe
				.call({
					method: HA_VERIFY_MARK + "mark_days",
					args: args,
					freeze: true,
					freeze_message: __("Marking the days"),
				})
				.then((r) => ha_verify_marked(frm, (r && r.message) || {}));
		},
	});
	dialog.show();
}

function ha_verify_marked(frm, done) {
	if (done.queued) {
		frappe.show_alert({
			message: __("Marking {0} days. You will be told when it is done.", [done.queued]),
			indicator: "blue",
		});
		return;
	}
	const lines = (done.summary || []).map((line) => frappe.utils.escape_html(line));
	if ((done.problems || []).length) {
		frappe.msgprint({ title: __("Mark Attendance"), message: lines.join("<br>"), indicator: "orange" });
	} else {
		frappe.show_alert({ message: lines[0] || __("Marked."), indicator: "green" });
	}
	frm.reload_doc();
}

function ha_verify_intro(frm) {
	const doc = frm.doc;
	const on = (value) => (value ? frappe.datetime.str_to_user(value) : "");
	const who = (user) => frappe.utils.escape_html(frappe.user.full_name(user) || user || "");
	if (doc.docstatus === 1) {
		frm.set_intro(
			__("Verified by {0} on {1}. Payroll may pay these days, and they change no more.", [
				who(doc.verified_by),
				on(doc.verified_on),
			]),
			"green"
		);
	} else if (doc.docstatus === 2) {
		frm.set_intro(
			__("Reopened by {0} on {1}. Amend it to verify it again.", [who(doc.reopened_by), on(doc.reopened_on)]),
			"red"
		);
	} else if (frm.is_new()) {
		frm.set_intro(__("Pick the branch and the month, then press Get Attendance."), "blue");
	} else if (doc.return_remarks) {
		frm.set_intro(__("Returned: {0}", [frappe.utils.escape_html(doc.return_remarks)]), "orange");
	} else if (cint(doc.issues_count)) {
		frm.set_intro(
			__("{0} to put right, listed under To Put Right. Put them right, then press Get Attendance.", [
				cint(doc.issues_count),
			]),
			"orange"
		);
	} else if (doc.workflow_state === "Pending General Manager") {
		frm.set_intro(__("Waiting for the General Manager to verify."), "blue");
	} else if (cint(doc.people)) {
		frm.set_intro(__("Nothing to put right. Send it to the General Manager from Actions."), "blue");
	} else {
		frm.set_intro("");
	}
}
