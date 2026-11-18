// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Calibration Movers"] = {
	filters: [
		{ fieldname: "talent_review", label: __("Talent Review"), fieldtype: "Link", options: "Talent Review" },
		{ fieldname: "calibration_session", label: __("Session"), fieldtype: "Link", options: "Calibration Session" },
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{ fieldname: "event", label: __("Event"), fieldtype: "Select", options: "\nMoved\nApplied\nProposed\nNot Agreed\nReverted" },
	],
};
