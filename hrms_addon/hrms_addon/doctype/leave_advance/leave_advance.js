// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Leave Advance", {
	setup(frm) {
		frm.set_query("leave_application", () => ({
			filters: Object.assign(
				{ docstatus: 1, status: "Approved" },
				frm.doc.employee ? { employee: frm.doc.employee } : {}
			),
		}));
	},
	refresh(frm) {
		if (frm.doc.leave_application) {
			frm.add_custom_button(__("Leave Application"), () =>
				frappe.set_route("Form", "Leave Application", frm.doc.leave_application)
			);
		}
		if (frm.doc.processing) {
			frm.add_custom_button(__("Leave Advance Processing"), () =>
				frappe.set_route("Form", "Leave Advance Processing", frm.doc.processing)
			);
		}
		if (frm.doc.journal_entry) {
			frm.add_custom_button(__("Bank Entry"), () =>
				frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry)
			);
		}
		if (frm.doc.gross_basis && frm.doc.allowed_amount) {
			frm.dashboard.set_headline(
				__("Most that may be advanced: {0}, being {1}.", [
					format_currency(frm.doc.allowed_amount),
					frappe.utils.escape_html(frm.doc.gross_basis),
				])
			);
		}
	},
});
