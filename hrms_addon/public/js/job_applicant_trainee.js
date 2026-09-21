// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Test case 16: a graduate hired through resourcing becomes a Graduate
// Trainee Program from their own applicant record, rather than being keyed
// in again on a second form.
//
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.

frappe.ui.form.on("Job Applicant", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.status !== "Accepted") return;
		frappe.db
			.get_value("Graduate Trainee Program", { job_applicant: frm.doc.name, docstatus: ["<", 2] }, "name")
			.then((result) => {
				const found = (result && result.message && result.message.name) || null;
				if (found) {
					frm.add_custom_button(__("Graduate Trainee"), () =>
						frappe.set_route("Form", "Graduate Trainee Program", found)
					);
					return;
				}
				frm.add_custom_button(
					__("Graduate Trainee Program"),
					() =>
						frappe.prompt(
							[
								{
									fieldname: "cohort",
									fieldtype: "Data",
									label: __("Cohort"),
									reqd: 1,
									default: __("Graduate Intake {0}", [
										frappe.datetime.get_today().slice(0, 4),
									]),
								},
								{
									fieldname: "start_date",
									fieldtype: "Date",
									label: __("Starts"),
									reqd: 1,
									default: frappe.datetime.get_today(),
								},
							],
							(values) =>
								frappe
									.xcall("hrms_addon.hrms_addon.talent.trainee_from_applicant", {
										job_applicant: frm.doc.name,
										cohort: values.cohort,
										start_date: values.start_date,
									})
									.then((name) =>
										frappe.set_route("Form", "Graduate Trainee Program", name)
									),
							__("Put this graduate on the trainee programme"),
							__("Create")
						),
					__("Create")
				);
			});
	},
});
