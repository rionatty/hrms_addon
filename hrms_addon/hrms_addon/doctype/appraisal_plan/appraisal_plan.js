// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Appraisal Plan", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.year) {
			frm.add_custom_button(__("Fill the Year"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.appraisals.fill_year", { year: frm.doc.year })
					.then((rows) => {
						const have = new Set((frm.doc.quarters || []).map((r) => r.quarter));
						for (const row of rows) {
							if (have.has(row.quarter)) continue;
							frm.add_child("quarters", row);
						}
						frm.refresh_field("quarters");
					})
			);
		}
		if (frm.doc.docstatus === 1) {
			for (const row of frm.doc.quarters || []) {
				if (row.appraisal_cycle) continue;
				frm.add_custom_button(
					__("Open {0}", [row.quarter]),
					() =>
						frappe.confirm(
							__("Raise the appraisals for {0}?", [row.quarter]),
							() =>
								frappe
									.xcall("hrms_addon.hrms_addon.appraisals.open_quarter", {
										plan: frm.doc.name,
										quarter: row.quarter,
									})
									.then((made) => {
										frappe.show_alert({
											message: __("{0} appraisal(s) raised.", [made]),
											indicator: "green",
										});
										frm.reload_doc();
									})
						),
					__("Open a Quarter")
				);
			}
		}
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.year) {
			frm.set_value("year", new Date().getFullYear());
		}
	},
});
