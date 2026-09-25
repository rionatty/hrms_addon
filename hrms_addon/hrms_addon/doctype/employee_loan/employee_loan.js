// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

const HA_LOANS = "hrms_addon.hrms_addon.loans.";

frappe.ui.form.on("Employee Loan", {
	refresh(frm) {
		frm.trigger("show_loan");
		const roles = (list) => list.some((role) => frappe.user.has_role(role));
		const accounts = roles(["Accounts User", "Accounts Manager", "System Manager"]);
		// chart step 3: Accounts pay the loan out once the employee has consented
		if (
			accounts &&
			frm.doc.docstatus === 0 &&
			frm.doc.workflow_state === "Pending Employee Consent" &&
			frm.doc.consent &&
			!frm.doc.disbursement_entry
		) {
			frm.add_custom_button(__("Record Payment"), () => ha_loan_journal(frm, "Payment"));
		}
		if (frm.doc.docstatus === 1 && frm.doc.status === "Running") {
			if (accounts) {
				frm.add_custom_button(__("Record Repayment"), () => ha_loan_journal(frm, "Repayment"));
			}
			if (roles(["Accounts Manager", "HR Manager", "System Manager"])) {
				frm.add_custom_button(__("Write Off"), () =>
					frappe.confirm(__("Write off the {0} still owed?", [ha_money(frm.doc.outstanding)]), () =>
						ha_loan_journal(frm, "Write Off")
					)
				);
			}
			frm.add_custom_button(__("Mark Recovered"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.recoveries.catch_up_for", {
						doctype: frm.doctype,
						name: frm.doc.name,
					})
					.then(() => frm.reload_doc())
			);
		}
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Loan Statement"), () =>
				frappe.set_route("query-report", "Loan Statement", { loan: frm.doc.name })
			);
		}
	},
	// "Approved?" on the chart rests on this, so say it before anyone signs.
	show_loan(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new() || !frm.doc.employee) return;
		const ok = frm.doc.qualifies;
		const parts = [`${__("Limit")} <b>${ha_money(frm.doc.limit)}</b>`];
		if (frm.doc.monthly_instalment) {
			parts.push(`${__("Monthly")} <b>${ha_money(frm.doc.monthly_instalment)}</b>`);
		}
		if (frm.doc.docstatus === 1) {
			parts.push(`${__("Outstanding")} <b>${ha_money(frm.doc.outstanding)}</b>`);
		}
		let pills = "";
		if (frm.doc.docstatus === 0) {
			pills += ` <span class="indicator-pill ${ok ? "green" : "orange"}">${
				ok ? __("Qualifies") : __("Does not qualify")
			}</span>`;
		}
		if (frm.doc.workflow_state === "Pending Employee Consent") {
			pills += frm.doc.disbursement_entry
				? ` <span class="indicator-pill green">${__("Paid out")}</span>`
				: ` <span class="indicator-pill orange">${__("Not paid out yet")}</span>`;
		}
		frm.dashboard.set_headline(
			`<span>${parts.join(" &nbsp;|&nbsp; ")}</span>` +
				pills +
				(ok || frm.doc.docstatus !== 0
					? ""
					: ` <span class="text-muted">${frappe.utils.escape_html(
							frm.doc.eligibility_remarks || ""
					  )}</span>`)
		);
	},
	approved_amount(frm) {
		if (frm.doc.approved_amount && !frm.doc.liability) {
			frm.set_value("liability", __("Staff loan of {0}", [ha_money(frm.doc.approved_amount)]));
		}
		ha_loan_schedule(frm);
	},
	employee: ha_loan_schedule,
	posting_date: ha_loan_schedule,
	loan_amount: ha_loan_schedule,
	instalments: ha_loan_schedule,
	interest_rate: ha_loan_schedule,
	first_repayment: ha_loan_schedule,
});

function ha_money(value) {
	return frappe.format(value || 0, { fieldtype: "Currency" });
}

// the schedule is drawn as the request is filled in, the way saving draws it
function ha_loan_schedule(frm) {
	if (frm.doc.docstatus !== 0 || !frm.doc.loan_amount) return;
	frappe.xcall(HA_LOANS + "preview_schedule", { doc: frm.doc }).then((drawn) => {
		if (!drawn) return;
		frm.clear_table("repayments");
		drawn.repayments.forEach((row) => frm.add_child("repayments", row));
		Object.assign(frm.doc, {
			interest_rate: drawn.interest_rate,
			total_interest: drawn.total_interest,
			monthly_instalment: drawn.monthly_instalment,
		});
		["repayments", "interest_rate", "total_interest", "monthly_instalment"].forEach((field) =>
			frm.refresh_field(field)
		);
		frm.trigger("show_loan");
	});
}

// the entry is drafted for Accounts; the loan follows when it is submitted
function ha_loan_journal(frm, purpose) {
	frappe.xcall(HA_LOANS + "make_journal", { loan: frm.doc.name, purpose: purpose }).then((entry) => {
		const doclist = frappe.model.sync(entry);
		frappe.set_route("Form", doclist[0].doctype, doclist[0].name);
	});
}
