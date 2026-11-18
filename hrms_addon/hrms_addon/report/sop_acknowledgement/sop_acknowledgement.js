// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.query_reports["SOP Acknowledgement"] = {
	filters: [
		{ fieldname: "content_type", label: __("Type"), fieldtype: "Select", default: "SOP",
			options: "\nDocument\nSOP\nManual\nVideo\nLink\nPresentation\nToolbox Talk\nQuiz" },
		{ fieldname: "learning_content", label: __("Content"), fieldtype: "Link", options: "Learning Content" },
		{ fieldname: "branch", label: __("Plant"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "work_section", label: __("Section"), fieldtype: "Link", options: "Work Section" },
		{ fieldname: "group_by", label: __("By"), fieldtype: "Select", options: "Plant\nSection\nContent", default: "Plant" },
	],
};
