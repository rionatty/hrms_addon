// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Job Requisition form, loaded through hooks.py doctype_js (read from
// disk at runtime, so no `bench build` is needed after changing it).
// HRMS ships its own job_requisition.js; both run, this one adds to it.
//
// Connections is the standard Connections tab, placed straight after Job
// Description by the field_order property setter; nothing here touches it.

frappe.ui.form.on("Job Requisition", {
	onload(frm) {
		// Requested By = the logged-in user's employee. The server applies
		// the same default in before_validate for anything that is not
		// this form (API, import).
		if (frm.is_new() && !frm.doc.requested_by) {
			frappe
				.xcall("hrms_addon.hrms_addon.job_requisition.get_session_employee")
				.then((employee) => {
					if (employee && !frm.doc.requested_by) {
						frm.set_value("requested_by", employee);
					}
				});
		}
	},
});
