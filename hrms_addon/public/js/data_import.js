// Luuka, 15 Nov 2026: "add a button to delete data impported through data import to allow quick deletion".
// Delete Imported Records, on a finished import that inserted new records, for someone who may delete them. The
// server deletes in the background and says how it went (import_undo.py).
const HA_IMPORT_UNDO = "hrms_addon.hrms_addon.import_undo.";

frappe.ui.form.on("Data Import", {
	refresh(frm) {
		ha_import_undo_button(frm);
	},
});

function ha_import_undo_button(frm) {
	const doc = frm.doc;
	if (doc.__islocal || doc.import_type !== "Insert New Records") return;
	if (!["Success", "Partial Success"].includes(doc.status)) return;
	frappe.xcall(HA_IMPORT_UNDO + "made", { data_import: doc.name }).then((made) => {
		if (!made || !made.count || frm.doc.name !== doc.name) return;
		frm.add_custom_button(__("Delete Imported Records"), () => ha_import_undo_confirm(frm, made));
	});
}

function ha_import_undo_confirm(frm, made) {
	frappe.confirm(
		__(
			"Delete the {0} {1} records this import made? Submitted ones are cancelled first. They can be restored from Deleted Document.",
			[made.count, __(made.doctype)]
		),
		() => {
			frappe.xcall(HA_IMPORT_UNDO + "delete_made", { data_import: frm.doc.name }).then((count) => {
				frappe.show_alert({
					message: __("Deleting {0} records. You will be told when it is done.", [count]),
					indicator: "blue",
				});
			});
		}
	);
}
