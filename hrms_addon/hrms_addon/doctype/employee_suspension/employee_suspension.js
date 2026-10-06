// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// the days run from the first, both ends counted, and the employee reports
// back the day after the last (suspension_rules.suspension_dates)
function ha_suspension_dates(frm) {
	if (frm.doc.docstatus !== 0) return;
	const days = cint(frm.doc.days);
	if (!frm.doc.from_date || days < 1) {
		frm.set_value({ to_date: null, report_back_on: null });
		return;
	}
	const last = frappe.datetime.add_days(frm.doc.from_date, days - 1);
	frm.set_value({ to_date: last, report_back_on: frappe.datetime.add_days(last, 1) });
}

frappe.ui.form.on("Employee Suspension", {
	days: ha_suspension_dates,
	from_date: ha_suspension_dates,
	refresh(frm) {
		const on = (day) => frappe.datetime.str_to_user(day);
		if (frm.doc.docstatus === 0 && frm.doc.return_remarks) {
			frm.set_intro(__("Returned: {0}", [frappe.utils.escape_html(frm.doc.return_remarks)]), "orange");
		} else if (frm.doc.status === "Approved") {
			frm.set_intro(__("Starts on {0}.", [on(frm.doc.from_date)]), "blue");
		} else if (frm.doc.status === "In Progress") {
			frm.set_intro(__("Suspended until {0}. Reports back on {1}.", [on(frm.doc.to_date), on(frm.doc.report_back_on)]), "orange");
		} else if (frm.doc.status === "Completed") {
			frm.set_intro(__("Reported back on {0}.", [on(frm.doc.report_back_on)]), "green");
		}
	},
});
