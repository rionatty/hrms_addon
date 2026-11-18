// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// One plant's day (excellence_sheet.py): a row for each section and shift,
// typed or pasted from a spreadsheet; the people come from the clock in the
// background; submitting is the one approval.
frappe.ui.form.on("Plant Day Sheet", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.sheet_date) {
			frm.set_value("sheet_date", frappe.datetime.add_days(frappe.datetime.get_today(), -1));
		}
	},
	setup(frm) {
		frm.set_query("supervisor", "rows", () => ({
			filters: Object.assign({ status: "Active" }, frm.doc.branch ? { branch: frm.doc.branch } : {}),
		}));
		frm.set_query("downtime_reason", "rows", () => ({ filters: { is_active: 1 } }));
	},
	refresh(frm) {
		me_sheet_headline(frm);
		if (frm.doc.docstatus !== 0 || frm.is_new()) return;
		frm.add_custom_button(__("Fetch from Clock"), () => {
			const work = () =>
				frappe.xcall("hrms_addon.hrms_addon.excellence_sheet.fetch_clock", { sheet: frm.doc.name }).then(() => {
					frappe.show_alert({ message: __("Fetching the crews from the clock"), indicator: "blue" });
					frm.reload_doc();
				});
			if (frm.is_dirty()) {
				frm.save().then(work);
			} else {
				work();
			}
		});
		frm.add_custom_button(__("Paste from Spreadsheet"), () => me_sheet_paste(frm));
	},
});

function me_sheet_headline(frm) {
	if (frm.is_new()) return;
	const parts = [];
	if (frm.doc.missing_rows) parts.push(__("{0} shifts not entered", [frm.doc.missing_rows]));
	if (frm.doc.job_status) parts.push(frm.doc.job_status);
	if (!frm.doc.clock_fetched_on && frm.doc.docstatus === 0) parts.push(__("Not fetched from the clock yet"));
	if (parts.length) {
		frm.dashboard.set_headline(parts.join(". ") + ".", frm.doc.missing_rows ? "orange" : "blue");
	}
	if (frm.doc.job_problems) frm.dashboard.add_comment(frm.doc.job_problems, "red", true);
}

function me_sheet_paste(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Paste from Spreadsheet"),
		fields: [
			{
				fieldname: "text",
				fieldtype: "Code",
				label: __("Rows"),
				description: __(
					"Copy the rows with their heading: Section, Shift, Actual Output, Housekeeping, Machines Running, Stop Hours, Main Downtime Reason, Waste Quantity, Waste Value, Complaint Value, Wearing Full PPE, Not Worked, Comment."
				),
			},
		],
		primary_action_label: __("Put on the Sheet"),
		primary_action(values) {
			frappe
				.xcall("hrms_addon.hrms_addon.excellence_sheet.paste_rows", { sheet: frm.doc.name, text: values.text || "" })
				.then((found) => {
					for (const update of found.updates) {
						const row = (frm.doc.rows || []).find((each) => each.name === update.key);
						if (!row) continue;
						for (const [field, value] of Object.entries(update.values)) {
							frappe.model.set_value(row.doctype, row.name, field, value);
						}
					}
					frm.refresh_field("rows");
					dialog.hide();
					if (found.errors.length) {
						frappe.msgprint({ title: __("Not Put on the Sheet"), message: found.errors.join("<br>"), indicator: "orange" });
					} else {
						frappe.show_alert({ message: __("{0} rows filled. Save to keep them.", [found.updates.length]), indicator: "green" });
					}
				});
		},
	});
	dialog.show();
}
