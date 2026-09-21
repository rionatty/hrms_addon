// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Overtime Request", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status === "Requested" && frm.has_perm("submit")) {
			frm.add_custom_button(__("Authorise"), () =>
				frappe.prompt(
					{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") },
					(values) =>
						frappe
							.xcall("hrms_addon.hrms_addon.attendance.authorise_overtime", {
								name: frm.doc.name,
								remarks: values.remarks,
							})
							.then(() => frm.reload_doc()),
					__("Authorise the overtime"),
					__("Authorise")
				)
			);
			frm.add_custom_button(__("Reject"), () =>
				frappe.prompt(
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
					(values) =>
						frappe
							.xcall("hrms_addon.hrms_addon.attendance.reject_overtime", {
								name: frm.doc.name,
								reason: values.reason,
							})
							.then(() => frm.reload_doc()),
					__("Reject the overtime"),
					__("Reject")
				)
			);
		}
		if (frm.doc.status === "Authorised" && !frm.doc.coupons_issued) {
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
		// the third step of the chain: HR check what it costs before it
		// goes anywhere near payroll
		if (frm.doc.status === "Authorised" && frm.has_perm("write")) {
			frm.add_custom_button(__("Check the Cost"), () =>
				frappe.prompt(
					[
						{
							fieldname: "cost_centre",
							fieldtype: "Link",
							options: "Cost Center",
							label: __("Cost Centre"),
							reqd: 1,
							default: frm.doc.cost_centre,
						},
						{ fieldname: "remarks", fieldtype: "Small Text", label: __("HR Remarks") },
					],
					(values) =>
						frappe
							.xcall("hrms_addon.hrms_addon.overtime.cost_check", {
								name: frm.doc.name,
								cost_centre: values.cost_centre,
								remarks: values.remarks,
							})
							.then((found) => {
								frappe.show_alert({
									message: __("{0} at {1}x on a {2}.", [
										format_currency(found.total),
										found.multiplier,
										found.kind,
									]),
									indicator: "green",
								});
								frm.reload_doc();
							}),
					__("What this overtime costs"),
					__("Cost")
				)
			);
		}
		if (frm.doc.status === "Costed" && frm.has_perm("submit")) {
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
		if (frm.doc.status === "Authorised") {
			frm.set_intro(__("Authorised. HR issue the coupons and check the cost."), "green");
		} else if (frm.doc.status === "Costed") {
			frm.set_intro(
				__("Costed at {0}. Sending it to payroll marks the attendance and draws the overtime slips.", [
					format_currency(frm.doc.total_cost),
				]),
				"blue"
			);
		} else if (frm.doc.status === "Sent to Payroll") {
			frm.set_intro(__("With payroll. The overtime slip prices it and pays it."), "green");
		} else if (frm.doc.status === "Rejected") {
			frm.set_intro(__("Not authorised."), "red");
		}
		frm.trigger("say_the_day");
	},
	// the rate is set by what sort of day it is, so the form says which
	say_the_day(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new() || !frm.doc.day_kind) return;
		const colour = frm.doc.day_kind === "Weekday" ? "blue" : "orange";
		frm.dashboard.set_headline(
			`<span class="indicator-pill ${colour}">${__(frm.doc.day_kind)}</span>` +
				(frm.doc.multiplier ? ` <span>${__("paid at")} <b>${frm.doc.multiplier}x</b></span>` : "") +
				(frm.doc.total_cost
					? ` <span>${__("costing")} <b>${format_currency(frm.doc.total_cost)}</b></span>`
					: "")
		);
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
