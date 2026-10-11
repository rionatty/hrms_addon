// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// Frappe HR's Salary Structure Assignment. The onboarding and the position
// change that made an assignment keep it as a record, so cancelling the
// assignment to correct it leaves them, and what follows them, as they are
// (salary_structures.keep_records lets the cancel through).
//
// The Allowances panel lists what the employee is paid every month besides
// the structure and changes it without touching the assignment: each
// allowance is a recurring Additional Salary (standing_allowances.py).
// doctype_js, read from disk when the form loads: no `bench build`.

frappe.ui.form.on("Salary Structure Assignment", {
	setup(frm) {
		frm.ignore_doctypes_on_cancel_all = [
			...new Set([
				...(frm.ignore_doctypes_on_cancel_all || []),
				"Employee Onboarding",
				"Employee Position Change",
			]),
		];
	},
	refresh(frm) {
		ha_standing_allowances(frm);
	},
	employee(frm) {
		ha_standing_allowances(frm);
	},
});

const HA_STANDING = "hrms_addon.hrms_addon.standing_allowances.";

function ha_standing_wrapper(frm) {
	const field = frm.fields_dict.custom_allowances_html;
	return field ? field.$wrapper : null;
}

// draws the panel for the employee on the form, as the server has it now
function ha_standing_allowances(frm) {
	const wrapper = ha_standing_wrapper(frm);
	if (!wrapper) return;
	const employee = frm.doc.employee;
	if (!employee) {
		wrapper.html(`<p class="text-muted">${__("Choose the employee.")}</p>`);
		return;
	}
	frappe.call({ method: HA_STANDING + "allowances", args: { employee } }).then((r) => {
		// the employee may have been changed while this was on its way
		if (frm.doc.employee !== employee) return;
		ha_standing_draw(frm, wrapper, r.message || {});
	});
}

function ha_standing_money(value, currency) {
	return format_currency(value || 0, currency);
}

function ha_standing_day(value) {
	return value ? frappe.datetime.str_to_user(value) : "";
}

function ha_standing_draw(frm, wrapper, data) {
	const rows = data.rows || [];
	const shown = rows.filter((row) => frm.ha_standing_ended || row.state !== "Ended");
	const ended = rows.length - rows.filter((row) => row.state !== "Ended").length;
	const cell = (text) => frappe.utils.escape_html(text == null ? "" : String(text));
	const action = (what, row, label) =>
		`<button type="button" class="btn btn-xs btn-default" data-ha-standing="${what}" ` +
		`data-name="${cell(row.name)}">${label}</button>`;
	const lines = shown
		.map((row) => {
			const buttons = [];
			if (data.can_change) {
				if (row.state !== "Ended") buttons.push(action("change", row, __("Change Amount")));
				buttons.push(action("end", row, row.state === "Ended" ? __("Extend") : __("End")));
				if (!row.paid) buttons.push(action("remove", row, __("Remove")));
			}
			const muted = row.state === "Ended" ? ' class="text-muted"' : "";
			const starts = row.state === "Starts" ? ` <span class="text-muted">${__("not started")}</span>` : "";
			return (
				`<tr${muted}><td>${cell(row.salary_component)}${starts}</td>` +
				`<td class="text-right">${ha_standing_money(row.amount, data.currency)}</td>` +
				`<td>${ha_standing_day(row.from_date)}</td><td>${ha_standing_day(row.to_date)}</td>` +
				`<td class="text-right">${buttons.join(" ")}</td></tr>`
			);
		})
		.join("");
	const none = `<tr><td colspan="5" class="text-muted">${__("No allowances.")}</td></tr>`;
	const add = data.can_change && data.assigned
		? `<button type="button" class="btn btn-xs btn-primary" data-ha-standing="add">${__("Add Allowance")}</button>`
		: "";
	const hint = data.assigned ? "" : `<p class="text-muted">${__("Allowances can be added once the employee has a submitted assignment.")}</p>`;
	const toggle = ended
		? ` <button type="button" class="btn btn-xs btn-default" data-ha-standing="ended">` +
		  `${frm.ha_standing_ended ? __("Hide Ended") : __("Show Ended ({0})", [ended])}</button>`
		: "";
	wrapper.html(
		`<table class="table table-bordered" style="margin-bottom: 8px">` +
			`<thead><tr><th>${__("Allowance")}</th><th class="text-right">${__("Amount")}</th>` +
			`<th>${__("From")}</th><th>${__("To")}</th><th></th></tr></thead>` +
			`<tbody>${lines || none}</tbody></table>` +
			`<p>${__("Allowances a month")}: <b>${ha_standing_money(data.running, data.currency)}</b>` +
			` &nbsp; ${__("Monthly gross")}: <b>${ha_standing_money(data.gross, data.currency)}</b></p>` +
			hint +
			`<p>${add}${toggle}</p>`
	);
	wrapper.find("[data-ha-standing]").on("click", function () {
		const what = $(this).attr("data-ha-standing");
		const row = rows.find((one) => one.name === $(this).attr("data-name"));
		if (what === "add") ha_standing_add(frm, data);
		else if (what === "ended") {
			frm.ha_standing_ended = !frm.ha_standing_ended;
			ha_standing_draw(frm, wrapper, data);
		} else if (!row) return;
		else if (what === "change") ha_standing_change(frm, row, data);
		else if (what === "end") ha_standing_end(frm, row);
		else if (what === "remove") ha_standing_remove(frm, row);
	});
}

