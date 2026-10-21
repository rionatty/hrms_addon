// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// Upload Attendance: the template out, the filled file back in. Import
// reads the file at once, so a wrong one is said while you wait, and marks
// the days in the background; the page updates when it is done
// (attendance_upload.py).
const HA_UPLOAD_ATTENDANCE = "hrms_addon.hrms_addon.attendance_upload.";
const HA_UPLOAD_RUNNING = ["Queued", "Importing"];

frappe.ui.form.on("Upload Attendance", {
	setup(frm) {
		frm.set_query("department", () => ({ filters: { company: frm.doc.company } }));
	},

	onload(frm) {
		// a new upload starts on the cycle today is in, 26th to 25th
		if (!frm.is_new() || (frm.doc.from_date && frm.doc.to_date)) return;
		frappe.xcall(HA_UPLOAD_ATTENDANCE + "this_cycle").then((cycle) => {
			if (!frm.doc.from_date) frm.set_value("from_date", cycle.from_date);
			if (!frm.doc.to_date) frm.set_value("to_date", cycle.to_date);
		});
	},

	refresh(frm) {
		ha_upload_attendance_buttons(frm);
	},

	attendance_file(frm) {
		ha_upload_attendance_buttons(frm);
	},
});

function ha_upload_attendance_buttons(frm) {
	frm.clear_custom_buttons();
	const running = HA_UPLOAD_RUNNING.includes(frm.doc.status);
	if (running) {
		frm.set_intro(__("Marking in the background. This page updates when it is done."), "blue");
	} else if (!frm.doc.attendance_file) {
		frm.set_intro(__("Download the template, put a Status on each day to mark, then attach it here."));
	} else {
		frm.set_intro("");
	}
	frm.add_custom_button(__("Download Template"), () => ha_attendance_template(frm));
	if (frm.doc.attendance_file && !running) {
		frm.add_custom_button(__("Import"), () => ha_import_attendance(frm)).addClass("btn-primary");
	}
}

function ha_attendance_template(frm) {
	const { company, branch, department, from_date, to_date } = frm.doc;
	if (!company || !from_date || !to_date) {
		frappe.msgprint(__("Pick the company and the period first."));
		return;
	}
	frappe
		.xcall(
			HA_UPLOAD_ATTENDANCE + "download_template",
			{ company, branch, department, from_date, to_date },
			null,
			{ freeze: true, freeze_message: __("Building the template") }
		)
		.then((file) => {
			ha_save_download(file.filename, file.content);
			frappe.show_alert({ message: __("{0} row(s) to fill.", [file.rows]), indicator: "green" });
		});
}

// the file comes back in the answer, so a problem is a message on this page
function ha_save_download(name, content) {
	const bytes = Uint8Array.from(atob(content), (char) => char.charCodeAt(0));
	const url = URL.createObjectURL(
		new Blob([bytes], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" })
	);
	const link = Object.assign(document.createElement("a"), { href: url, download: name });
	document.body.appendChild(link);
	link.click();
	link.remove();
	setTimeout(() => URL.revokeObjectURL(url), 10000);
}

function ha_import_attendance(frm) {
	const saved = frm.is_new() || frm.is_dirty() ? frm.save() : Promise.resolve();
	saved
		.then(() =>
			frm.call({
				method: "start_import",
				doc: frm.doc,
				freeze: true,
				freeze_message: __("Reading the file"),
			})
		)
		.then((r) => {
			frappe.show_alert({
				message: __("Marking {0} day(s) in the background.", [(r.message || {}).days]),
				indicator: "blue",
			});
			frm.reload_doc();
		});
}
