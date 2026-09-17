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
//
// Every Job Description table has Download and Upload buttons under it
// (allow_bulk_edit on its Designation field): Upload is Frappe's own,
// Download is replaced below so Excel reads the file correctly.

const HA_KRA_TABLE = "custom_jd_key_result_areas";

frappe.ui.form.on("Designation", {
	setup(frm) {
		// Upload fills the rows without any row event, which would leave the
		// totals describing the rows it replaced. Each row it adds marks the
		// form dirty (frappe/public/js/frappe/model/create_new.js) before its
		// values are set, so the recount waits until the upload has finished.
		$(frm.wrapper).on(
			"dirty",
			frappe.utils.debounce(() => ha_show_kra_totals(frm), 300)
		);
	},
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
		ha_setup_jd_downloads(frm);
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

// Download under each Job Description table. Frappe's own button saves the
// CSV without a UTF-8 byte order mark, so Excel opens it as Windows-1252:
// "Bachelor’s" shows as "Bachelorâ€™s", and saving keeps it that way. This
// writes the same rows as Frappe (frappe/public/js/frappe/form/grid.js
// setup_download), so its Upload reads the file back, with the mark in
// front. Values are quoted as they are, not passed through HTML the way
// frappe.tools.to_csv does, so text comes back from Upload unchanged.
// scripts/verify_job_description.py checks the rows against grid.js.
function ha_setup_jd_downloads(frm) {
	frm.meta.fields
		.filter((df) => df.fieldtype === "Table" && df.fieldname.startsWith("custom_jd_"))
		.forEach((df) => {
			const field = frm.fields_dict[df.fieldname];
			if (!field || !field.grid) {
				return;
			}
			$(field.grid.wrapper)
				.find(".grid-download")
				.off("click")
				.on("click", () => {
					ha_download_table(frm, field.grid.df);
					return false;
				});
		});
}

function ha_download_table(frm, df) {
	const title = df.label || frappe.model.unscrub(df.fieldname);
	const data = [
		[__("Bulk Edit {0}", [title])],
		[],
		[],
		[],
		[__("The CSV format is case sensitive")],
		[__("Do not edit headers which are preset in the template")],
		["------"],
	];
	// Upload reads the fieldnames from row 3 (data[2]) and rows from row 8 on
	const columns = frappe
		.get_meta(df.options)
		.fields.filter((column) => frappe.model.is_value_type(column.fieldtype));
	columns.forEach((column) => {
		data[1].push(column.label);
		data[2].push(column.fieldname);
		let description = (column.description || "") + " ";
		if (column.fieldtype === "Date") {
			description += frappe.boot.sysdefaults.date_format;
		}
		data[3].push(description);
	});
	(frm.doc[df.fieldname] || []).forEach((row) => {
		data.push(
			columns.map((column) => {
				let value = row[column.fieldname];
				if (column.fieldtype === "Date" && value) {
					value = frappe.datetime.str_to_user(value);
				}
				return value || "";
			})
		);
	});

	const csv = data.map((cells) => cells.map(ha_csv_cell).join(",")).join("\n");
	const link = document.createElement("a");
	link.href = URL.createObjectURL(new Blob(["\ufeff" + csv], { type: "text/csv;charset=UTF-8" }));
	link.download = `${title}.csv`;
	document.body.appendChild(link);
	link.click();
	document.body.removeChild(link);
}

function ha_csv_cell(value) {
	return typeof value === "string" ? `"${value.replace(/"/g, '""')}"` : value;
}
