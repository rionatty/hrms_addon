// HRMS Addon — the training session (Frappe HR's Training Event) in Luuka's
// process: a draft while scheduled (the HOD confirms the participants, HR
// marks attendance on the day and attaches the signed sheet), submitted once
// the training was held, then the evaluations keyed in.
// See hrms_addon/hrms_addon/training.py.

frappe.ui.form.on("Training Event", {
	setup(frm) {
		// each participant once
		frm.set_query("employee", "employees", () => {
			const listed = (frm.doc.employees || []).map((row) => row.employee).filter(Boolean);
			return { filters: Object.assign({ status: "Active" }, listed.length ? { name: ["not in", listed] } : {}) };
		});
	},
	refresh(frm) {
		const grid = frm.fields_dict.employees.grid;
		if (frm.doc.docstatus === 0) {
			grid.add_custom_button(__("Add Employees"), () =>
				hrms_addon.pick_employees({
					company: frm.doc.company,
					department: frm.doc.custom_department,
					skip: (frm.doc.employees || []).map((row) => row.employee),
					action: (rows) => {
						const have = new Set((frm.doc.employees || []).map((row) => row.employee));
						for (const row of rows) {
							if (have.has(row.employee)) continue;
							have.add(row.employee);
							frm.add_child("employees", {
								employee: row.employee, employee_name: row.employee_name, department: row.department,
							});
						}
						frm.refresh_field("employees");
						frm.dirty();
					},
				})
			);
		} else {
			grid.clear_custom_buttons();
		}
		if (frm.is_new()) return;
		if (frm.doc.docstatus === 0) {
			frm.dashboard.set_headline(
				__("Mark each participant Present or Absent, attach the signed attendance sheet, then Submit: the training was held.")
			);
		}
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(
				__("Create Evaluations"),
				() =>
					frappe
						.xcall("hrms_addon.hrms_addon.training.create_evaluations", { training_event: frm.doc.name })
						.then((made) => {
							frappe.show_alert({
								message: made
									? __("{0} evaluation form(s) created. Open each one to enter the ratings.", [made])
									: __("Every participant marked Present already has an evaluation."),
								indicator: made ? "green" : "blue",
							});
							frm.reload_doc();
						}),
				__("Actions")
			);
			frm.add_custom_button(
				__("Evaluations"),
				() => frappe.set_route("List", "Training Feedback", { training_event: frm.doc.name }),
				__("View")
			);
		}
	},
});
