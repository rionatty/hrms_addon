// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// The Interview calendar: Frappe HR's own view, with each interview still to
// come marked with the candidate's answer to the invitation, or that none has
// come (interviews.get_calendar_events).
frappe.views.calendar["Interview"] = {
	field_map: {
		start: "from",
		end: "to",
		id: "name",
		title: "subject",
		allDay: "allDay",
		color: "color",
	},
	order_by: "scheduled_on",
	gantt: true,
	get_events_method: "hrms_addon.hrms_addon.interviews.get_calendar_events",
};
