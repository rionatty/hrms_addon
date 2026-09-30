// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// The month's output pay (minutes 4.6): Get Output fills it from the
// submitted daily reports, or an hourly run from attendance; a Per Meter
// run can also take Luuka's own sheet, downloaded for the month and
// uploaded filled in. Submitting it writes each person's pay as an
// Additional Salary on top of their basic.

const HRA_PAY_MONTHS = [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
];

frappe.ui.form.on("Output Pay Run", {
	onload(frm) {
		if (!frm.is_new()) return;
		// the payroll month a day belongs to: from the 26th, the next one
		const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
		let month = today.getMonth();
		let year = today.getFullYear();
		if (today.getDate() >= 26) {
			month += 1;
			if (month > 11) {
				month = 0;
				year += 1;
			}
		}
		if (!frm.doc.year) frm.set_value("year", year);
		if (!frm.doc.month) frm.set_value("month", HRA_PAY_MONTHS[month]);
	},

	setup(frm) {
		const people = () => {
			const filters = { custom_pay_category: frm.doc.section };
			if (frm.doc.branch) filters.branch = frm.doc.branch;
			return { filters: filters };
		};
		frm.set_query("employee", "lines", people);
		frm.set_query("employee", "employees", people);
		frm.set_query("employee", "overtime", people);
		frm.set_query("size", "lines", () => ({ filters: { section: frm.doc.section, enabled: 1 } }));
	},

	refresh(frm) {
		if (frm.doc.docstatus !== 0 || frm.is_new()) return;
		const label = frm.doc.section === "Hourly" ? __("Get Hours") : __("Get Output");
		frm.add_custom_button(label, () =>
			frappe
				.xcall("hrms_addon.hrms_addon.output_pay.get_output", { run: frm.doc.name })
				.then((found) => {
					frappe.show_alert({
						message: __("{0} line(s), {1} people", [found.lines, found.employees]),
						indicator: "green",
					});
					frm.reload_doc();
				})
		);
		if (frm.doc.section !== "Per Meter") return;
		const group = __("Per Meter Sheet");
		frm.add_custom_button(
			__("Download Sheet"),
			() =>
				window.open(
					frappe.urllib.get_full_url(
						"/api/method/hrms_addon.hrms_addon.output_pay.download_sheet?run=" +
							encodeURIComponent(frm.doc.name)
					)
				),
			group
		);
		frm.add_custom_button(__("Upload Sheet"), () => ha_upload_output_sheet(frm), group);
	},
});

function ha_upload_output_sheet(frm) {
	new frappe.ui.FileUploader({
		// kept with the run, among its attachments
		doctype: frm.doctype,
		docname: frm.docname,
		fieldname: "uploaded_sheet",
		restrictions: { allowed_file_types: [".xlsx"] },
		on_success: (file) =>
			frappe
				.xcall(
					"hrms_addon.hrms_addon.output_pay.upload_sheet",
					{ run: frm.doc.name, file_url: file.file_url },
					null,
					{ freeze: true, freeze_message: __("Reading the sheet") }
				)
				.then((found) => {
					ha_output_sheet_summary(found);
					frm.reload_doc();
				}),
	});
}

// What the upload took, and what it left out and why
function ha_output_sheet_summary(found) {
	const esc = frappe.utils.escape_html;
	const money = (value) => format_currency(value || 0);
	const list = (rows) =>
		rows.length ? "<ul>" + rows.map((row) => "<li>" + esc(row) + "</li>").join("") + "</ul>" : "";
	const problems = found.problems || [];
	const notes = found.notes || [];
	let html =
		"<p>" +
		esc(
			__("{0} day(s), {1} people, {2} metres: {3}, and {4} Looms OT.", [
				found.days,
				found.people,
				found.metres,
				money(found.amount),
				money(found.looms_ot),
			])
		) +
		"</p>";
	if (problems.length) html += "<p><b>" + esc(__("Left out")) + "</b></p>" + list(problems);
	if (notes.length) html += "<p><b>" + esc(__("Seen on the sheet")) + "</b></p>" + list(notes);
	frappe.msgprint({
		title: __("Per Meter Sheet"),
		message: html,
		indicator: problems.length ? "orange" : "green",
	});
}
