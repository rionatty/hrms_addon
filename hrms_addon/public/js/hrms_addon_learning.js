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

// The learning library (learning_library.py): open a piece of content,
// acknowledge it, or take its quiz; then call back.
hrms_addon.open_content = function (assignment, done) {
	const call = (method, args) =>
		frappe.xcall("hrms_addon.hrms_addon.learning_library." + method, Object.assign({ assignment: assignment }, args || {}), "POST");
	call("start").then((content) => {
		if (content.content_type === "Quiz") {
			hrms_addon.take_quiz(assignment, done);
			return;
		}
		const where = content.file || content.url;
		if (where) window.open(where, "_blank");
		const dialog = new frappe.ui.Dialog({
			title: content.title,
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
			primary_action_label: __("I Have Read It"),
			primary_action() {
				call("acknowledge").then((found) => {
					dialog.hide();
					frappe.show_alert({ message: __(found.status), indicator: "green" });
					done && done();
				});
			},
		});
		dialog.fields_dict.body.$wrapper.html(content.body || (where ? `<p>${__("It opened in a new tab.")}</p>` : ""));
		dialog.show();
	});
};

hrms_addon.take_quiz = function (assignment, done) {
	frappe.xcall("hrms_addon.hrms_addon.learning_library.quiz", { assignment: assignment }).then((quiz) => {
		const fields = (quiz.questions || []).map((question, index) => ({
			fieldname: question.name,
			fieldtype: question.options.length ? "Select" : "Data",
			label: `${index + 1}. ${question.question}`,
			options: question.options.length ? [""].concat(question.options).join("\n") : undefined,
		}));
		const dialog = new frappe.ui.Dialog({
			title: quiz.title,
			fields: fields,
			primary_action_label: __("Submit"),
			primary_action(values) {
				frappe
					.xcall("hrms_addon.hrms_addon.learning_library.submit_quiz", { assignment: assignment, answers: JSON.stringify(values) }, "POST")
					.then((found) => {
						dialog.hide();
						frappe.msgprint(__("{0}%: {1} (pass mark {2}%).", [found.score, __(found.status), found.pass_mark]));
						done && done();
					});
			},
		});
		dialog.show();
	});
};
