// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// The requirements: each one's light and whether it is booked; HR raise the
// gaps the list shows as draft requisitions (learning_loop.raise_requisitions).
frappe.listview_settings["Employee Training Requirement"] = {
	add_fields: ["status", "booking_status", "booked_for"],
	get_indicator(doc) {
		const colour = { Overdue: "red", "Due Soon": "orange", Compliant: "green", Pending: "blue", "Not Applicable": "gray" };
		let label = __(doc.status);
		if (doc.booking_status && doc.status !== "Compliant") label += " · " + __(doc.booking_status);
		return [label, colour[doc.status] || "gray", "status,=," + doc.status];
	},
	onload(listview) {
		if (!frappe.user.has_role(["HR Manager", "HR User", "System Manager"])) return;
		listview.page.add_inner_button(__("Raise Requisitions"), () => {
			const values = {};
			(listview.filter_area.get() || []).forEach((filter) => {
				if (filter[2] === "=" && ["company", "branch", "department", "work_section", "training_program"].includes(filter[1])) {
					values[filter[1]] = filter[3];
				}
			});
			const dialog = new frappe.ui.Dialog({
				title: __("Raise Requisitions"),
				fields: [
					{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", default: values.company },
					{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch", default: values.branch },
					{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department", default: values.department },
					{ fieldname: "work_section", label: __("Section"), fieldtype: "Link", options: "Work Section", default: values.work_section },
					{ fieldname: "training_program", label: __("Training"), fieldtype: "Link", options: "Training Program", default: values.training_program },
					{ fieldname: "overdue_only", label: __("Overdue Only"), fieldtype: "Check" },
				],
				primary_action_label: __("Raise"),
				primary_action(picked) {
					dialog.hide();
					frappe
						.xcall("hrms_addon.hrms_addon.learning_loop.raise_requisitions", picked, "POST", {
							freeze: true,
							freeze_message: __("Raising requisitions"),
						})
						.then((found) => {
							if (found.queued) {
								frappe.msgprint(__("{0} requisitions for {1} employees are being drafted. You will be told when they are ready.", [found.groups, found.employees]));
							} else if (!(found.requisitions || []).length) {
								frappe.msgprint(__("No training is due or overdue without a booking or a requisition."));
							} else {
								frappe.msgprint(__("{0} draft requisitions for {1} employees: {2}", [found.requisitions.length, found.employees, found.requisitions.join(", ")]));
							}
							listview.refresh();
						});
				},
			});
			dialog.show();
		});
	},
};
