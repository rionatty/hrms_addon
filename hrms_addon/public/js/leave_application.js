// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// LPL/HR/15 on Frappe HR's own Leave Application. Part 2 is the HR
// Officer's balances, with the leave earned by the days worked
// (leave_accrual.py); Part 3 the three signatures and Part 4 the Leave
// Advance, raised when the leave is approved (leave_advances.py).
//
// doctype_js, read from disk when the form loads, so a change to it needs
// no `bench build`.

frappe.ui.form.on("Leave Application", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status === "Approved") {
			if (frm.doc.custom_leave_advance) {
				frm.add_custom_button(__("Leave Advance"), () =>
					frappe.set_route("Form", "Leave Advance", frm.doc.custom_leave_advance)
				);
			} else if (frm.doc.custom_salary_requested_in_advance && !frm.doc.custom_advance) {
				frm.add_custom_button(__("Raise Leave Advance"), () =>
					frappe
						.xcall("hrms_addon.hrms_addon.leave.raise_advance", {
							leave_application: frm.doc.name,
						})
						.then((advance) => {
							frappe.show_alert({
								message: __("Leave advance {0} raised.", [advance]),
								indicator: "green",
							});
							frappe.set_route("Form", "Leave Advance", advance);
						})
				);
			}
			if (!frm.doc.custom_reported_back) {
				frm.add_custom_button(__("Mark Reported Back"), () =>
					frm.set_value("custom_reported_back", 1).then(() => frm.save("Update"))
				);
			}
		}
		frm.trigger("show_balances");
	},
	// Part 2 of the form, said once at the top: what has been earned, what
	// can be taken, and what is left after this leave.
	show_balances(frm) {
		frm.dashboard.clear_headline();
		const parts = [];
		if (frm.doc.custom_earned_by && frm.doc.custom_leave_earned !== null && frm.doc.custom_leave_earned !== undefined) {
			parts.push(
				__("Earned by {0}: {1} from {2} day(s) worked", [
					frappe.datetime.str_to_user(frm.doc.custom_earned_by),
					`<b>${frm.doc.custom_leave_earned}</b>`,
					frm.doc.custom_days_worked || 0,
				])
			);
			parts.push(__("Can be taken: {0}", [`<b>${frm.doc.custom_leave_available || 0}</b>`]));
		}
		if (frm.doc.custom_balance_before) {
			parts.push(
				`${__("Leave due before")} <b>${frm.doc.custom_balance_before}</b>, ${__("after")} <b>${
					frm.doc.custom_balance_after || 0
				}</b>`
			);
		}
		if (!parts.length) return;
		const over =
			frm.doc.custom_earned_by &&
			(frm.doc.total_leave_days || 0) > (frm.doc.custom_leave_available || 0) + 0.000001;
		frm.dashboard.set_headline(
			`<span>${parts.join(" &nbsp;|&nbsp; ")}</span> <span class="indicator-pill ${over ? "red" : "green"}">${
				over ? __("More than earned") : __("Within what is earned")
			}</span>`
		);
	},
	// the Part 2 figures, as the employee, the type and the dates are typed in
	earned(frm) {
		if (frm.doc.docstatus !== 0 || !frm.doc.employee || !frm.doc.leave_type || !frm.doc.from_date) return;
		frappe
			.xcall("hrms_addon.hrms_addon.leave_accrual.get_application_accrual", {
				employee: frm.doc.employee,
				leave_type: frm.doc.leave_type,
				from_date: frm.doc.from_date,
				to_date: frm.doc.to_date,
				posting_date: frm.doc.posting_date,
				name: frm.is_new() ? null : frm.doc.name,
			})
			.then((found) => {
				const values = found
					? {
							custom_leave_earned: found.earned,
							custom_earned_by: found.earned_by,
							custom_days_worked: found.days_worked,
							custom_leave_brought_forward: found.brought_forward,
							custom_leave_available: found.available,
					  }
					: {
							custom_leave_earned: null,
							custom_earned_by: null,
							custom_days_worked: null,
							custom_leave_brought_forward: null,
							custom_leave_available: null,
					  };
				Object.entries(values).forEach(([field, value]) => (frm.doc[field] = value));
				frm.refresh_fields(Object.keys(values));
				frm.trigger("show_balances");
			});
	},
	employee(frm) {
		frm.trigger("earned");
	},
	leave_type(frm) {
		// the two the form asks for a certificate with are the two it
		// marks "(Attach Medical Certificate)"
		frm.refresh_field("custom_medical_certificate");
		frm.trigger("earned");
	},
	from_date(frm) {
		frm.trigger("earned");
	},
	to_date(frm) {
		frm.trigger("earned");
	},
	total_leave_days(frm) {
		frm.trigger("show_balances");
	},
	custom_balance_before(frm) {
		frm.trigger("show_balances");
	},
});
