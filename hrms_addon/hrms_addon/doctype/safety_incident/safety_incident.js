// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// The doctor's latest report: the last dated, and of two on one day the
// later row (safety_rules.latest_report)
function ha_safety_latest_report(frm) {
	let latest = null;
	(frm.doc.medical_reports || []).forEach((row) => {
		if (row.report_date && (!latest || row.report_date >= latest.report_date)) latest = row;
	});
	return latest;
}

// a rest runs from its first day, both ends counted (safety_rules.rest_to)
function ha_safety_rest_to(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const days = cint(row.rest_days);
	frappe.model.set_value(cdt, cdn, "rest_to",
		row.recommendation === "Rest" && row.rest_from && days > 0 ? frappe.datetime.add_days(row.rest_from, days - 1) : null);
}

function ha_safety_separate(frm) {
	const latest = ha_safety_latest_report(frm);
	const ends = (frm.doc.medical_reports || []).filter((row) => row.recommendation === "Rest" && row.rest_to).map((row) => row.rest_to);
	const last = [latest.report_date, ...ends].sort().pop();
	frappe.prompt([{
		fieldname: "last_day", fieldtype: "Date", label: __("Last Day of Work"), reqd: 1, default: last,
		description: __("The letter says the employee was paid to this day."),
	}], (values) => {
		frappe.call({
			method: "hrms_addon.hrms_addon.safety.separate_on_medical_grounds",
			args: { incident: frm.doc.name, last_day: values.last_day },
			freeze: true,
		}).then(() => frm.reload_doc());
	}, __("Separate on Medical Grounds"), __("Separate"));
}

frappe.ui.form.on("Safety Incident", {
	refresh(frm) {
		const latest = ha_safety_latest_report(frm);
		if (!frm.is_new() && frm.doc.docstatus < 2) {
			// the order the employee takes to the hospital (medical_treatment_order.js)
			frm.add_custom_button(__("Treatment Order"), () => frappe.new_doc("Medical Treatment Order", {
				employee: frm.doc.employee, safety_incident: frm.doc.name, hospital: frm.doc.hospital,
				complaint: frm.doc.nature,
			}), __("Create"));
		}
		if (frm.doc.docstatus === 0 && frm.doc.return_remarks) {
			frm.set_intro(__("Returned: {0}", [frappe.utils.escape_html(frm.doc.return_remarks)]), "orange");
		} else if (frm.doc.docstatus === 1 && !frm.doc.separation && latest && latest.recommendation === "Unfit for Work") {
			frm.set_intro(__("The doctor finds {0} unfit for work. The HR Manager decides on a separation on medical grounds.",
				[frappe.utils.escape_html(frm.doc.employee_name || frm.doc.employee)]), "red");
			if (frappe.user.has_role("HR Manager")) {
				frm.add_custom_button(__("Separate on Medical Grounds"), () => ha_safety_separate(frm));
			}
		}
	},
});

frappe.ui.form.on("Safety Medical Report", {
	recommendation: ha_safety_rest_to,
	rest_from: ha_safety_rest_to,
	rest_days: ha_safety_rest_to,
});
