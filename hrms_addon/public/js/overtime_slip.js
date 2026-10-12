// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Frappe HR's Overtime Slip. It reads the attendance, and overtime is
// written there only when its Overtime Request is sent to payroll, so a
// slip made while a request is still on its way finds nothing and says
// only that there is no attendance. Those requests are named on the slip
// with the step each waits for (overtime.waiting).
// doctype_js, read from disk when the form loads: no `bench build`.

frappe.ui.form.on("Overtime Slip", {
	refresh(frm) {
		ha_overtime_waiting(frm);
	},
	start_date(frm) {
		ha_overtime_waiting(frm);
	},
	end_date(frm) {
		ha_overtime_waiting(frm);
	},
});

function ha_overtime_waiting(frm) {
	const doc = frm.doc;
	if (doc.docstatus !== 0 || !doc.employee || !doc.start_date || !doc.end_date) return;
	const asked = [doc.employee, doc.start_date, doc.end_date].join("|");
	frappe
		.call({
			method: "hrms_addon.hrms_addon.overtime.waiting",
			args: { employee: doc.employee, start_date: doc.start_date, end_date: doc.end_date },
		})
		.then((r) => {
			// the form has moved on to another employee or other dates
			if (asked !== [frm.doc.employee, frm.doc.start_date, frm.doc.end_date].join("|")) return;
			const rows = r.message || [];
			if (!rows.length) {
				if (frm.ha_overtime_waiting_shown) frm.set_intro("");
				frm.ha_overtime_waiting_shown = false;
				return;
			}
			const cell = (text) => frappe.utils.escape_html(text == null ? "" : String(text));
			const lines = rows
				.map(
					(row) =>
						`<li><a href="/app/overtime-request/${encodeURIComponent(row.name)}">${cell(row.name)}</a>, ` +
						`${cell(frappe.datetime.str_to_user(row.overtime_date))}, ` +
						`${row.hours === 1 ? __("1 hour") : __("{0} hours", [cell(row.hours)])}: ${cell(__(row.status))}. ` +
						`${__("Next: {0}", [cell(__(row.next))])}</li>`
				)
				.join("");
			frm.set_intro(
				`${__("Overtime in these dates that has not reached payroll:")}<ul style="margin: 4px 0 0">${lines}</ul>`,
				"orange"
			);
			frm.ha_overtime_waiting_shown = true;
		});
}
