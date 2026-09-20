// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Position Change", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.employee && frm.doc.change_type === "Promotion") {
			frm.add_custom_button(__("Get Background"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.positions.get_background", { employee: frm.doc.employee })
					.then((found) => {
						const education = found.education || [];
						const experience = found.experience || [];
						if (!education.length && !experience.length) {
							frappe.show_alert({
								message: __("Nothing on the employee's bio-data to bring in."),
								indicator: "blue",
							});
							return;
						}
						const have_education = new Set((frm.doc.education || []).map((r) => r.certification));
						for (const row of education) {
							if (have_education.has(row.certification)) continue;
							frm.add_child("education", row);
						}
						const have_experience = new Set(
							(frm.doc.experience || []).map((r) => [r.designation, r.company].join("|"))
						);
						for (const row of experience) {
							if (have_experience.has([row.designation, row.company].join("|"))) continue;
							frm.add_child("experience", row);
						}
						frm.refresh_field("education");
						frm.refresh_field("experience");
					})
			);
		}
		frm.trigger("show_letter");
	},
	show_letter(frm) {
		const letters = {
			Promotion: "Promotion Letter",
			"Change of Designation": "Change of Designation Letter",
			"Salary Increment": "Salary Increment Letter",
		};
		const letter = letters[frm.doc.change_type];
		if (!letter) return;
		frm.set_intro("");
		if (frm.doc.docstatus === 1) {
			frm.set_intro(__("Approved. Print the {0} for signature.", [__(letter)]), "green");
		} else if (frm.doc.change_type === "Promotion") {
			frm.set_intro(
				__("The Candidate Preamble Promotion Form is signed by the Supervisor, the HR Manager, the General Manager and the Executive Director; then the {0} is printed.", [__(letter)]),
				"blue"
			);
		}
	},
	change_type(frm) {
		frm.trigger("show_letter");
		frm.trigger("employee");
	},
	employee(frm) {
		if (!frm.doc.employee) return;
		frappe.db.get_value("Employee", frm.doc.employee, ["designation", "reports_to"]).then((r) => {
			if (!r.message) return;
			if (!frm.doc.current_designation && r.message.designation) {
				frm.set_value("current_designation", r.message.designation);
			}
			if (!frm.doc.current_supervisor && r.message.reports_to) {
				frm.set_value("current_supervisor", r.message.reports_to);
			}
		});
	},
	setup(frm) {
		frm.set_query("employee", () => ({ filters: { status: "Active" } }));
		for (const field of ["new_supervisor", "current_supervisor"]) {
			frm.set_query(field, () => ({ filters: { status: "Active" } }));
		}
	},
});
