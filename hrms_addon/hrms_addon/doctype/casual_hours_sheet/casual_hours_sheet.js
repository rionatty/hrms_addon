// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

const HA_HOURS = "hrms_addon.hrms_addon.casual_hours.";

frappe.ui.form.on("Casual Hours Sheet", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.from_date) ha_hours_week(frm);
	},
	company: ha_hours_week_if_new,
	branch: ha_hours_week_if_new,
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Download Template"), () =>
			window.open(
				frappe.urllib.get_full_url(
					"/api/method/" + HA_HOURS + "download_template?sheet=" + encodeURIComponent(frm.doc.name)
				)
			)
		);
		if (frm.doc.docstatus === 0 && (frm.doc.workflow_state || "Draft") === "Draft") {
			frm.add_custom_button(__("Upload Sheet"), () => ha_hours_upload(frm)).addClass("btn-primary");
		}
	},
});

function ha_hours_week_if_new(frm) {
	if (frm.is_new()) ha_hours_week(frm);
}

// a new sheet is for the week after the plant's last one
function ha_hours_week(frm) {
	frappe
		.xcall(HA_HOURS + "new_sheet_week", { company: frm.doc.company, branch: frm.doc.branch })
		.then((week) => {
			if (week && week.from_date) frm.set_value({ from_date: week.from_date, to_date: week.to_date });
		});
}

function ha_hours_upload(frm) {
	new frappe.ui.FileUploader({
		doctype: frm.doctype,
		docname: frm.docname,
		restrictions: { allowed_file_types: [".xlsx"] },
		on_success: (file) =>
			frappe
				.xcall(
					HA_HOURS + "upload_sheet",
					{ sheet: frm.doc.name, file_url: file.file_url },
					null,
					{ freeze: true, freeze_message: __("Reading the sheet") }
				)
				.then((found) => {
					frm.reload_doc();
					ha_hours_said(found);
				}),
	});
}

function ha_hours_said(found) {
	if (!found) return;
	const esc = frappe.utils.escape_html;
	let html = `<p>${__("{0} people taken: {1} hours and {2} overtime hours.", [
		found.people,
		found.hours,
		found.overtime,
	])}</p>`;
	if (found.missing) {
		html += `<p>${__("{0} of the plant's casuals are not on it.", [found.missing])}</p>`;
	}
	if ((found.problems || []).length) {
		html += `<p><b>${__("Left out")}</b></p><ul>${found.problems
			.map((problem) => `<li>${esc(problem)}</li>`)
			.join("")}</ul>`;
	}
	frappe.msgprint({ title: __("Sheet uploaded"), message: html, indicator: found.problems.length ? "orange" : "green" });
}
