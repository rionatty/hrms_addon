// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Monthly Training Schedule", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Calendar Trainings"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.training.get_calendar_trainings", {
						month: frm.doc.month, year: frm.doc.year, branch: frm.doc.branch,
						training_calendar: frm.doc.training_calendar,
					})
					.then((rows) => {
						if (!rows.length) {
							frappe.show_alert({ message: __("Nothing on the calendar for that month."), indicator: "blue" });
							return;
						}
						const have = new Set((frm.doc.lines || []).map((r) => r.calendar_entry).filter(Boolean));
						for (const row of rows) {
							if (have.has(row.calendar_entry)) continue;
							frm.add_child("lines", row);
						}
						frm.refresh_field("lines");
					})
			);
		}
	},
	month(frm) { frm.trigger("set_title"); },
	year(frm) { frm.trigger("set_title"); },
	branch(frm) { frm.trigger("set_title"); },
	set_title(frm) {
		if (frm.doc.month && frm.doc.year) {
			frm.set_value("title", [frm.doc.month + " " + frm.doc.year, frm.doc.branch].filter(Boolean).join(" - "));
		}
	},
});
