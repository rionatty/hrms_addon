// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Luuka's appraisal templates are built on Frappe HR's own Appraisal
// Template rather than beside it, laid out as the LPL PMS workbook lays
// them out: Section A's KPIs under their perspectives, each perspective's
// weight on its first KPI and the four totalling 80, then Section B's
// competencies totalling 20. The whole workbook is read straight in, one
// sheet per role. A template for the supervisory form (LPL/HR/18) carries
// its ratable factors and objectives instead.
//
// Every Job Title names its template, and the appraisal fills itself from
// it, so what is set here is what an appraiser sees already filled in.
//
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.

const HA_SUPERVISORY = "Supervisory Skills (LPL/HR/18)";
// each form's own scale: (band, range, colour, meaning)
const HA_SCALES = {
	"Balanced Scorecard": [
		["Excellent", "≥90", "#1A2B4A", "Consistently exceeds all objectives & expectations"],
		["Very Good", "80–89", "#007B87", "Frequently meets & exceeds targets"],
		["Good", "70–79", "#2E8B57", "Fully meets most objectives"],
		["Fair", "60–69", "#E87722", "Meets some but not all objectives"],
		["Poor", "<60", "#C00000", "Consistently fails to meet standards"],
	],
	[HA_SUPERVISORY]: [
		["5 Excellent", "90–100%", "#1A2B4A", ""],
		["4 Very Good", "75–89%", "#007B87", ""],
		["3 Good", "60–74%", "#2E8B57", ""],
		["2 Average", "50–59%", "#E87722", ""],
		["1 Below Average", "40% and below", "#C00000", ""],
	],
};

frappe.ui.form.on("Appraisal Template", {
	refresh(frm) {
		frm.add_custom_button(__("Import PMS Workbook"), () =>
			frappe.prompt(
				[
					{
						fieldname: "review_year",
						fieldtype: "Int",
						label: __("Review Year"),
						reqd: 1,
						default: frm.doc.custom_review_year || new Date().getFullYear(),
					},
					{ fieldname: "company", fieldtype: "Link", options: "Company", label: __("Company") },
					{
						fieldname: "activate",
						fieldtype: "Check",
						label: __("Activate the ones that add up"),
						default: 1,
						description: __("A sheet whose weights do not total 80 and 20 is imported but left inactive."),
					},
				],
				(values) => {
					new frappe.ui.FileUploader({
						restrictions: { allowed_file_types: [".xlsx"] },
						on_success: (file) =>
							frappe
								.xcall("hrms_addon.hrms_addon.bsc.import_workbook", {
									file_url: file.file_url,
									review_year: values.review_year,
									company: values.company,
									activate: values.activate ? 1 : 0,
								})
								.then((found) => {
									const flagged = (found.flagged || []).length;
									frappe.msgprint({
										title: __("Scorecards imported"),
										indicator: flagged ? "orange" : "green",
										message: [
											__("{0} created, {1} updated.", [
												(found.created || []).length,
												(found.updated || []).length,
											]),
											flagged
												? __("{0} left inactive because their weights do not add up:", [flagged]) +
												  "<ul>" +
												  (found.flagged || [])
														.map(
															(row) =>
																"<li>" +
																frappe.utils.escape_html(row.sheet) +
																": " +
																frappe.utils.escape_html((row.problems || []).join("; ")) +
																"</li>"
														)
														.join("") +
												  "</ul>"
												: "",
											(found.skipped || []).length
												? __("Skipped (no scorecard on the sheet): {0}", [
														(found.skipped || []).join(", "),
												  ])
												: "",
										]
											.filter(Boolean)
											.join("<br>"),
									});
								}),
					});
				},
				__("Import an LPL PMS workbook"),
				__("Choose the file")
			)
		);
		ha_kpi_arrows(frm);
		frm.trigger("show_weights");
		frm.trigger("show_scale");
	},
	custom_form_type(frm) {
		frm.trigger("show_weights");
		frm.trigger("show_scale");
	},
	// Frappe HR's own KRA and rating tables are hidden on these templates,
	// but hiding a table does not stop its rows being checked: one blank
	// row left in it refuses the save with "KRA is required in every row",
	// about a table nobody can see. A blank row is dropped here, before
	// Frappe's mandatory check runs (form.js runs validate and before_save
	// first, save.js checks afterwards). A row with anything in it is left
	// alone: a plain Frappe HR template keeps its KRAs.
	before_save(frm) {
		const ours =
			(frm.doc.custom_kpis || []).length ||
			(frm.doc.custom_competencies || []).length ||
			(frm.doc.custom_factors || []).length ||
			frm.doc.custom_form_type === HA_SUPERVISORY;
		if (!ours) return;
		const drop = (table, filled) => {
			const rows = frm.doc[table] || [];
			const kept = rows.filter(filled);
			if (kept.length === rows.length) return;
			frm.doc[table] = kept;
			frm.refresh_field(table);
		};
		drop("goals", (row) => row.key_result_area || row.per_weightage);
		drop("rating_criteria", (row) => row.criteria || row.per_weightage);
	},
	// The headline says at a glance whether the template adds up: Section A
	// from each perspective's weight on its first KPI, Section B from the
	// competencies. The totals are summed from the rows on screen, so a
	// template being typed reads right before it is saved.
	show_weights(frm) {
		frm.dashboard.clear_headline();
		if (frm.doc.custom_form_type === HA_SUPERVISORY) {
			const factors = (frm.doc.custom_factors || []).length;
			const objectives = (frm.doc.custom_objectives || []).length;
			frm.dashboard.set_headline(
				`<span>${__("Section A: {0} ratable factors", [factors])} &nbsp;|&nbsp; ${__(
					"Section B: {0} objectives",
					[objectives]
				)}</span>` +
					(objectives > 8
						? ` <span class="indicator-pill orange">${__("At most eight objectives")}</span>`
						: "")
			);
			return;
		}
		const kpis = frm.doc.custom_kpis || [];
		const competencies = frm.doc.custom_competencies || [];
		if (!kpis.length && !competencies.length) return;
		const total = (rows) => rows.reduce((sum, row) => sum + (row.weight || 0), 0);
		const a = total(kpis);
		const b = total(competencies);
		const good = a === 80 && b === 20;
		frm.dashboard.set_headline(
			`<span>${__("Section A")} <b>${a}</b>/80 &nbsp;|&nbsp; ${__("Section B")} <b>${b}</b>/20</span>` +
				` <span class="indicator-pill ${good ? "green" : "orange"}">${
					good ? __("Adds up") : __("Does not add up")
				}</span>`
		);
	},
	show_scale(frm) {
		const field = frm.get_field("custom_rating_scale");
		if (!field) return;
		const bands = HA_SCALES[frm.doc.custom_form_type] || HA_SCALES["Balanced Scorecard"];
		const esc = frappe.utils.escape_html;
		field.$wrapper.html(
			'<div style="display:flex;flex-wrap:wrap;gap:6px;">' +
				bands
					.map(
						([band, range, colour, meaning]) =>
							'<div style="flex:1 1 160px;border-radius:6px;overflow:hidden;border:1px solid var(--border-color);">' +
							`<div style="background:${colour};color:#fff;font-weight:600;padding:6px 8px;">${esc(
								__(band)
							)} &nbsp;${esc(range)}</div>` +
							(meaning
								? `<div style="padding:6px 8px;color:var(--text-muted);font-size:var(--text-sm);">${esc(
										__(meaning)
								  )}</div>`
								: "") +
							"</div>"
					)
					.join("") +
				"</div>"
		);
	},
});

