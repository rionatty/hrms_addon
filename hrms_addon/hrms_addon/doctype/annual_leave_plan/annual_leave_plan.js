// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

const HA_LEAVE = "hrms_addon.hrms_addon.leave.";
const HA_PLAN_HR = ["HR User", "HR Manager", "System Manager"];

frappe.ui.form.on("Annual Leave Plan", {
	refresh(frm) {
		const hr = frappe.user.has_role(HA_PLAN_HR);
		const drawing_up = frm.doc.docstatus === 0 && ["Draft", undefined, null, ""].includes(frm.doc.workflow_state);
		if (hr && drawing_up && frm.doc.company) {
			frm.add_custom_button(__("Get Employees"), () => ha_get_employees(frm));
		}
		if (frm.doc.docstatus === 1) {
			if (hr) {
				frm.add_custom_button(__("Tell the Employees"), () =>
					frappe.xcall(HA_LEAVE + "inform_employees", { plan: frm.doc.name }).then((told) => {
						frappe.show_alert({
							message: __("{0} employee(s) told their leave dates.", [told]),
							indicator: "green",
						});
						frm.reload_doc();
					})
				);
			}
			ha_my_rows(frm).then((mine) => {
				const rows = hr ? frm.doc.employees || [] : mine;
				if (rows.length) {
					frm.add_custom_button(__("Change Dates"), () => ha_change_dates(frm, rows));
				}
				const open = mine.filter((row) => !row.leave_application);
				if (open.length) {
					frm.add_custom_button(__("Apply for My Leave"), () => ha_apply(open));
				}
			});
		}
		frm.trigger("show_totals");
	},
	// how the plan stands: over what people have, no days on record, clashes
	show_totals(frm) {
		frm.dashboard.clear_headline();
		const rows = (frm.doc.employees || []).filter((row) => row.employee);
		if (!rows.length) return;
		const planned = {};
		rows.forEach((row) => {
			const entry = (planned[row.employee] = planned[row.employee] || { days: 0, available: 0 });
			entry.days += row.planned_days || 0;
			entry.available = Math.max(entry.available, row.available_days || 0);
		});
		const people = Object.values(planned);
		const over = people.filter((entry) => entry.available && entry.days > entry.available).length;
		const unknown = people.filter((entry) => !entry.available).length;
		const clashes = (frm.doc.clashes || "").split("\n").filter(Boolean).length;
		const pill = (count, text, colour) =>
			count ? ` <span class="indicator-pill ${colour}">${__(text, [count])}</span>` : "";
		frm.dashboard.set_headline(
			`<span>${__("Employees")} <b>${people.length}</b> &nbsp;|&nbsp; ${__("Days planned")} <b>${
				frm.doc.total_days || 0
			}</b></span>` +
				pill(over, "{0} planned for more than they have", "orange") +
				pill(unknown, "{0} with no leave on record", "orange") +
				pill(clashes, "{0} clash(es)", "red") +
				(over || unknown || clashes ? "" : ` <span class="indicator-pill green">${__("Within what each has")}</span>`)
		);
	},
	year(frm) {
		if (frm.doc.year && !frm.doc.posting_date) {
			frm.set_value("posting_date", frappe.datetime.get_today());
		}
	},
});

function ha_get_employees(frm) {
	// an empty row would stop the save
	(frm.doc.employees || [])
		.filter((row) => !row.employee)
		.forEach((row) => frappe.model.clear_doc(row.doctype, row.name));
	frm.refresh_field("employees");
	const fetch = () =>
		frappe.xcall(HA_LEAVE + "get_employees", { plan: frm.doc.name }).then((added) => {
			frappe.show_alert({ message: __("{0} employee(s) added.", [added]), indicator: "green" });
			frm.reload_doc();
		});
	if (frm.is_new() || frm.is_dirty()) {
		frm.save().then(fetch);
	} else {
		fetch();
	}
}

// the rows of the plan that are the signed-in employee's own
function ha_my_rows(frm) {
	return frappe.db.get_value("Employee", { user_id: frappe.session.user }, "name").then((r) => {
		const me = r && r.message && r.message.name;
		return (frm.doc.employees || []).filter((row) => me && row.employee === me);
	});
}

function ha_row_label(row) {
	return __("{0}: {1} to {2}", [
		row.employee_name || row.employee,
		frappe.datetime.str_to_user(row.planned_from),
		frappe.datetime.str_to_user(row.planned_to),
	]);
}

function ha_change_dates(frm, rows) {
	const choices = rows.map((row) => ({ value: row.name, label: ha_row_label(row) }));
	const dialog = new frappe.ui.Dialog({
		title: __("Change Dates"),
		fields: [
			{ fieldname: "row", fieldtype: "Select", label: __("Planned Leave"), options: choices, reqd: 1,
				default: choices[0].value },
			{ fieldname: "new_from", fieldtype: "Date", label: __("New From"), reqd: 1 },
			{ fieldname: "column_break_1", fieldtype: "Column Break" },
			{ fieldname: "new_to", fieldtype: "Date", label: __("New To"), reqd: 1 },
			{ fieldname: "section_break_1", fieldtype: "Section Break" },
			{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			frappe.xcall(HA_LEAVE + "request_change", values).then((name) => {
				dialog.hide();
				frappe.set_route("Form", "Leave Plan Change", name);
			});
		},
	});
	dialog.show();
}

function ha_apply(rows) {
	const apply = (row) =>
		frappe.xcall(HA_LEAVE + "apply_from_plan", { row }).then((name) =>
			frappe.set_route("Form", "Leave Application", name)
		);
	if (rows.length === 1) {
		apply(rows[0].name);
		return;
	}
	frappe.prompt(
		{ fieldname: "row", fieldtype: "Select", label: __("Planned Leave"), reqd: 1,
			options: rows.map((row) => ({ value: row.name, label: ha_row_label(row) })) },
		(values) => apply(values.row),
		__("Apply for My Leave"),
		__("Apply")
	);
}
