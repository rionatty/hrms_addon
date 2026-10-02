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

// ── The scorecard as Luuka's workbook lays it out ─────────────────────
// A Balanced Scorecard template is shown as the LPL PMS BSC Appraisal Form:
// the header, Section A with its quarters, the assignments, Section B, the
// overall score, the scale and Parts D and E. What the template holds is
// filled in; what an appraisal fills in is left blank, as on the sheet. The
// palette and columns are the workbook's, as the offline sheet paints them
// (appraisal_sheet.py). It is shown here and set in the tables below.
const HA_TEMPLATE_BSC = "Balanced Scorecard";
const HA_SHEET = {
	navy: "#1A2B4A",
	teal: "#007B87",
	tealDark: "#005F6B",
	gold: "#C9A42B",
	label: "#EEF2F6",
	note: "#E8EDF4",
	soft: "#E0F4F6",
	cream: "#FFF8E1",
	green: "#E8F5E9",
	grey: "#F9F9F9",
};
// (a word in the perspective's name, its fill, its text)
const HA_PERSPECTIVE_COLOURS = [
	["financ", "#E3F2FD", "#1A5276"],
	["customer", "#E8F5E9", "#1E8449"],
	["internal", "#FFFDE7", "#7D6608"],
	["learning", "#F3E5F5", "#6C3483"],
];
// the workbook's columns A to P, in its own widths
const HA_SHEET_WIDTHS = [5, 16, 36, 9, 8, 18, 8, 9, 18, 8, 9, 18, 8, 9, 10, 10];
const HA_SHEET_HEADS = [
	["#", "head"],
	["BSC\nPerspective", "head"],
	["KPI / Objective", "head"],
	["Timing", "head"],
	["Weight\n(total=80%)", "head"],
	["Q1 Comments", "head"],
	["Q1 %\nAchieved", "head dark"],
	["Q1 Wtd\nScore", "head dark"],
	["Q2 Comments", "head"],
	["Q2 %\nAchieved", "head dark"],
	["Q2 Wtd\nScore", "head dark"],
	["Q3 Comments", "head"],
	["Q3 %\nAchieved", "head dark"],
	["Q3 Wtd\nScore", "head dark"],
	["Annual\nScore\n(0–10)", "head"],
	["Annual\nWtd\nScore", "head"],
];
const HA_SIGNATORIES = [
	"Appraiser / Line Manager",
	"Employee / Appraisee",
	"HOD / Reviewing Manager",
	"HR Manager",
	"Executive Director",
];
const HA_SHEET_STYLE = `
.ha-bsc { overflow-x: auto; margin-bottom: var(--margin-md); }
.ha-bsc table { border-collapse: collapse; width: 100%; min-width: 1240px; table-layout: fixed;
	font-family: Arial, Helvetica, sans-serif; font-size: 11px; line-height: 1.3; color: #000; background: #fff; }
.ha-bsc td { border: 1px solid #7F7F7F; padding: 3px 5px; vertical-align: middle; overflow-wrap: anywhere;
	white-space: pre-wrap; height: 20px; }
.ha-bsc .c { text-align: center; }
.ha-bsc .r { text-align: right; }
.ha-bsc .b { font-weight: 700; }
.ha-bsc .i { font-style: italic; }
.ha-bsc .small { font-size: 10px; }
.ha-bsc .band { background: ${HA_SHEET.navy}; color: #fff; font-weight: 700; text-align: center; font-size: 12px; }
.ha-bsc .band.teal { background: ${HA_SHEET.teal}; }
.ha-bsc .head { background: ${HA_SHEET.teal}; color: #fff; font-weight: 700; text-align: center; font-size: 9px;
	padding: 3px 2px; overflow-wrap: normal; }
.ha-bsc .head.dark { background: ${HA_SHEET.tealDark}; }
.ha-bsc .head.gold { background: ${HA_SHEET.gold}; color: ${HA_SHEET.navy}; }
.ha-bsc .label { background: ${HA_SHEET.label}; font-weight: 700; }
.ha-bsc .note { background: ${HA_SHEET.note}; }
.ha-bsc .soft { background: ${HA_SHEET.soft}; }
.ha-bsc .cream { background: ${HA_SHEET.cream}; }
.ha-bsc .green { background: ${HA_SHEET.green}; }
.ha-bsc .grey { background: ${HA_SHEET.grey}; color: #666; }
.ha-bsc .weight { background: ${HA_SHEET.cream}; color: #1A5276; font-weight: 700; text-align: center; font-size: 12px; }
.ha-bsc .gold { background: ${HA_SHEET.gold}; font-weight: 700; text-align: center; }
.ha-bsc .total { background: ${HA_SHEET.teal}; color: #fff; font-weight: 700; text-align: center; }
.ha-bsc .company { font-size: 17px; letter-spacing: .5px; height: 34px; }
.ha-bsc .title { background: ${HA_SHEET.teal}; height: 30px; }
.ha-bsc .logo { background: #fff; text-align: left; }
.ha-bsc .logo img { max-height: 56px; max-width: 100%; }
.ha-bsc .kpi td { height: 40px; }
.ha-bsc .tall td { height: 56px; }
`;

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
		frm.trigger("show_form");
	},
	custom_form_type(frm) {
		frm.trigger("show_weights");
		frm.trigger("show_scale");
		frm.trigger("show_form");
	},
	show_form(frm) {
		ha_bsc_form(frm);
	},
	// what the form's header shows, redrawn as it is typed
	custom_designation: (frm) => frm.trigger("show_form"),
	custom_department: (frm) => frm.trigger("show_form"),
	custom_grade: (frm) => frm.trigger("show_form"),
	custom_review_period: (frm) => frm.trigger("show_form"),
	custom_review_year: (frm) => frm.trigger("show_form"),
	custom_company: (frm) => frm.trigger("show_form"),
	custom_form_reference: (frm) => frm.trigger("show_form"),
	custom_revision: (frm) => frm.trigger("show_form"),
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