// sends one change and draws the panel again; an empty value is left out
function ha_standing_send(frm, method, values, done) {
	const args = {};
	Object.keys(values).forEach((key) => {
		if (values[key] !== null && values[key] !== undefined && values[key] !== "") args[key] = values[key];
	});
	frappe.call({ method: HA_STANDING + method, args, freeze: true }).then(() => {
		if (done) done();
		frappe.show_alert({ message: __("Allowances updated"), indicator: "green" });
		ha_standing_allowances(frm);
	});
}

function ha_standing_add(frm, data) {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Allowance"),
		fields: [
			{
				fieldname: "salary_component",
				fieldtype: "Link",
				options: "Salary Component",
				label: __("Allowance"),
				reqd: 1,
				get_query: () => ({ filters: { type: "Earning", disabled: 0 } }),
			},
			{ fieldname: "amount", fieldtype: "Currency", label: __("Amount a Month"), reqd: 1 },
			{
				fieldname: "from_date",
				fieldtype: "Date",
				label: __("From"),
				reqd: 1,
				default: frm.doc.docstatus === 0 && frm.doc.from_date ? frm.doc.from_date : frappe.datetime.get_today(),
			},
			{ fieldname: "to_date", fieldtype: "Date", label: __("To"), description: __("Leave empty until it is ended.") },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			ha_standing_send(frm, "add", Object.assign({ employee: frm.doc.employee }, values), () => dialog.hide());
		},
	});
	dialog.show();
}

function ha_standing_change(frm, row, data) {
	const dialog = new frappe.ui.Dialog({
		title: __("Change Amount: {0}", [row.salary_component]),
		fields: [
			{ fieldname: "amount", fieldtype: "Currency", label: __("New Amount a Month"), reqd: 1 },
			{
				fieldname: "from_date",
				fieldtype: "Date",
				label: __("From"),
				reqd: 1,
				default: frappe.datetime.get_today(),
				description: __("Now {0}.", [ha_standing_money(row.amount, data.currency)]),
			},
		],
		primary_action_label: __("Change"),
		primary_action(values) {
			ha_standing_send(frm, "change", Object.assign({ name: row.name }, values), () => dialog.hide());
		},
	});
	dialog.show();
}

function ha_standing_end(frm, row) {
	const dialog = new frappe.ui.Dialog({
		title: __("Last Day: {0}", [row.salary_component]),
		fields: [
			{
				fieldname: "to_date",
				fieldtype: "Date",
				label: __("Last Day"),
				default: row.to_date || null,
				description: __("Leave empty to let it run."),
			},
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			ha_standing_send(frm, "end", Object.assign({ name: row.name }, values), () => dialog.hide());
		},
	});
	dialog.show();
}

function ha_standing_remove(frm, row) {
	frappe.confirm(__("Remove {0}? Use this for one entered by mistake.", [row.salary_component]), () => {
		ha_standing_send(frm, "remove", { name: row.name });
	});
}
