// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// One employee's learning content: open it, acknowledge it or take its quiz.
frappe.ui.form.on("Learning Content Assignment", {
	refresh(frm) {
		if (frm.is_new() || ["Completed", "Passed", "Withdrawn"].includes(frm.doc.status)) return;
		frm.add_custom_button(frm.doc.content_type === "Quiz" ? __("Take the Quiz") : __("Open"), () =>
			hrms_addon.open_content(frm.doc.name, () => frm.reload_doc())
		).addClass("btn-primary");
	},
});
