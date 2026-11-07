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
		// whoever may save it now: HR while it is a draft, the General Manager while it waits
		if (frm.doc.docstatus === 0 && !frappe.workflow.is_read_only(frm.doctype, frm.docname)) {
			frm.add_custom_button(__("Get Attendance"), () => frm.save());
		}
	},
	company(frm) {
		ha_verify_months_load(frm);
		ha_verify_weekly(frm);
	},
	branch: ha_verify_weekly,
	pay_kind(frm) {
		ha_verify_header(frm);
		if (frm.doc.pay_kind === "Monthly") ha_verify_month_dates(frm, true);
		else ha_verify_weekly(frm);
	},
	pay_period(frm) {
		ha_verify_month_dates(frm, false);
	},
});

// The page buttons of both tables. Frappe draws them in a table's footer, and hides the footer of a read-only table
// drawn with less than a page of rows, as a new sheet's are, then never shows it again (grid.js setup_toolbar): once
// Get Attendance filled the tables, only their first 50 rows could be seen. Each time a table is drawn (Frappe's grid
// says "change" when it is), its footer shows while it has more than one page.
const HA_VERIFY_TABLES = ["employees", "issues"];

function ha_verify_pages(frm) {
	HA_VERIFY_TABLES.forEach((fieldname) => {
		const grid = frm.fields_dict[fieldname] && frm.fields_dict[fieldname].grid;
		if (!grid || !grid.wrapper) return;
		const show = () => {
			const pages = grid.grid_pagination;
			if (!pages || grid.is_editable()) return;
			grid.wrapper.find(".grid-footer").toggleClass("hidden", (grid.data || []).length <= pages.page_length);
		};
		grid.wrapper.off("change.ha_verify_pages").on("change.ha_verify_pages", show);
		show();
	});
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
		frm.set_value({ from_date: dates.from_date, to_date: dates.to_date });
	});
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
