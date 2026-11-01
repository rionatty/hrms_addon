// Recreate Salary Slips on a submitted payroll whose slips are still drafts
// and nothing is posted: the drafts are deleted and made again on the same
// payroll, in the background (payroll_entries.py). Frappe HR's own refresh
// clears the buttons of a submitted payroll first; this one runs after it.
frappe.ui.form.on("Payroll Entry", {
	refresh(frm) {
		ha_payroll_recreate_button(frm);
	},
});

function ha_payroll_recreate_button(frm) {
	const doc = frm.doc;
	const may_write = frm.perm && frm.perm[0] && frm.perm[0].write;
	if (doc.docstatus !== 1 || !may_write || cint(doc.salary_slips_submitted)) return;
	if (["Queued", "Cancelled"].includes(doc.status)) return;
	if (!cint(doc.salary_slips_created) && doc.status !== "Failed") return;
	frm.add_custom_button(__("Recreate Salary Slips"), () => {
		frappe.confirm(__("Delete the draft salary slips and make them again?"), () => {
			frappe
				.call({
					method: "hrms_addon.hrms_addon.payroll_entries.recreate_salary_slips",
					args: { payroll_entry: doc.name },
					freeze: true,
				})
				.then(() => {
					frappe.show_alert({ message: __("Making the salary slips again"), indicator: "blue" });
					frm.reload_doc();
				});
		});
	});
}
