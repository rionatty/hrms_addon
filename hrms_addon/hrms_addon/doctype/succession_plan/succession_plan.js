// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// A year's critical roles and their benches (succession_plans.py): Get Positions
// gathers the year's roles; a finalised plan's benches are read again on demand.
frappe.ui.form.on("Succession Plan", {
	setup(frm) {
		// a role cancelled on its own leaves the plan as it was
		frm.ignore_doctypes_on_cancel_all = [...new Set([...(frm.ignore_doctypes_on_cancel_all || []), "Succession Position"])];
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.plan_year) {
			frm.set_value("plan_year", new Date().getFullYear());
		}
		if (frm.is_new() && !frm.doc.plan_owner) {
			frm.set_value("plan_owner", frappe.session.user);
		}
	},
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Read the Benches Again"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.succession_plans.refresh_plan", { plan: frm.doc.name })
					.then(() => frm.reload_doc())
			);
		}
		frm.set_query("succession_position", "positions", () => ({
			filters: { company: frm.doc.company, docstatus: ["!=", 2] },
		}));
	},
	plan_year(frm) {
		frm.trigger("make_title");
	},
	branch(frm) {
		frm.trigger("make_title");
	},
	make_title(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.plan_year) {
			frm.set_value("title", [__("Succession Plan"), frm.doc.plan_year, frm.doc.branch].filter(Boolean).join(" "));
		}
	},
	get_positions(frm) {
		const fetch = () =>
			frappe
				.xcall("hrms_addon.hrms_addon.succession_plans.get_positions", { plan: frm.doc.name })
				.then((added) => {
					frappe.show_alert({ message: __("{0} role(s) added", [added]), indicator: added ? "green" : "orange" });
					frm.reload_doc();
				});
		if (frm.is_new() || frm.is_dirty()) {
			frm.save().then(fetch);
		} else {
			fetch();
		}
	},
});
