// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// The plant's accountant pays the transport in cash: a Cash Entry drafted
// for them to check and submit (safety.make_transport_entry)
function ha_treatment_pay_transport(frm) {
	frappe.xcall("hrms_addon.hrms_addon.safety.make_transport_entry", { order: frm.doc.name }).then((entry) => {
		const doclist = frappe.model.sync(entry);
		frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
	});
}

frappe.ui.form.on("Medical Treatment Order", {
	setup(frm) {
		frm.set_query("safety_incident", () => ({ filters: { employee: frm.doc.employee || "", docstatus: ["<", 2] } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.return_remarks) {
			frm.set_intro(__("Returned: {0}", [frappe.utils.escape_html(frm.doc.return_remarks)]), "orange");
		}
		const accountant = frappe.user.has_role("Accounts User") || frappe.user.has_role("Accounts Manager");
		if (frm.doc.docstatus === 1 && frm.doc.transport_required && !frm.doc.transport_entry && accountant) {
			frm.add_custom_button(__("Pay Transport"), () => ha_treatment_pay_transport(frm));
		}
	},
});
