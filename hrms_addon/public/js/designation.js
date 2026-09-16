// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Designation (Job Title) — Job Description tab. Loaded through hooks.py
// doctype_js, read from disk at runtime, so no `bench build` is needed.
//
// Each Key Result Areas row picks a KRA from HRMS's KRA master; its
// perspective is fetched from the KRA. Several KRAs can share a
// perspective, so this keeps a running total per perspective under the
// table, the way the paper JD prints it ("Financial 25%").
//
// Perspectives are a master HR maintains (KRA Perspective), so the list and
// its order come from the server, never from a list written here.

const HA_KRA_TABLE = "custom_jd_key_result_areas";

frappe.ui.form.on("Designation", {
	onload(frm) {
		frappe
			.xcall("hrms_addon.hrms_addon.designation.get_perspective_order")
			.then((names) => {
				frm.__ha_perspectives = names || [];
				ha_show_kra_totals(frm);
			});
	},
	refresh(frm) {
		ha_show_kra_totals(frm);
	},
	custom_jd_key_result_areas_add(frm) {
		ha_show_kra_totals(frm);
	},
	custom_jd_key_result_areas_remove(frm) {
		ha_show_kra_totals(frm);
	},
});

frappe.ui.form.on("JD Key Result Area", {
	// `perspective` fires when the fetch from the picked KRA lands, which
	// is after `kra` itself — both are needed for an accurate total.
	kra(frm) {
		ha_show_kra_totals(frm);
	},
	perspective(frm) {
		ha_show_kra_totals(frm);
	},
	weighting(frm) {
		ha_show_kra_totals(frm);
	},
});

function ha_show_kra_totals(frm) {
	const field = frm.fields_dict[HA_KRA_TABLE];
	if (!field || !field.grid) {
		return;
	}
	const rows = frm.doc[HA_KRA_TABLE] || [];

	// Every perspective in the master, in Display Order, then any other
	// perspective a row carries (e.g. added since the form was opened).
	const order = (frm.__ha_perspectives || []).slice();
	rows.forEach((row) => {
		if (row.perspective && !order.includes(row.perspective)) {
			order.push(row.perspective);
		}
	});
	const totals = {};
	order.forEach((perspective) => (totals[perspective] = 0));

	let total = 0;
	rows.forEach((row) => {
		const value = flt(row.weighting);
		total += value;
		if (row.perspective) {
			totals[row.perspective] += value;
		}
	});

	let html = "";
	if (rows.length) {
		const parts = order.map(
			(perspective) => `${frappe.utils.escape_html(__(perspective))} <b>${ha_percent(totals[perspective])}</b>`
		);
		// Same 0.01 tolerance as jd_rules.TOLERANCE
		const ok = Math.abs(total - 100) <= 0.01;
		const colour = ok ? "var(--green-600, #28a745)" : "var(--red-600, #dc3545)";
		html =
			parts.join(" &nbsp;·&nbsp; ") +
			` &nbsp;|&nbsp; ${__("Total")} <b style="color:${colour}">${ha_percent(total)}</b>` +
			(ok ? "" : ` <span style="color:${colour}">${__("(must be 100%)")}</span>`);
	}
	// Kept on the df too, so Frappe's own grid refresh re-renders the same text.
	field.grid.df.description = html;
	// Set visibility here rather than via grid.set_grid_description(): that
	// hides the box when the description is empty but never shows it again
	// (frappe/public/js/frappe/form/grid.js), so a new Job Title would never
	// display the totals once its first row was added.
	$(field.grid.parent).find(".grid-description").html(html).toggle(Boolean(html));
}

function ha_percent(value) {
	return `${(Math.round(value * 100) / 100).toString()}%`;
}
