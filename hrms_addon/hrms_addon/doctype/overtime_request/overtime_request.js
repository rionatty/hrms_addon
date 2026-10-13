// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// LPL/HR/14. It is approved from the Actions menu, as every other request
// is (overtime_approval.py): Submit, Approve by the authorising officer,
// Approve by HR, which works out the cost and submits it. The hours go to
// payroll by themselves once the day's attendance is in; HR can send them
// from here, which says what stops them.

frappe.ui.form.on("Overtime Request", {
	refresh(frm) {
		const status = frm.doc.status;
		if (
			["Authorised", "Costed", "Sent to Payroll"].includes(status) &&
			!frm.doc.coupons_issued &&
			frm.has_perm("write")
		) {
			frm.add_custom_button(__("Issue Food Coupons"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.attendance.issue_coupons", { name: frm.doc.name })
					.then((found) => {
						frappe.show_alert({
							message: __("{0} permanent and {1} casual coupon(s).", [
								found.permanent,
								found.casual,
							]),
							indicator: "green",
						});
						frm.reload_doc();
					})
			);
		}
		if (frm.doc.docstatus === 1 && status === "Costed" && frm.has_perm("submit")) {
			frm.add_custom_button(__("Send to Payroll"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.overtime.send_to_payroll", { name: frm.doc.name })
					.then((found) => {
						frappe.show_alert({
							message: __("{0} attendance row(s) marked, {1} overtime slip(s).", [
								found.attendance_marked,
								(found.slips || []).length,
							]),
							indicator: "green",
						});
						frm.reload_doc();
					})
			);
		}
		frm.trigger("say_where_it_stands");
	},
	// one line under the title: what sort of day it is, and where the request
	// stands. No rate here: each line carries its own
	say_where_it_stands(frm) {
		if (frm.is_new()) return;
		const cost = format_currency(frm.doc.total_cost);
		const stands = {
			Requested: [__("Waiting for the authorising officer."), "orange"],
			Authorised: [__("Authorised. Waiting for HR to approve the cost."), "orange"],
			Costed: [__("Approved at {0}. The hours go to payroll once the day's attendance is in.", [cost]), "blue"],
			"Sent to Payroll": [__("With payroll at {0}. The overtime slip pays it.", [cost]), "green"],
			Rejected: [__("Refused."), "red"],
		}[frm.doc.status];
		const day = frm.doc.day_kind
			? `<span class="indicator-pill ${frm.doc.day_kind === "Weekday" ? "blue" : "orange"}">${__(
					frm.doc.day_kind
			  )}</span> `
			: "";
		if (!stands && !day) return;
		frm.set_intro(day + (stands ? stands[0] : ""), stands ? stands[1] : "blue");
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.overtime_date) {
			frm.set_value("overtime_date", frappe.datetime.get_today());
		}
	},
	setup(frm) {
		frm.set_query("employee", "employees", () => ({ filters: { status: "Active" } }));
	},
});
