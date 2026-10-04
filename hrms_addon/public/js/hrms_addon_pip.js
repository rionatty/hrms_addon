// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Employees on an improvement plan in red, wherever a form lists them
// (Luuka, 4 Oct 2026): the appraisal cycle's appraisees, the appraisal
// plan's employees and the performance review's rows. Each form calls
// hrms_addon.pip.mark_rows on refresh, and again when its table is filled;
// who is on an open plan comes from pips.open_plans.
//
// app_include_js, a plain file rather than a bundle, so a change to it
// needs no `bench build`.

frappe.provide("hrms_addon.pip");

// employee -> their open plan (or 1 where the plans cannot be read)
hrms_addon.pip.plans = hrms_addon.pip.plans || {};

// what Frappe draws for a cell, with no formatter of ours in the way
hrms_addon.pip.plain = function (value, df, options, row) {
	return frappe.format(value, Object.assign({}, df, { formatter: null }), options, row);
};

// the cell red, with a PIP pill, for someone on a plan
hrms_addon.pip.mark_html = function (html, on_plan) {
	if (!on_plan) return html;
	return (
		`<span class="text-danger" style="font-weight:600">${html}</span> ` +
		`<span class="indicator-pill red" title="${frappe.utils.escape_html(
			__("On an improvement plan")
		)}">${__("PIP")}</span>`
	);
};

// a score below the pass mark, red
hrms_addon.pip.score_html = function (html, below) {
	return below ? `<span class="text-danger" style="font-weight:600">${html}</span>` : html;
};

// the rows of `table` whose employee is on an open plan, marked in the
// `field` column (the employee's name, or the employee where that is all
// the table shows)
hrms_addon.pip.mark_rows = function (frm, table, field) {
	const grid = frm.fields_dict[table] && frm.fields_dict[table].grid;
	if (!grid) return;
	const employees = [...new Set((frm.doc[table] || []).map((row) => row.employee).filter(Boolean))];
	if (!employees.length) return;
	frappe
		.xcall("hrms_addon.hrms_addon.pips.open_plans", { employees: employees })
		.then((found) => {
			for (const employee of employees) delete hrms_addon.pip.plans[employee];
			Object.assign(hrms_addon.pip.plans, found || {});
			grid.update_docfield_property(field || "employee_name", "formatter", (value, df, options, row) =>
				hrms_addon.pip.mark_html(
					hrms_addon.pip.plain(value, df, options, row),
					row && hrms_addon.pip.plans[row.employee]
				)
			);
		});
};
