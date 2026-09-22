// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// The month's output pay (minutes 4.6): Get Output fills it from the
// submitted daily reports, or an hourly run from attendance; submitting it
// writes each person's pay as an Additional Salary on top of their basic.

const HRA_PAY_MONTHS = [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
];

frappe.ui.form.on("Output Pay Run", {
	onload(frm) {
		if (!frm.is_new()) return;
		// the payroll month a day belongs to: from the 26th, the next one
		const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
		let month = today.getMonth();
		let year = today.getFullYear();
		if (today.getDate() >= 26) {
			month += 1;
			if (month > 11) {
				month = 0;
				year += 1;
			}
		}
		if (!frm.doc.year) frm.set_value("year", year);
		if (!frm.doc.month) frm.set_value("month", HRA_PAY_MONTHS[month]);
	},

	setup(frm) {
		const people = () => {
			const filters = { custom_pay_category: frm.doc.section };
			if (frm.doc.branch) filters.branch = frm.doc.branch;
			return { filters: filters };
		};
		frm.set_query("employee", "lines", people);
		frm.set_query("employee", "employees", people);
		frm.set_query("machine", "lines", () => ({ filters: { section: frm.doc.section } }));
	},

	refresh(frm) {
		if (frm.doc.docstatus !== 0 || frm.is_new()) return;
		const label = frm.doc.section === "Hourly" ? __("Get Hours") : __("Get Output");
		frm.add_custom_button(label, () =>
			frappe
				.xcall("hrms_addon.hrms_addon.output_pay.get_output", { run: frm.doc.name })
				.then((found) => {
					frappe.show_alert({
						message: __("{0} line(s), {1} people", [found.lines, found.employees]),
						indicator: "green",
					});
					frm.reload_doc();
				})
		);
	},
});
