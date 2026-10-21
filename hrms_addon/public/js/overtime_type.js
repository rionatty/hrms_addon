// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Frappe HR's Overtime Type. Overtime is paid only under a type that lists
// the employee (overtime_rules.person_type), and each of Luuka's types is for
// its own set of employees. Get Employees fills the Eligibility tab's
// Employees from one or more departments at once, instead of one by one
// (overtime.employees_of_departments). Somebody another type lists already
// is added only when asked.
// doctype_js, read from disk when the form loads: no `bench build`.

frappe.ui.form.on("Overtime Type", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Get Employees"), () => ha_overtime_type_employees(frm));
	},
});

function ha_overtime_type_employees(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Get Employees"),
		fields: [
			{
				fieldname: "departments",
				fieldtype: "Table MultiSelect",
				label: __("Departments"),
				options: "Overtime Type Department",
				reqd: 1,
				description: __("Their active employees, and those of the departments under them."),
			},
			{ fieldname: "branch", fieldtype: "Link", label: __("Plant"), options: "Branch" },
			{
				fieldname: "include_listed",
				fieldtype: "Check",
				label: __("Add those another Overtime Type lists too"),
			},
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			const departments = (values.departments || []).map((row) => row.department).filter(Boolean);
			frappe
				.xcall("hrms_addon.hrms_addon.overtime.employees_of_departments", {
					departments,
					branch: values.branch,
					overtime_type: frm.doc.name,
				})
				.then((people) => {
					dialog.hide();
					ha_add_overtime_type_employees(frm, people, values.include_listed);
				});
		},
	});
	dialog.show();
}

function ha_add_overtime_type_employees(frm, people, include_listed) {
	const here = new Set((frm.doc.custom_employees || []).map((row) => row.employee));
	let added = 0;
	let already = 0;
	const elsewhere = [];
	for (const person of people || []) {
		if (here.has(person.employee)) {
			already += 1;
			continue;
		}
		if (person.elsewhere.length && !include_listed) {
			elsewhere.push(`${person.employee_name || person.employee} (${person.elsewhere.join(", ")})`);
			continue;
		}
		frm.add_child("custom_employees", {
			employee: person.employee,
			employee_name: person.employee_name,
			department: person.department,
		});
		here.add(person.employee);
		added += 1;
	}
	frm.refresh_field("custom_employees");
	const lines = [__("{0} added. Save to keep them.", [added])];
	if (already) lines.push(__("{0} were on this type already.", [already]));
	if (elsewhere.length) {
		lines.push(__("Not added, on another type already: {0}.", [elsewhere.slice(0, 20).join(", ")]));
		if (elsewhere.length > 20) lines.push(__("And {0} more.", [elsewhere.length - 20]));
	}
	frappe.msgprint({
		title: __("Get Employees"),
		message: lines.map((line) => frappe.utils.escape_html(line)).join("<br>"),
		indicator: added ? "green" : "orange",
	});
}
