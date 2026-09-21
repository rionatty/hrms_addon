// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Document Expiry"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{
			fieldname: "employee_status",
			label: __("Employee Status"),
			fieldtype: "Select",
			options: "Active\nInactive\nSuspended\nLeft",
			default: "Active",
		},
		{ fieldname: "expiring_only", label: __("Only What Is Wrong"), fieldtype: "Check", default: 1 },
		{ fieldname: "skip_missing", label: __("Hide Missing Documents"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data && data.status) {
			const colour =
				data.status === "Expired" || data.status === "Missing"
					? "red"
					: data.status === "Expiring Soon"
					? "orange"
					: "green";
			value = `<span class="indicator-pill ${colour}">${value}</span>`;
		}
		return value;
	},
};
