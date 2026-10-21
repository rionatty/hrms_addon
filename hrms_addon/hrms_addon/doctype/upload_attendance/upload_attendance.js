// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// Upload Attendance: the register out, the filled file back in. Import
// checks the file's heading at once and marks the days in the background,
// however many there are; the page updates when it is done
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
	const stopped = (frm.doc.__onload || {}).stopped;
	const running = HA_UPLOAD_RUNNING.includes(frm.doc.status) && !stopped;
	if (running) {
		ha_upload_attendance_hint(frm, __("Marking in the background. This page updates when it is done."), "blue");
	} else if (stopped) {
		ha_upload_attendance_hint(
			frm,
			__("The marking stopped before the end. Press Import to go on from where it stopped."),
			"orange"
		);
	} else if (!frm.doc.attendance_file) {
		ha_upload_attendance_hint(
			frm,
			__("Download the template, put the day's letter on each day to mark, then attach it here.")
		);
	} else {
		ha_upload_attendance_hint(frm, "");
	}
	frm.add_custom_button(__("Download Template"), () => ha_attendance_template(frm));
	if (frm.doc.attendance_file && !running) {
		frm.add_custom_button(__("Import"), () => ha_import_attendance(frm)).addClass("btn-primary");
	}
}

// one hint at a time: set_intro forgets a hint the form drew before it was
// last rendered, and two stood on the page (Luuka, 21 Oct 2026)
function ha_upload_attendance_hint(frm, text, colour) {
	frm.layout.message.find(".ha-upload-hint").remove();
	frm.set_intro(text, colour);
	if (text && frm.$intro_message) frm.$intro_message.addClass("ha-upload-hint");
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
			frappe.show_alert({ message: __("{0} people on the register.", [file.people]), indicator: "green" });
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
		.then(() => {
			frappe.show_alert({ message: __("Marking the days in the background."), indicator: "blue" });
			frm.reload_doc();
		});
}
