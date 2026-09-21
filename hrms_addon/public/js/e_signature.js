// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The Sign button, and the signatures a document already carries.
//
// A desk-wide script rather than a form script per doctype: the same
// button on seventeen forms is one thing, not seventeen, and putting it
// here means a new signable document needs one line in signature_rules.py
// and nothing else.
//
// A plain asset path in app_include_js, so no `bench build` is needed.

frappe.provide("hrms_addon.signatures");

hrms_addon.signatures.DOCTYPES = [
	"Employee Contract",
	"Disciplinary Case",
	"Appraisal",
	"Performance Review",
	"Performance Improvement Plan",
	"Probation Evaluation",
	"Travel Request",
	"Expense Claim",
	"Employee Advance",
	"Employee Loan",
	"Employee Separation",
	"Clearance Form",
	"Employee Data Change Request",
	"Employee Position Change",
	"Off Duty Request",
	"Overtime Request",
	"Gate Pass",
];

hrms_addon.signatures.STEPS = [
	"Prepared",
	"Reviewed",
	"Approved",
	"Acknowledged",
	"Witnessed",
	"Received",
];

hrms_addon.signatures.show = function (frm) {
	frm.dashboard.wrapper.find(".hra-signatures").remove();
	if (frm.is_new()) return;
	frappe
		.xcall("hrms_addon.hrms_addon.signatures.signatures_on", {
			doctype: frm.doc.doctype,
			name: frm.doc.name,
		})
		.then((rows) => {
			if (!rows || !rows.length) return;
			const lines = rows
				.map((row) => {
					const who = frappe.utils.escape_html(row.employee_name || row.signatory || "");
					const when = row.signed_on ? frappe.datetime.str_to_user(row.signed_on) : "";
					const mark = row.has_specimen
						? `<span class="indicator-pill green">${__("signed")}</span>`
						: `<span class="indicator-pill gray">${__("no specimen on file")}</span>`;
					return (
						`<div style="padding:4px 0;border-bottom:1px solid var(--border-color)">` +
						`<b>${frappe.utils.escape_html(row.step || "")}</b> — ${who}` +
						` <span class="text-muted">${when}</span> ${mark}` +
						`<div class="text-muted" style="font-size:11px">${frappe.utils.escape_html(
							row.statement || ""
						)}</div></div>`
					);
				})
				.join("");
			frm.dashboard.wrapper.prepend(
				`<div class="hra-signatures" style="margin:8px 0 12px">` +
					`<div class="text-muted" style="font-size:11px;text-transform:uppercase;letter-spacing:.5px">${__(
						"Signatures"
					)}</div>${lines}</div>`
			);
		});
};

hrms_addon.signatures.ask = function (frm) {
	frappe.prompt(
		[
			{
				fieldname: "step",
				fieldtype: "Select",
				label: __("Signing As"),
				options: hrms_addon.signatures.STEPS,
				default: "Approved",
				reqd: 1,
			},
			{
				fieldname: "statement",
				fieldtype: "Small Text",
				label: __("What You Are Signing To"),
				description: __("Left empty, the wording for the step is used."),
			},
			{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") },
		],
		(values) =>
			frappe
				.xcall("hrms_addon.hrms_addon.signatures.sign", {
					doctype: frm.doc.doctype,
					name: frm.doc.name,
					step: values.step,
					statement: values.statement,
					remarks: values.remarks,
				})
				.then((signed) => {
					frappe.show_alert({
						message: signed.has_specimen
							? __("Signed as {0}.", [signed.step])
							: __("Signed as {0}. There is no specimen on your record.", [signed.step]),
						indicator: signed.has_specimen ? "green" : "orange",
					});
					hrms_addon.signatures.show(frm);
				}),
		__("Sign this document"),
		__("Sign")
	);
};

hrms_addon.signatures.DOCTYPES.forEach((doctype) => {
	frappe.ui.form.on(doctype, {
		refresh(frm) {
			if (frm.is_new()) return;
			frm.add_custom_button(__("Sign"), () => hrms_addon.signatures.ask(frm));
			hrms_addon.signatures.show(frm);
		},
	});
});
