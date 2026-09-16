// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Job Requisition form, loaded through hooks.py doctype_js (read from
// disk at runtime, so no `bench build` is needed after changing it).
// HRMS ships its own job_requisition.js; both run, this one adds to it.

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

	refresh(frm) {
		ha_mount_connections(frm);
	},
});

// Connections live in their own section on the Details tab instead of a
// separate tab.
//
// Frappe only lets a Tab Break host the form dashboard (DocField
// show_dashboard is Tab-Break-only). The standard connections_tab is
// hidden with show_dashboard switched off by property setters, so the
// dashboard falls back to the top of the first tab
// (frappe/public/js/frappe/form/form.js, setup_std_layout). From there the
// links part alone is moved into custom_connections_html; the rest of the
// dashboard, including the HRMS "Employee Referrals" headline, stays at
// the top where it belongs.
//
// Moving the element is safe across refreshes: frappe.ui.form.Dashboard
// keeps references to links_area and re-renders inside it, wherever it
// sits in the DOM. The section's own "Connections" label is the heading;
// the links area hides its label (hide_label: true in dashboard.js).
function ha_mount_connections(frm) {
	const field = frm.fields_dict.custom_connections_html;
	const links = frm.dashboard && frm.dashboard.links_area;
	if (!field || !field.$wrapper || !links || !links.wrapper) {
		return;
	}
	if (!field.$wrapper.find(links.wrapper).length) {
		field.$wrapper.empty().append(links.wrapper);
	}
}
