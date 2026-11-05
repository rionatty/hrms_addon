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
// The Period of a monthly payroll: picked from its company's open months, and the
// dates follow it (payroll_months.py). Should the list not come, the dates stay
// open to type and the server still checks them. Frappe HR fills the dates from
// the calendar month whenever the frequency changes; these handlers run after
// its own and put them back.
const HA_PAYROLL_PERIOD_FIELD = "custom_pay_period";
const HA_PAYROLL_PERIOD_METHOD = "hrms_addon.hrms_addon.payroll_months.open_months";
// the list, once it is here; false if it could not be had. And who asked: months close and open, so each document
// asks again
let ha_payroll_periods = null;
let ha_payroll_periods_of = null;

const HA_WEEKLY_METHOD = "hrms_addon.hrms_addon.weekly_pay.dates_for";
const HA_WEEKLY_FILTERS = ["branch", "department", "designation", "grade"];
// where a weekly payroll starts and stops, once it is here; false if it could not be had. And who it was asked for
let ha_weekly_dates = null;
let ha_weekly_for = null;
// whether the answer on its way is written onto the form: a new payroll's, or one changed to Weekly, or to another
// company or filter
let ha_weekly_fill = false;
// what the End says under it, set only when it changes
let ha_weekly_hint = "";

const HA_PAYROLL_REGISTER_TAB = "custom_salary_register_tab";
const HA_PAYROLL_REGISTER_FIELD = "custom_salary_register";
const HA_PAYROLL_REGISTER_METHOD = "hrms_addon.hrms_addon.payroll_register.salary_register";
const HA_PAYROLL_REGISTER_DOWNLOAD = "hrms_addon.hrms_addon.payroll_register.download_salary_register";

frappe.ui.form.on("Payroll Entry", {
	refresh(frm) {
		ha_payroll_recreate_button(frm);
		ha_payroll_register(frm);
		ha_payroll_period(frm);
		ha_weekly(frm);
	},
	on_tab_change(frm) {
		ha_payroll_register(frm);
	},
	company: ha_payroll_dates_changed,
	payroll_frequency: ha_payroll_dates_changed,
	salary_slip_based_on_timesheet: ha_payroll_dates_changed,
	branch: ha_weekly_changed,
	department: ha_weekly_changed,
	designation: ha_weekly_changed,
	grade: ha_weekly_changed,
	// Frappe HR moves the End a week from a Start typed: this runs after its own, its answer in, and puts it back
	set_end_date: ha_weekly_after_frappe_end,
	custom_pay_period: ha_payroll_period_dates,
	start_date: ha_payroll_period_dates,
	end_date: ha_payroll_period_dates,
});

function ha_payroll_dates_changed(frm) {
	ha_payroll_period_changed(frm);
	ha_weekly_changed(frm);
}

function ha_payroll_period_asked(frm) {
	return (frm.doc.company || "") + "|" + frm.doc.name;
}

function ha_payroll_period_on(frm) {
	return (
		Array.isArray(ha_payroll_periods) &&
		frm.doc.payroll_frequency === "Monthly" &&
		!cint(frm.doc.salary_slip_based_on_timesheet)
	);
}

function ha_payroll_period(frm) {
	if (ha_payroll_periods_of !== ha_payroll_period_asked(frm)) {
		ha_payroll_period_load(frm);
		return;
	}
	const on = ha_payroll_period_on(frm);
	frm.toggle_display(HA_PAYROLL_PERIOD_FIELD, on);
	frm.toggle_reqd(HA_PAYROLL_PERIOD_FIELD, on);
	frm.toggle_enable(["start_date", "end_date"], !on);
	ha_weekly_show(frm);
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
	frm.set_df_property(
		HA_PAYROLL_PERIOD_FIELD,
		"description",
		names.length ? "" : __("No open period for this company. Open or add one in Payroll Period.")
	);
	frm.refresh_field(HA_PAYROLL_PERIOD_FIELD);
}