// A KPI under the same perspective as the one above it shows the workbook's
// arrow in place of the perspective's name again.
function ha_kpi_arrows(frm) {
	const grid = frm.fields_dict.custom_kpis && frm.fields_dict.custom_kpis.grid;
	if (!grid) return;
	const df = (grid.docfields || []).find((d) => d.fieldname === "perspective");
	if (!df || df.__ha_arrow) return;
	df.__ha_arrow = true;
	const plain = frappe.form.get_formatter("Link");
	df.formatter = (value, field, options, row) => {
		const rows = frm.doc.custom_kpis || [];
		const at = rows.findIndex((one) => row && one.name === row.name);
		if (at > 0 && value && rows[at - 1].perspective === value) {
			return '<span class="text-muted">↳</span>';
		}
		return plain(value, field, options, row);
	};
	grid.refresh();
}

// the headline moves as the weights are typed, not only when the form is saved
frappe.ui.form.on("BSC Template KPI", {
	weight(frm) {
		frm.trigger("show_weights");
	},
	perspective(frm) {
		frm.fields_dict.custom_kpis.grid.refresh();
	},
	custom_kpis_remove(frm) {
		frm.trigger("show_weights");
	},
});

frappe.ui.form.on("BSC Template Competency", {
	weight(frm) {
		frm.trigger("show_weights");
	},
	custom_competencies_remove(frm) {
		frm.trigger("show_weights");
	},
});

frappe.ui.form.on("Appraisal Template Factor", {
	custom_factors_add(frm) {
		frm.trigger("show_weights");
	},
	custom_factors_remove(frm) {
		frm.trigger("show_weights");
	},
});

frappe.ui.form.on("Appraisal Template Objective", {
	custom_objectives_add(frm) {
		frm.trigger("show_weights");
	},
	custom_objectives_remove(frm) {
		frm.trigger("show_weights");
	},
});