// The scorecard template drawn as the workbook's form, into custom_form_view
function ha_bsc_form(frm) {
	const field = frm.get_field("custom_form_view");
	if (!field) return;
	if (frm.doc.custom_form_type !== HA_TEMPLATE_BSC) {
		field.$wrapper.empty();
		return;
	}
	if (!document.getElementById("ha-bsc-style")) {
		$('<style id="ha-bsc-style"></style>').text(HA_SHEET_STYLE).appendTo("head");
	}
	const esc = (value) => frappe.utils.escape_html(value === undefined || value === null ? "" : String(value));
	const td = (text, cls = "", span = 1, extra = "") =>
		`<td${span > 1 ? ` colspan="${span}"` : ""}${cls ? ` class="${cls}"` : ""}${extra}>${text}</td>`;
	const percent = (value) => (value || value === 0 ? `${esc(Math.round(value * 100) / 100)}%` : "");
	const band = (text, cls = "band") => `<tr>${td(esc(text), cls, 16)}</tr>`;
	const doc = frm.doc;
	const year = doc.custom_review_year || "";
	const rows = [];

	// the header: the logo, the company, the form; then who and what is appraised
	rows.push(
		`<tr>${td("", "logo", 4, ' rowspan="2"')}${td(
			esc(String(doc.custom_company || "").toUpperCase()),
			"band company",
			12
		)}</tr>`,
		`<tr>${td(
			esc(`PERFORMANCE MANAGEMENT SYSTEM  ·  BSC APPRAISAL FORM  ·  FY ${year}`),
			"band title",
			12
		)}</tr>`
	);
	for (const [left, leftValue, right, rightValue] of [
		["Role / Position:", doc.custom_designation, "Department:", doc.custom_department],
		["Employee Name:", "", "Grade:", doc.custom_grade],
		["Appraiser Name & Title:", "", "Review Period:", doc.custom_review_period],
		["Date of Review:", "", "HR Ref:", ""],
	]) {
		rows.push(
			`<tr>${td(esc(__(left)), "label", 2)}${td(esc(leftValue), "", 5)}${td(esc(__(right)), "label", 3)}${td(
				esc(rightValue),
				"",
				6
			)}</tr>`
		);
	}
	rows.push(
		`<tr>${td(
			esc(
				__(
					"HOW TO USE:  (1) Distribute the 80% weight across the perspectives: they must sum to 80%.  (2) Enter Q1–Q3 % Achieved against target: the quarterly weighted scores work themselves out.  (3) Enter the annual score (0–10) at year-end: the annual weighted score works itself out.  (4) Section B competencies = 20% of total.  RATING: Excellent ≥90  ·  Very Good 80–89  ·  Good 70–79  ·  Fair 60–69  ·  Poor <60"
				)
			),
			"note i small",
			16
		)}</tr>`
	);

	// Section A: each perspective's KPIs together, its weight on the first
	rows.push(
		band(
			__(
				"SECTION A  —  OBJECTIVES & KPIs  (80% of Total Score)  |  Distribute 80% weight across the perspectives"
			)
		),
		`<tr>${HA_SHEET_HEADS.map(([text, cls]) => td(esc(__(text)), cls)).join("")}</tr>`
	);
	const kpis = doc.custom_kpis || [];
	let weights = 0;
	(kpis.length ? kpis : [{}]).forEach((kpi, index) => {
		const first = index === 0 || kpi.perspective !== kpis[index - 1].perspective;
		const name = String(kpi.perspective || "").toLowerCase();
		const [, fill, text] = HA_PERSPECTIVE_COLOURS.find(([word]) => name.includes(word)) || [
			"",
			HA_SHEET.label,
			HA_SHEET.navy,
		];
		weights += kpi.weight || 0;
		rows.push(
			`<tr class="kpi">${td(index + 1, "label c")}${
				first
					? td(esc(kpi.perspective), "c b", 1, ` style="background:${fill};color:${text}"`)
					: td("↳", "grey c")
			}${td(esc(kpi.kpi))}${td(esc(kpi.timing), "label c small")}${td(
				first ? percent(kpi.weight) : "",
				first ? "weight" : "note"
			)}${["soft", "green", "soft", "label", "green", "soft", "soft", "green", "soft"]
				.map((cls) => td("", cls))
				.join("")}${td("", "cream")}${td("", "soft")}</tr>`
		);
	});
	const adds_up = Math.round(weights * 100) / 100 === 80;
	rows.push(
		`<tr>${td(esc(__("WEIGHT CHECK & QUARTERLY TOTALS")), "total r", 4)}${td(percent(weights), "gold")}${td(
			esc(
				adds_up
					? __("✓ Total = 80%")
					: __("⚠ Total must = 80%, currently {0}", [percent(weights)])
			),
			"note i",
			2
		)}${td("0", "total")}${td(esc(__("Q2 Total →")), "total r small")}${td("")}${td(
			"0",
			"total"
		)}${td(esc(__("Q3 Total →")), "total r small")}${td("")}${td("0", "total")}${td(
			esc(__("Sec A →")),
			"total r small"
		)}${td("0", "total")}</tr>`
	);

	// what else the appraisal records, and Section B from the template
	rows.push(
		band(
			__("OTHER ASSIGNMENTS / SPECIAL TASKS  (Record only — informational, not scored separately)")
		),
		`<tr>${td(esc(__("S/No & Task")), "head", 2)}${td(esc(__("Assignment Given")), "head", 4)}${td(
			esc(__("Expected Outcome")),
			"head",
			3
		)}${td(esc(__("Employee Comments")), "head", 4)}${td(esc(__("Supervisor Comments")), "head", 3)}</tr>`
	);
	for (const number of [1, 2, 3]) {
		rows.push(`<tr class="kpi">${td(number, "label c")}${td("")}${td("", "", 4)}${td("", "", 3)}${td("", "", 4)}${td("", "", 3)}</tr>`);
	}
	rows.push(
		band(__("SECTION B  —  COMPETENCIES  (20% of Total Score)  |  Score each 0–10  |  Weights must sum to 20%")),
		`<tr>${td(esc(__("Competency")), "head", 3)}${td(esc(__("Behavioural Indicators")), "head", 6)}${td(
			esc(__("Weight\n(%)")),
			"head",
			2
		)}${td(esc(__("Score\n(0–10)")), "head gold", 2)}${td(esc(__("Weighted\nScore")), "head", 3)}</tr>`
	);
	let competency_weights = 0;
	(doc.custom_competencies || []).forEach((row, index) => {
		competency_weights += row.weight || 0;
		rows.push(
			`<tr class="kpi">${td(esc(row.competency), "note b", 3)}${td(
				esc(row.indicators),
				`small ${index % 2 ? "" : "soft"}`,
				6
			)}${td(percent(row.weight), "weight", 2)}${td("", "", 2)}${td("", "soft", 3)}</tr>`
		);
	});
	const b_adds_up = Math.round(competency_weights * 100) / 100 === 20;
	rows.push(
		`<tr>${td(esc(__("COMPETENCY WEIGHT CHECK & SECTION B SCORE")), "total r", 9)}${td(
			percent(competency_weights),
			"gold",
			2
		)}${td(esc(b_adds_up ? __("✓ 20%") : __("⚠ Must = 20%")), "note i small", 2)}${td("0", "total", 3)}</tr>`
	);

	// the overall, the scale, and the parts the appraisal is signed and planned on
	rows.push(
		band(__("OVERALL PERFORMANCE SCORE   =   Section A (×0.8 already embedded in weights) + Section B")),
		`<tr>${td(esc(__("Section A Score  (sum of weighted KPI scores)")), "label r", 15)}${td("0", "label c b")}</tr>`,
		`<tr>${td(esc(__("Section B Score  (sum of weighted competency scores)")), "label r", 15)}${td(
			"0",
			"label c b"
		)}</tr>`,
		`<tr>${td(esc(__("OVERALL SCORE  (Section A + Section B)")), "gold r", 15, ' style="color:#fff"')}${td(
			"0",
			"gold",
			1,
			' style="color:#fff"'
		)}</tr>`,
		band(__("PERFORMANCE RATING SCALE"), "band teal")
	);
	const scale = HA_SCALES[HA_TEMPLATE_BSC];
	const spans = [3, 3, 3, 3, 4];
	rows.push(
		`<tr>${scale
			.map(([name, range, colour], index) =>
				td(esc(`${__(name)}  ${range}`), "c b small", spans[index], ` style="background:${colour};color:#fff"`)
			)
			.join("")}</tr>`,
		`<tr>${scale.map(([, , , meaning], index) => td(esc(__(meaning)), "label c small", spans[index])).join("")}</tr>`,
		band(__("PART D  —  COMMENTS & SIGNATURES"))
	);
	for (const who of HA_SIGNATORIES) {
		rows.push(
			`<tr class="kpi">${td(esc(__(who)), "label", 2)}${td(
				esc(__("Comments:")) + " _______________________________________________",
				"",
				7
			)}${td(esc(__("Name:")) + " _______________________  " + esc(__("Sig:")) + " __________________  " + esc(__("Date:")) + " ________", "small", 7)}</tr>`
		);
	}
	rows.push(
		band(__("PART E  —  DEVELOPMENT PLAN")),
		`<tr>${td(esc(__("Continue / Strengths")), "head", 5)}${td(esc(__("Stop / Weaknesses")), "head", 5)}${td(
			esc(__("Start / Gaps to Fill")),
			"head",
			6
		)}</tr>`,
		`<tr class="tall">${td("", "", 5)}${td("", "", 5)}${td("", "", 6)}</tr>`,
		`<tr>${td(esc(__("Development Action")), "head", 6)}${td(esc(__("Duration")), "head", 3)}${td(
			esc(__("By When")),
			"head",
			3
		)}${td(esc(__("By Whom")), "head", 2)}${td(esc(__("Est. Cost ({0})", ["UGX"])), "head ha-bsc-currency", 2)}</tr>`
	);
	for (let index = 0; index < 3; index++) {
		rows.push(`<tr class="kpi">${td("", "", 6)}${td("", "", 3)}${td("", "", 3)}${td("", "", 2)}${td("", "", 2)}</tr>`);
	}
	rows.push(
		`<tr>${td(
			esc(
				[
					doc.custom_company,
					`PMS BSC Appraisal Form FY ${year}`,
					doc.custom_department,
					doc.custom_form_reference,
					"CONFIDENTIAL",
					doc.custom_revision,
				]
					.filter(Boolean)
					.join("  |  ")
			),
			"band small",
			16
		)}</tr>`
	);

	field.$wrapper.html(
		`<div class="ha-bsc"><table><colgroup>${HA_SHEET_WIDTHS.map(
			(width) => `<col style="width:${((100 * width) / 191).toFixed(2)}%">`
		).join("")}</colgroup><tbody>${rows.join("")}</tbody></table></div>`
	);
	// the company's logo and currency, as the offline sheet carries them
	if (doc.custom_company) {
		frappe.db.get_value("Company", doc.custom_company, ["company_logo", "default_currency"]).then((r) => {
			const company = (r && r.message) || {};
			const logo = company.company_logo || "";
			if (logo && /^(\/|https?:\/\/)/.test(logo)) {
				field.$wrapper.find("td.logo").html(`<img src="${esc(logo)}" alt="">`);
			}
			if (company.default_currency) {
				field.$wrapper.find("td.ha-bsc-currency").text(__("Est. Cost ({0})", [company.default_currency]));
			}
		});
	}
}

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

// the headline and the form move as the rows are typed, not only when the
// template is saved
frappe.ui.form.on("BSC Template KPI", {
	weight(frm) {
		frm.trigger("show_weights");
		frm.trigger("show_form");
	},
	perspective(frm) {
		frm.fields_dict.custom_kpis.grid.refresh();
		frm.trigger("show_form");
	},
	kpi: (frm) => frm.trigger("show_form"),
	timing: (frm) => frm.trigger("show_form"),
	custom_kpis_add: (frm) => frm.trigger("show_form"),
	custom_kpis_remove(frm) {
		frm.trigger("show_weights");
		frm.trigger("show_form");
	},
});

frappe.ui.form.on("BSC Template Competency", {
	weight(frm) {
		frm.trigger("show_weights");
		frm.trigger("show_form");
	},
	competency: (frm) => frm.trigger("show_form"),
	indicators: (frm) => frm.trigger("show_form"),
	custom_competencies_add: (frm) => frm.trigger("show_form"),
	custom_competencies_remove(frm) {
		frm.trigger("show_weights");
		frm.trigger("show_form");
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
