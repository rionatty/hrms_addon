// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Monthly Training Schedule", {
	refresh(frm) {
		frm.trigger("draw_calendar");
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
	// the month's trainings as a roster by department: click a day to add
	// one, drag it to another day, click it to change it
	draw_calendar(frm) {
		const field = frm.fields_dict.calendar_html;
		if (!field) return;
		if (frm.is_new()) {
			frm.ha_calendar = null;
			field.$wrapper.html(
				`<div class="text-muted small">${__("Save the schedule to place its trainings on the calendar.")}</div>`
			);
			return;
		}
		const make = () => {
			if (frm.ha_calendar && frm.ha_calendar.opts.schedule === frm.doc.name) {
				frm.ha_calendar.refresh();
				return;
			}
			frm.ha_calendar = new hrms_addon.HRCalendarView({
				parent: field.$wrapper,
				view: "training",
				schedule: frm.doc.name,
				before_change: () => (frm.is_dirty() ? frm.save() : null),
				after_change: () => frm.reload_doc(),
			});
		};
		if (window.hrms_addon && hrms_addon.HRCalendarView) make();
		else frappe.require("/assets/hrms_addon/js/hr_calendar_view.js", make);
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
