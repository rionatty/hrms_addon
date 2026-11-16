// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
	"October", "November", "December"];

frappe.ui.form.on("Salary Advance Processing", {
	setup(frm) {
		frm.set_query("bank_account", () => ({
			filters: { company: frm.doc.company, account_type: ["in", ["Bank", "Cash"]], is_group: 0 },
		}));
		// the run's own cancel takes these back (salary_advances.run_on_cancel)
		frm.ignore_doctypes_on_cancel_all = [
			...new Set([
				...(frm.ignore_doctypes_on_cancel_all || []),
				"Employee Advance",
				"Journal Entry",
				"Additional Salary",
			]),
		];
	},
	onload(frm) {
		if (!frm.is_new()) return;
		const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
		if (!frm.doc.company) frm.set_value("company", frappe.defaults.get_user_default("Company"));
		if (!frm.doc.year) frm.set_value("year", today.getFullYear());
		if (!frm.doc.month) frm.set_value("month", MONTHS[today.getMonth()]);
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.processing_date) {
			frm.dashboard.set_headline(
				__("Processed on {0}. Payroll period {1} to {2}.", [
					frappe.datetime.str_to_user(frm.doc.processing_date),
					frappe.datetime.str_to_user(frm.doc.period_start),
					frappe.datetime.str_to_user(frm.doc.period_end),
				])
			);
		}
		// Luuka, 16 Nov 2026: "add download functionality". The run's lines as Excel, as saved (salary_advances.download)
		if (!frm.is_new() && (frm.doc.employees || []).length) {
			frm.add_custom_button(__("Download"), () => {
				if (frm.is_dirty()) {
					frappe.show_alert({
						message: __("Save the run first. The file holds what is saved."),
						indicator: "orange",
					});
					return;
				}
				window.open(
					"/api/method/hrms_addon.hrms_addon.salary_advances.download?name=" + encodeURIComponent(frm.doc.name)
				);
			});
		}
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Advance Payment Report"), () =>
				frappe.set_route("query-report", "Advance Payment Report", {
					salary_advance_processing: frm.doc.name,
				})
			);
			if (frm.doc.journal_entry) {
				frm.add_custom_button(__("Bank Entry"), () =>
					frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry)
				);
			}
			// Luuka's own ADVANCE_PAYMENT workbook, those paid by bank and a cash report (salary_advances.bank_file):
			// asked first, so a refusal is a message; who has a bank detail left blank is said
			frm.add_custom_button(__("Bank File"), () => {
				const method = "hrms_addon.hrms_addon.salary_advances.bank_file";
				frappe
					.call({ method: method + "_check", args: { name: frm.doc.name }, freeze: true })
					.then((r) => {
						const found = r && r.message;
						if (!found || !(found.rows || found.cash)) return;
						window.open("/api/method/" + method + "?name=" + encodeURIComponent(frm.doc.name));
						if ((found.blank || []).length) {
							frappe.msgprint({
								title: __("Bank File"),
								message: found.blank.map((line) => frappe.utils.escape_html(line)).join("<br>"),
								indicator: "orange",
							});
						}
					});
			});
		}
	},
	get_requests(frm) {
		const fetch = () =>
			frappe
				.xcall("hrms_addon.hrms_addon.salary_advances.get_requests", { name: frm.doc.name })
				.then((result) => {
					frm.reload_doc();
					const left_out = (result.not_added || []).map(
						([reason, count]) => `${frappe.utils.escape_html(reason)} (${count})`
					);
					const added = result.added
						? __("{0} request(s) added.", [result.added])
						: __("No request was added.");
					if (left_out.length) {
						frappe.msgprint({
							title: __("Get Requests"),
							indicator: "orange",
							message: `<p>${added}</p><p>${__("Not added:")}<br>${left_out.join("<br>")}</p>`,
						});
					} else {
						frappe.show_alert({
							message: result.added ? added : __("No approved Salary Advance Requests."),
							indicator: result.added ? "green" : "orange",
						});
					}
				});
		if (frm.is_dirty() || frm.is_new()) {
			frm.save().then(fetch);
		} else {
			fetch();
		}
	},
});
