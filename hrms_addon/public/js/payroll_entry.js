// Recreate Salary Slips on a submitted payroll whose slips are still drafts
// and nothing is posted: the drafts are deleted and made again on the same
// payroll, in the background (payroll_entries.py). Frappe HR's own refresh
// clears the buttons of a submitted payroll first; this one runs after it.
//
// The Salary Register tab: Frappe HR's Salary Register kept to this payroll's
// slips, drafts or submitted (payroll_register.py). It loads when the tab is
// opened, not with the form, and again once the payroll changes or Refresh
// is pressed.
//
// The Period of a monthly payroll: picked from a list, and the dates follow it.
// The list is the server's, where the 26th to the 25th is kept (payslip_rules.py).
// Should it not come, the dates stay open to type and the server still checks
// them. Frappe HR fills the dates from the calendar month whenever the frequency
// changes; these handlers run after its own and put them back.
const HA_PAYROLL_PERIOD_FIELD = "custom_pay_period";
const HA_PAYROLL_PERIOD_METHOD = "hrms_addon.hrms_addon.payslip.pay_periods";
let ha_payroll_periods = null;
let ha_payroll_periods_asked = false;

const HA_PAYROLL_REGISTER_TAB = "custom_salary_register_tab";
const HA_PAYROLL_REGISTER_FIELD = "custom_salary_register";
const HA_PAYROLL_REGISTER_METHOD = "hrms_addon.hrms_addon.payroll_register.salary_register";
const HA_PAYROLL_REGISTER_DOWNLOAD = "hrms_addon.hrms_addon.payroll_register.download_salary_register";

frappe.ui.form.on("Payroll Entry", {
	refresh(frm) {
		ha_payroll_recreate_button(frm);
		ha_payroll_register(frm);
		ha_payroll_period(frm);
	},
	on_tab_change(frm) {
		ha_payroll_register(frm);
	},
	payroll_frequency: ha_payroll_period_changed,
	salary_slip_based_on_timesheet: ha_payroll_period_changed,
	custom_pay_period: ha_payroll_period_dates,
	start_date: ha_payroll_period_dates,
	end_date: ha_payroll_period_dates,
});

function ha_payroll_period_on(frm) {
	return (
		ha_payroll_periods &&
		ha_payroll_periods.length > 0 &&
		frm.doc.payroll_frequency === "Monthly" &&
		!cint(frm.doc.salary_slip_based_on_timesheet)
	);
}

function ha_payroll_period(frm) {
	if (!ha_payroll_periods) {
		ha_payroll_period_load(frm);
		return;
	}
	const on = ha_payroll_period_on(frm);
	frm.toggle_display(HA_PAYROLL_PERIOD_FIELD, on);
	frm.toggle_reqd(HA_PAYROLL_PERIOD_FIELD, on);
	frm.toggle_enable(["start_date", "end_date"], !on);
	if (!on) return;
	// a payroll saved before there was a list shows the period its dates make, and is not changed by it
	const its_own = ha_payroll_periods.find(
		(period) => period.start === frm.doc.start_date && period.end === frm.doc.end_date
	);
	if (!frm.doc[HA_PAYROLL_PERIOD_FIELD] && its_own) frm.doc[HA_PAYROLL_PERIOD_FIELD] = its_own.name;
	const names = ha_payroll_periods.map((period) => period.name);
	const kept = frm.doc[HA_PAYROLL_PERIOD_FIELD];
	// one older than the list stays as it is
	if (kept && !names.includes(kept)) names.push(kept);
	frm.set_df_property(HA_PAYROLL_PERIOD_FIELD, "options", ["", ...names].join("\n"));
	frm.refresh_field(HA_PAYROLL_PERIOD_FIELD);
}

function ha_payroll_period_load(frm) {
	if (ha_payroll_periods_asked) return;
	ha_payroll_periods_asked = true;
	// fetch, not frappe.call: a list that cannot be loaded leaves the dates to type, with no dialog
	fetch("/api/method/" + HA_PAYROLL_PERIOD_METHOD, {
		credentials: "same-origin",
		cache: "no-store",
		headers: { Accept: "application/json" },
	})
		.then((response) => (response.ok ? response.json() : null))
		.catch(() => null)
		.then((body) => {
			ha_payroll_periods = (body && body.message) || [];
			// an unsaved payroll may have had the calendar month filled in by now; a saved one keeps what it has
			if (frm.is_new()) ha_payroll_period_changed(frm);
			else ha_payroll_period(frm);
		});
}

function ha_payroll_period_changed(frm) {
	ha_payroll_period(frm);
	if (ha_payroll_period_on(frm)) {
		ha_payroll_period_dates(frm);
	} else if (frm.doc[HA_PAYROLL_PERIOD_FIELD]) {
		frm.set_value(HA_PAYROLL_PERIOD_FIELD, "");
	}
}

function ha_payroll_period_dates(frm) {
	if (frm.doc.docstatus !== 0 || !ha_payroll_period_on(frm)) return;
	const name = frm.doc[HA_PAYROLL_PERIOD_FIELD];
	const period = ha_payroll_periods.find((row) => row.name === name);
	// one older than the list keeps its dates
	if (name && !period) return;
	const wanted = { start_date: period ? period.start : "", end_date: period ? period.end : "" };
	Object.keys(wanted).forEach((field) => {
		if ((frm.doc[field] || "") !== wanted[field]) frm.set_value(field, wanted[field]);
	});
}

