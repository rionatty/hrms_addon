// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// each deletion by how far it has got (attendance_deletions.py)
frappe.listview_settings["Attendance Deletion"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const colour = {
			Draft: "gray",
			Queued: "blue",
			Deleting: "blue",
			Stopped: "orange",
			Finished: "green",
			Failed: "red",
		}[doc.status];
		return [__(doc.status || "Draft"), colour || "gray", "status,=," + (doc.status || "Draft")];
	},
};
