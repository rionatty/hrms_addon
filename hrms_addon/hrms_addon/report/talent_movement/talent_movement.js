// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// Where each person sat in one talent review and where they sit in the next (talent_movement.py).
const MOVEMENT_PILLS = { Up: "green", Down: "red", Across: "orange", Same: "gray", New: "blue", "Not Placed": "gray" };

frappe.query_reports["Talent Movement"] = {
	filters: [
		{ fieldname: "talent_review", label: __("Review"), fieldtype: "Link", options: "Talent Review" },
		{ fieldname: "compared_with", label: __("Compared With"), fieldtype: "Link", options: "Talent Review" },
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{
			fieldname: "movement",
			label: __("Movement"),
			fieldtype: "Select",
			options: "\nUp\nDown\nAcross\nSame\nNew\nNot Placed",
		},
		{ fieldname: "from_box", label: __("From Box"), fieldtype: "Int" },
		{ fieldname: "to_box", label: __("To Box"), fieldtype: "Int" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "movement" && data && data.movement) {
			value = `<span class="indicator-pill ${MOVEMENT_PILLS[data.movement] || "gray"}">${value}</span>`;
		}
		return value;
	},
};
