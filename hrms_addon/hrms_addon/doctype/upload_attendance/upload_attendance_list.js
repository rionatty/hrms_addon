// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// each upload by where its marking has got to (attendance_upload.py)
frappe.listview_settings["Upload Attendance"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colour = {
			Draft: "gray",
			Queued: "blue",
			Importing: "blue",
			Done: "green",
			"Done with Problems": "orange",
			Failed: "red",
		}[doc.status];
		return [__(doc.status || "Draft"), colour || "gray", "status,=," + (doc.status || "Draft")];
	},
};
