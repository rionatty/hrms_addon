// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Performance Improvement Plan", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.status === "Agreed") {
			frm.add_custom_button(__("Start the Plan"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.pips.start", { name: frm.doc.name })
					.then(() => frm.reload_doc())
			);
		}
		if (frm.doc.docstatus === 0 && frm.doc.status === "Draft") {
			frm.set_intro(
				__("Agree the plan with the employee: what must improve, the standard to reach, the support and how it is measured. Both sign, then start it."),
				"blue"
			);
		} else if (frm.doc.status === "In Progress") {
			frm.set_intro(__("Under way. Record each review as it is held, then submit to close the plan."), "orange");
		} else if (frm.doc.docstatus === 1) {
			frm.set_intro(__("Closed: {0}.", [frm.doc.outcome || ""]), "green");
		}
	},
	start_date(frm) {
		frm.trigger("set_end");
	},
	months(frm) {
		frm.trigger("set_end");
	},
	set_end(frm) {
		if (!frm.doc.start_date || !frm.doc.months) return;
		frm.set_value(
			"end_date",
			frappe.datetime.add_days(frappe.datetime.add_months(frm.doc.start_date, frm.doc.months), -1)
		);
	},
	setup(frm) {
		frm.set_query("employee", () => ({ filters: { status: "Active" } }));
		frm.set_query("supervisor", () => ({ filters: { status: "Active" } }));
	},
});
