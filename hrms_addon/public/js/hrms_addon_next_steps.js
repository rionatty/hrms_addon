// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Next Steps on every form whose process goes on into other documents
// (next_steps.py): the documents this one raised, or that followed it, each
// opened from a button in the Next Steps group. One document opens its
// form; several open their list. Which forms have steps comes with the
// session boot (frappe.boot.hrms_addon_next_steps).
//
// Frappe fires form-refresh on every form once its toolbar is cleared, so
// one handler serves them all. app_include_js, a plain file rather than a
// bundle, so a change to it needs no `bench build`.

frappe.provide("hrms_addon.next_steps");

hrms_addon.next_steps.show = function (frm) {
	const forms = (frappe.boot && frappe.boot.hrms_addon_next_steps) || [];
	if (!frm || !frm.doc || frm.is_new() || !forms.includes(frm.doctype)) return;
	// only the latest refresh draws: a slower answer for an earlier one is dropped
	const token = (frm.__ha_next_steps = (frm.__ha_next_steps || 0) + 1);
	const name = frm.doc.name;
	frappe.call({
		method: "hrms_addon.hrms_addon.next_steps.get_next_steps",
		args: { doctype: frm.doctype, name: name },
		callback: (response) => {
			if (frm.__ha_next_steps !== token || !frm.doc || frm.doc.name !== name) return;
			(response.message || []).forEach((step) => {
				const label = step.count > 1 ? __("{0} ({1})", [__(step.label), step.count]) : __(step.label);
				frm.add_custom_button(label, () => hrms_addon.next_steps.open(step), __("Next Steps"));
			});
		},
	});
};

hrms_addon.next_steps.open = function (step) {
	if (step.count === 1) {
		frappe.set_route("Form", step.doctype, step.names[0]);
		return;
	}
	frappe.route_options = step.filters;
	frappe.set_route("List", step.doctype);
};

$(document).on("form-refresh", (event, frm) => hrms_addon.next_steps.show(frm));
