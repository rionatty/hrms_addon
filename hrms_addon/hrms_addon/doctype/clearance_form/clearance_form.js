// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The Clearance Form (LPL/HR/22): where its boxes stand, and the buttons a
// box is signed with. A box is signed by its own department, or by HR on
// the department's behalf (exits.sign_boxes); HR approve the form once
// every box is signed (clearance_approval.py).

frappe.ui.form.on("Clearance Form", {
	refresh(frm) {
		// one line for each box in use, kept by the form itself
		frm.set_df_property("sections", "cannot_add_rows", 1);
		frm.set_df_property("sections", "cannot_delete_rows", 1);
		frm.trigger("show_boxes");
	},
	show_boxes(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new()) return;
		const name = frm.doc.name;
		frappe
			.xcall("hrms_addon.hrms_addon.exits.clearance_boxes", { name: frm.doc.name })
			.then((boxes) => {
				// the answer is for the form that asked, not one opened since
				if (!boxes || !boxes.length || frm.doc.name !== name) return;
				ha_clearance_headline(frm, boxes);
				if (frm.doc.docstatus !== 0) return;
				if (boxes.some((box) => box.can_sign)) {
					frm.add_custom_button(__("Sign Boxes"), () => ha_clearance_sign(frm));
				}
				if (boxes.some((box) => box.can_unsign)) {
					frm.add_custom_button(__("Remove Signature"), () => ha_clearance_unsign(frm));
				}
			});
	},
});

function ha_clearance_headline(frm, boxes) {
	const unsigned = boxes.filter((box) => !box.signed_by).map((box) => box.section);
	const waiting = boxes.reduce((count, box) => count + (box.waiting || []).length, 0);
	let html =
		`<span>${__("Boxes signed")} <b>${boxes.length - unsigned.length}</b> ${__("of")} ${
			boxes.length
		}</span>` +
		` <span class="indicator-pill ${unsigned.length ? "orange" : "green"}">${
			unsigned.length
				? __("Not signed: {0}", [frappe.utils.escape_html(unsigned.join(", "))])
				: __("All boxes signed")
		}</span>`;
	if (waiting) {
		html += ` <span class="indicator-pill orange">${__("Items to account for: {0}", [waiting])}</span>`;
	}
	frm.dashboard.set_headline(html);
}

// what is on the screen is saved first: a box is signed for the items as stored
function ha_clearance_saved(frm, then) {
	if (frm.doc.docstatus === 0 && frm.is_dirty()) {
		frm.save().then(then);
	} else {
		then();
	}
}

function ha_clearance_sign(frm) {
	ha_clearance_saved(frm, () =>
		frappe
			.xcall("hrms_addon.hrms_addon.exits.clearance_boxes", { name: frm.doc.name })
			.then((boxes) => {
				const mine = (boxes || []).filter((box) => box.can_sign);
				if (!mine.length) {
					frappe.show_alert({ message: __("No box is ready for you to sign."), indicator: "orange" });
					return;
				}
				const dialog = new frappe.ui.Dialog({
					title: __("Sign Boxes"),
					fields: [
						{
							fieldname: "sections",
							fieldtype: "MultiCheck",
							label: __("Boxes"),
							columns: 2,
							options: mine.map((box) => ({ label: box.label, value: box.section, checked: 1 })),
						},
						{ fieldname: "remarks", fieldtype: "Data", label: __("Remarks") },
					],
					primary_action_label: __("Sign"),
					primary_action(values) {
						const args = { name: frm.doc.name, sections: values.sections || [] };
						if (values.remarks) args.remarks = values.remarks;
						frappe.xcall("hrms_addon.hrms_addon.exits.sign_boxes", args).then(() => {
							dialog.hide();
							frm.reload_doc();
						});
					},
				});
				dialog.show();
			})
	);
}

function ha_clearance_unsign(frm) {
	ha_clearance_saved(frm, () =>
		frappe
			.xcall("hrms_addon.hrms_addon.exits.clearance_boxes", { name: frm.doc.name })
			.then((boxes) => {
				const signed = (boxes || []).filter((box) => box.can_unsign);
				if (!signed.length) return;
				frappe.prompt(
					[
						{
							fieldname: "section",
							fieldtype: "Select",
							label: __("Box"),
							reqd: 1,
							options: signed.map((box) => ({ label: box.label, value: box.section })),
						},
					],
					(values) =>
						frappe
							.xcall("hrms_addon.hrms_addon.exits.unsign_box", {
								name: frm.doc.name,
								section: values.section,
							})
							.then(() => frm.reload_doc()),
					__("Remove Signature"),
					__("Remove")
				);
			})
	);
}