function ha_payroll_period_load(frm) {
	const company = frm.doc.company || "";
	const asked = ha_payroll_period_asked(frm);
	ha_payroll_periods_of = asked;
	ha_payroll_periods = null;
	// fetch, not frappe.call: a list that cannot be loaded leaves the dates to type, with no dialog
	const answer = company
		? fetch("/api/method/" + HA_PAYROLL_PERIOD_METHOD + "?company=" + encodeURIComponent(company), {
				credentials: "same-origin",
				cache: "no-store",
				headers: { Accept: "application/json" },
		  })
				.then((response) => (response.ok ? response.json() : null))
				.catch(() => null)
				.then((body) => (body ? body.message || [] : false))
		: Promise.resolve([]);
	answer.then((periods) => {
		// the company changed while it was on its way: it is the later answer that counts
		if (ha_payroll_periods_of !== asked) return;
		ha_payroll_periods = periods;
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

function ha_weekly_on(frm) {
	return frm.doc.payroll_frequency === "Weekly" && !cint(frm.doc.salary_slip_based_on_timesheet);
}

function ha_weekly_asked(frm) {
	return JSON.stringify(["name", "company", ...HA_WEEKLY_FILTERS].map((field) => frm.doc[field] || ""));
}

function ha_weekly(frm) {
	if (ha_weekly_on(frm) && frm.doc.docstatus === 0 && ha_weekly_for !== ha_weekly_asked(frm)) {
		ha_weekly_load(frm, frm.is_new());
	} else {
		ha_weekly_show(frm);
	}
}

function ha_weekly_changed(frm) {
	if (!ha_weekly_on(frm) || frm.doc.docstatus !== 0) {
		ha_weekly_show(frm);
	} else if (ha_weekly_for !== ha_weekly_asked(frm)) {
		ha_weekly_load(frm, true);
	} else if (ha_weekly_dates === null) {
		// asked already, as the form refreshed: written on when the answer comes
		ha_weekly_fill = true;
	} else {
		ha_weekly_write(frm);
	}
}

function ha_weekly_load(frm, fill) {
	const asked = ha_weekly_asked(frm);
	ha_weekly_for = asked;
	ha_weekly_dates = null;
	ha_weekly_fill = fill;
	const args = new URLSearchParams();
	["company", ...HA_WEEKLY_FILTERS].forEach((field) => {
		if (frm.doc[field]) args.set(field, frm.doc[field]);
	});
	// fetch, not frappe.call: dates that cannot be had leave them to type, with no dialog
	const answer = frm.doc.company
		? fetch("/api/method/" + HA_WEEKLY_METHOD + "?" + args.toString(), {
				credentials: "same-origin",
				cache: "no-store",
				headers: { Accept: "application/json" },
		  })
				.then((response) => (response.ok ? response.json() : null))
				.catch(() => null)
				.then((body) => (body && body.message ? body.message : false))
		: Promise.resolve(false);
	answer.then((dates) => {
		// asked again while it was on its way: it is the later answer that counts
		if (ha_weekly_for !== asked) return;
		ha_weekly_dates = dates;
		if (ha_weekly_fill) ha_weekly_write(frm);
		else ha_weekly_show(frm);
	});
}

function ha_weekly_write(frm) {
	const dates = ha_weekly_dates;
	if (dates && ha_weekly_on(frm) && frm.doc.docstatus === 0) {
		ha_weekly_put(frm, "start_date", dates.start);
		ha_weekly_put(frm, "end_date", dates.end);
	}
	ha_weekly_show(frm);
}

// after Frappe HR's End a week from a Start: the last day marked instead, where there is one or a payroll before
function ha_weekly_after_frappe_end(frm) {
	const dates = ha_weekly_dates;
	if (!dates || !ha_weekly_on(frm) || frm.doc.docstatus !== 0) return;
	if (dates.end || dates.last) ha_weekly_put(frm, "end_date", dates.end);
	ha_weekly_show(frm);
}

function ha_weekly_show(frm) {
	const dates = ha_weekly_on(frm) && frm.doc.docstatus === 0 ? ha_weekly_dates : null;
	// it starts where the last one stopped; the first has nothing to go from
	if (dates && dates.last) frm.toggle_enable("start_date", false);
	const nothing = dates && dates.last && !frm.doc.end_date;
	const hint = nothing ? __("No attendance to pay after {0}.", [frappe.datetime.str_to_user(dates.last)]) : "";
	if (hint === ha_weekly_hint) return;
	ha_weekly_hint = hint;
	frm.set_df_property("end_date", "description", hint);
}

// written straight on, not with set_value: Frappe HR's handlers would work the End out from the Start again
function ha_weekly_put(frm, field, value) {
	if ((frm.doc[field] || "") === (value || "")) return;
	frm.doc[field] = value || "";
	frm.refresh_field(field);
	frm.dirty();
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
