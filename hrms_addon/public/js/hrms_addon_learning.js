// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// What the learning forms share (learning_sheets.py): how far a submitted
// entry sheet has got, and Run Again for one that stopped or left rows out.
frappe.provide("hrms_addon");

hrms_addon.sheet_progress = function (frm) {
	if (frm.doc.docstatus !== 1) return;
	const colour = { Queued: "blue", Processing: "blue", Done: frm.doc.failed ? "orange" : "green", Failed: "red" };
	frm.dashboard.set_headline(
		__("{0}: {1} rows done, {2} created, {3} updated, {4} failed.", [__(frm.doc.status || ""), frm.doc.rows_done || 0,
			frm.doc.created || 0, frm.doc.updated || 0, frm.doc.failed || 0]),
		colour[frm.doc.status] || "blue"
	);
	if (frm.doc.status === "Failed" || (frm.doc.status === "Done" && frm.doc.failed)) {
		frm.add_custom_button(__("Run Again"), () =>
			frappe
				.xcall("hrms_addon.hrms_addon.learning_sheets.run_again", { doctype: frm.doctype, name: frm.doc.name }, "POST")
				.then(() => frm.reload_doc())
		);
	}
	if (["Queued", "Processing"].includes(frm.doc.status)) {
		setTimeout(() => !frm.is_dirty() && frm.doc.docstatus === 1 && frm.reload_doc(), 5000);
	}
};