function ha_payroll_recreate_button(frm) {
	const doc = frm.doc;
	const may_write = frm.perm && frm.perm[0] && frm.perm[0].write;
	if (doc.docstatus !== 1 || !may_write || cint(doc.salary_slips_submitted)) return;
	if (["Queued", "Cancelled"].includes(doc.status)) return;
	if (!cint(doc.salary_slips_created) && doc.status !== "Failed") return;
	frm.add_custom_button(__("Recreate Salary Slips"), () => {
		frappe.confirm(__("Delete the draft salary slips and make them again?"), () => {
			frappe
				.call({
					method: "hrms_addon.hrms_addon.payroll_entries.recreate_salary_slips",
					args: { payroll_entry: doc.name },
					freeze: true,
				})
				.then(() => {
					frappe.show_alert({ message: __("Making the salary slips again"), indicator: "blue" });
					frm.reload_doc();
				});
		});
	});
}

function ha_payroll_register(frm, again) {
	const field = frm.get_field(HA_PAYROLL_REGISTER_FIELD);
	if (!field || !field.$wrapper) return;
	const $wrapper = field.$wrapper;
	const key = frm.doc.name + "|" + frm.doc.modified;
	if ($wrapper.data("ha-register") !== key) {
		// another payroll, or this one since changed: what is drawn is not its register
		$wrapper.data("ha-register", null).empty();
	}
	const tab = frm.get_active_tab && frm.get_active_tab();
	if (!tab || !tab.df || tab.df.fieldname !== HA_PAYROLL_REGISTER_TAB) return;
	if (frm.is_new()) {
		$wrapper.html(ha_payroll_register_note(__("No salary slips yet.")));
		return;
	}
	if ($wrapper.data("ha-register") === key && !again) return;
	$wrapper.data("ha-register", key).html(ha_payroll_register_note(__("Loading...")));
	// fetch, not frappe.call: a register that cannot be loaded says so in the tab, not in a dialog
	fetch("/api/method/" + HA_PAYROLL_REGISTER_METHOD + "?payroll_entry=" + encodeURIComponent(frm.doc.name), {
		credentials: "same-origin",
		cache: "no-store",
		headers: { Accept: "application/json" },
	})
		.then((response) =>
			response
				.json()
				.catch(() => null)
				.then((body) => {
					if (!response.ok) throw { ha_message: ha_payroll_register_error(body) };
					return (body && body.message) || {};
				})
		)
		.then((register) => {
			if ($wrapper.data("ha-register") !== key) return;
			ha_payroll_register_draw(frm, $wrapper, register);
		})
		.catch((error) => {
			if ($wrapper.data("ha-register") !== key) return;
			// asked again the next time the tab is opened
			const message = (error && error.ha_message) || __("The Salary Register could not be loaded.");
			$wrapper.data("ha-register", null).html(ha_payroll_register_note(message));
		});
}

function ha_payroll_register_draw(frm, $wrapper, register) {
	const rows = register.rows || [];
	if (!rows.length) {
		$wrapper.html(ha_payroll_register_note(__("No salary slips yet.")));
		return;
	}
	// the table's height is read as it is drawn, so its rule is in place before; fewer rows than fit take less
	$wrapper.html(`
		<div class="ha-payroll-register">
			<style>.ha-payroll-register .datatable .dt-scrollable { height: 60vh; }</style>
			<div class="flex align-center justify-between" style="gap: 8px; margin-bottom: 10px;">
				<span class="text-muted">${__("{0} salary slips", [format_number(rows.length, null, 0)])}</span>
				<span>
					<button class="btn btn-default btn-sm" data-action="refresh">${__("Refresh")}</button>
					<button class="btn btn-default btn-sm" data-action="download">${__("Download Excel")}</button>
				</span>
			</div>
			<div class="ha-payroll-register-table"></div>
		</div>`);
	$wrapper.find('[data-action="refresh"]').on("click", () => ha_payroll_register(frm, true));
	$wrapper.find('[data-action="download"]').on("click", () => {
		window.open(
			"/api/method/" + HA_PAYROLL_REGISTER_DOWNLOAD + "?payroll_entry=" + encodeURIComponent(frm.doc.name)
		);
	});
	const columns = (register.columns || [])
		.filter((column) => !column.hidden)
		.map((column) => ha_payroll_register_column(column, rows));
	// as Frappe's own reports draw it: a filter row, and a total row that follows the filters
	new frappe.DataTable($wrapper.find(".ha-payroll-register-table")[0], {
		columns: columns,
		data: rows,
		inlineFilters: true,
		layout: "fixed",
		cellHeight: 33,
		showTotalRow: true,
		language: frappe.boot.lang,
		translations: frappe.utils.datatable.get_translations(),
		direction: frappe.utils.is_rtl() ? "rtl" : "ltr",
		hooks: { columnTotal: frappe.utils.report_column_total },
	});
}

function ha_payroll_register_column(column, rows) {
	const width = parseInt(column.width);
	return Object.assign({}, column, {
		id: column.fieldname,
		name: column.label,
		width: width > 0 ? width : 120,
		editable: false,
		format: (value, row, df, data) => {
			if (!data) {
				// the total row: its first column says so, and its amounts are in the slips' currency
				if (df.id === "salary_slip_id") return `<b>${__("Total")}</b>`;
				if (!frappe.model.is_numeric_field(df.fieldtype)) return "";
				data = rows[0];
			}
			return frappe.format(value, df, { always_show_decimals: true }, data);
		},
	});
}

function ha_payroll_register_note(text) {
	return `<div class="text-muted" style="padding: 12px 0;">${frappe.utils.escape_html(text)}</div>`;
}

function ha_payroll_register_error(body) {
	// the message a refused or failed call came back with, as Frappe sends it
	try {
		const messages = JSON.parse((body && body._server_messages) || "[]");
		const first = messages.length ? JSON.parse(messages[0]) : null;
		if (first && first.message) return $("<div>").html(first.message).text();
	} catch (e) {
		// the plain message instead
	}
	return __("The Salary Register could not be loaded.");
}
