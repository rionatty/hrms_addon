// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["Calibration Movers"] = {
	filters: [
		{ fieldname: "talent_review", label: __("Talent Review"), fieldtype: "Link", options: "Talent Review" },
	],
};
