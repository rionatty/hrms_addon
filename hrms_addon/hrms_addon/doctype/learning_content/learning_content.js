// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// A piece of learning content (learning_library.py): assign it to everyone a
// training rule reaches, a plant, a section or a department.
frappe.ui.form.on("Learning Content", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.is_active) return;
		frm.add_custom_button(__("Assign"), () => {
			const dialog = new frappe.ui.Dialog({
				title: __("Assign {0}", [frm.doc.title]),
				fields: [
					{ fieldname: "training_rule", label: __("Everyone a Rule Reaches"), fieldtype: "Link", options: "Training Rule" },
					{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch", default: frm.doc.branch },
					{ fieldname: "work_section", label: __("Section"), fieldtype: "Link", options: "Work Section", default: frm.doc.work_section },
					{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department", default: frm.doc.department },
					{ fieldname: "due_date", label: __("Due Date"), fieldtype: "Date" },
				],
				primary_action_label: __("Assign"),
				primary_action(values) {
					dialog.hide();
					frappe
						.xcall("hrms_addon.hrms_addon.learning_library.assign", Object.assign({ content: frm.doc.name }, values), "POST")
						.then((found) => frappe.show_alert({ message: __("Being assigned to {0} employees.", [found.employees]), indicator: "green" }));
				},
			});
			dialog.show();
		}).addClass("btn-primary");
		frm.add_custom_button(__("Assignments"), () => frappe.set_route("List", "Learning Content Assignment", { learning_content: frm.doc.name }));
	},
});
