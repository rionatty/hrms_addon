// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

/* The HR calendar page: leave and training for a month, drawn and worked
 * like Frappe HR's shift roster (public/js/hr_calendar_view.js), across
 * every plant and department the user may see. The Annual Leave Plan and
 * the Monthly Training Schedule draw the same view for themselves.
 */

frappe.pages["hr-calendar"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("HR Calendar"),
		single_column: true,
	});
	const make = () => {
		const options = frappe.route_options || {};
		frappe.route_options = null;
		wrapper.calendar = new hrms_addon.HRCalendarView({
			parent: $("<div></div>").appendTo(page.main),
			view: options.view === "training" ? "training" : "leave",
			switchable: true,
			branch: options.branch || null,
			department: options.department || null,
		});
		const filters = () =>
			wrapper.calendar.set_filters({
				branch: branch.get_value() || null,
				department: department.get_value() || null,
				everyone: everyone.get_value() ? 1 : 0,
			});
		const branch = page.add_field({
			fieldtype: "Link",
			label: __("Plant"),
			fieldname: "branch",
			options: "Branch",
			default: options.branch || "",
			change: filters,
		});
		const department = page.add_field({
			fieldtype: "Link",
			label: __("Department"),
			fieldname: "department",
			options: "Department",
			default: options.department || "",
			change: filters,
		});
		const everyone = page.add_field({
			fieldtype: "Check",
			label: __("Everyone"),
			fieldname: "everyone",
			change: filters,
		});
		page.set_primary_action(__("Refresh"), () => wrapper.calendar.refresh(), "refresh");
	};
	if (window.hrms_addon && hrms_addon.HRCalendarView) make();
	else frappe.require("/assets/hrms_addon/js/hr_calendar_view.js", make);
};

frappe.pages["hr-calendar"].on_page_show = function (wrapper) {
	if (wrapper.calendar && wrapper.calendar.data) wrapper.calendar.refresh();
};
