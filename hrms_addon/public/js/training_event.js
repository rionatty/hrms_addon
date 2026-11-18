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
		// a development plan keeps the session on its Training table, and lets
		// go of it itself when the session is cancelled (training.event_on_cancel)
		frm.ignore_doctypes_on_cancel_all = [
			...new Set([...(frm.ignore_doctypes_on_cancel_all || []), "Talent Program"]),
		];
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
		// the day rows, the sign-in table and the seats (learning_attendance.py)
		if (frm.doc.docstatus < 2 && frm.doc.event_status !== "Cancelled") {
			frm.add_custom_button(__("Sign-In"), () => frappe.set_route("training-sign-in", frm.doc.name), __("Attendance"));
			frm.add_custom_button(
				__("Attendance Days"),
				() => frappe.set_route("List", "Training Attendance", { training_event: frm.doc.name }),
				__("Attendance")
			);
		}
		if (frm.doc.docstatus === 0 && frm.doc.event_status !== "Cancelled") {
			const seat = (action, employee) =>
				frappe
					.xcall("hrms_addon.hrms_addon.learning_attendance." + action, { training_event: frm.doc.name, employee: employee || null }, "POST")
					.then((found) => {
						frappe.show_alert({ message: __(found.status), indicator: found.status === "Withdrawn" ? "orange" : "green" });
						frm.reload_doc();
					});
			frm.add_custom_button(__("Register Me"), () => seat("register"), __("Registration"));
			frm.add_custom_button(__("Withdraw Me"), () => seat("withdraw"), __("Registration"));
			if (frappe.user.has_role(["HR Manager", "HR User", "System Manager", "Supervisor"])) {
				frm.add_custom_button(
					__("Register an Employee"),
					() =>
						frappe.prompt(
							{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee", reqd: 1 },
							(values) => seat("register", values.employee),
							__("Register an Employee")
						),
					__("Registration")
				);
			}
		}
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
