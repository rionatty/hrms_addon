// HRMS Addon — employees picked from a list, filtered by name, company and
// department: a requisition's target employees, a training's participants.
// Those already listed are left out of the list.

frappe.provide("hrms_addon");

hrms_addon.pick_employees = function (opts) {
	const skip = (opts.skip || []).filter(Boolean);
	return new frappe.ui.form.MultiSelectDialog({
		doctype: "Employee",
		target: {},
		setters: {
			employee_name: null,
			company: opts.company || frappe.defaults.get_user_default("Company") || null,
			department: opts.department || null,
		},
		primary_action_label: __("Add"),
		get_query: () => ({
			filters: Object.assign({ status: "Active" }, skip.length ? { name: ["not in", skip] } : {}),
		}),
		action(names) {
			const picked = (names || []).filter((name) => name && !skip.includes(name));
			this.dialog.hide();
			if (!picked.length) return;
			frappe.db
				.get_list("Employee", {
					filters: { name: ["in", picked] },
					fields: ["name", "employee_name", "department", "designation"],
					limit: picked.length,
				})
				.then((rows) => {
					const found = {};
					(rows || []).forEach((row) => (found[row.name] = row));
					opts.action(
						picked.map((name) => ({
							employee: name,
							employee_name: (found[name] || {}).employee_name || name,
							department: (found[name] || {}).department || null,
							designation: (found[name] || {}).designation || null,
						}))
					);
				});
		},
	});
};
