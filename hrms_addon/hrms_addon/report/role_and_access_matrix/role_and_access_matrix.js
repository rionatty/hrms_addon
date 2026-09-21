// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Role and Access Matrix"] = {
	filters: [
		{ fieldname: "document", label: __("Document"), fieldtype: "Link", options: "DocType" },
		{ fieldname: "role", label: __("Role"), fieldtype: "Link", options: "Role" },
		{
			fieldname: "read_only_roles_only",
			label: __("Read-Only Roles Only"),
			fieldtype: "Check",
		},
		{
			fieldname: "level_one_only",
			label: __("Salary and Bank Fields Only"),
			fieldtype: "Check",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "level" && data && data.level) {
			value = `<span class="indicator-pill orange">${value}</span>`;
		}
		return value;
	},
};
