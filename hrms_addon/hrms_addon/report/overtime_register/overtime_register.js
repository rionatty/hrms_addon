// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The Overtime Register, on the Payroll tab: the dates start on the current
// attendance cycle, the 26th to the 25th.

frappe.query_reports["Overtime Register"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Date",
			default: ha_overtime_register_cycle()[0],
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To"),
			fieldtype: "Date",
			default: ha_overtime_register_cycle()[1],
			reqd: 1,
		},
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{ fieldname: "overtime_type", label: __("Overtime Type"), fieldtype: "Link", options: "Overtime Type" },
		{
			fieldname: "day_kind",
			label: __("Day"),
			fieldtype: "Select",
			options: ["", "Weekday", "Rest Day", "Public Holiday", "Leave Day"],
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Draft", "Requested", "Authorised", "Costed", "Sent to Payroll", "Rejected", "Cancelled"],
		},
		{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
	],
};

// the attendance cycle today falls in: the 26th to the 25th
function ha_overtime_register_cycle() {
	const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	const back = today.getDate() >= 26 ? 0 : 1;
	const start = new Date(today.getFullYear(), today.getMonth() - back, 26);
	const end = new Date(start.getFullYear(), start.getMonth() + 1, 25);
	return [frappe.datetime.obj_to_str(start), frappe.datetime.obj_to_str(end)];
}
