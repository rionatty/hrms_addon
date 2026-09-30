// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The form's job beyond the fields themselves: say plainly where each
// value is going to land, let someone re-push without saving, and fill the
// Desk Modules table from the desk's current tiles (desk_modules.py).

frappe.ui.form.on("HRMS Addon Branding", {
	refresh(frm) {
		ha_branding_headline(frm);
		ha_desk_modules_help(frm);

		frm.add_custom_button(__("Apply Now"), () => {
			frappe.call({
				method: "hrms_addon.hrms_addon.doctype.hrms_addon_branding.hrms_addon_branding.apply_now",
				freeze: true,
				freeze_message: __("Applying branding…"),
				callback(r) {
					const changed = (r.message && r.message.changed) || [];
					if (!changed.length) {
						frappe.show_alert({
							message: __("Nothing to change."),
							indicator: "blue",
						});
						return;
					}
					frappe.msgprint({
						title: __("Branding Applied"),
						indicator: "green",
						message:
							__("Updated:") +
							"<ul>" +
							changed.map((c) => `<li><code>${frappe.utils.escape_html(c)}</code></li>`).join("") +
							"</ul>" +
							__("Reload the page to see the logo and title change."),
					});
				},
			});
		});

		if (!frm.doc.company_logo) {
			frm.add_custom_button(__("Use Placeholder Logo"), () => {
				frappe.call({
					method: "hrms_addon.hrms_addon.doctype.hrms_addon_branding.hrms_addon_branding.get_placeholder_logo",
					callback(r) {
						if (!r.message) return;
						frm.set_value("company_logo", r.message);
						frappe.show_alert({
							message: __("Placeholder set. Save, then replace it with the real logo."),
							indicator: "blue",
						});
					},
				});
			});
		}

		frm.add_custom_button(__("Open Website Settings"), () =>
			frappe.set_route("Form", "Website Settings")
		);
	},

	enabled(frm) {
		ha_branding_headline(frm);
	},
});

// Frappe's desktop shows the modules of a hidden group (an app or a folder)
// on their own instead of hiding them, which is rarely what unticking the
// group means: offer to take them off the desk too, and to bring them back.
frappe.ui.form.on("HRMS Addon Desk Module", {
	show_on_desk(frm, cdt, cdn) {
		const group = locals[cdt][cdn];
		if (!["App", "Folder"].includes(group.icon_type)) return;
		const members = (frm.doc.desk_modules || []).filter((row) => row.group === group.module);
		const shown = members.filter((row) => row.show_on_desk);
		if (!group.show_on_desk && shown.length) {
			frappe.confirm(
				__("Hide the {0} modules in {1} too? If not, they show on the desk on their own.", [
					shown.length,
					frappe.utils.escape_html(group.module),
				]),
				() => ha_set_shown(frm, shown, 0)
			);
		} else if (group.show_on_desk && members.length && !shown.length) {
			frappe.confirm(
				__("Show the {0} modules in {1} again?", [members.length, frappe.utils.escape_html(group.module)]),
				() => ha_set_shown(frm, members, 1)
			);
		}
	},
});

function ha_set_shown(frm, rows, value) {
	rows.forEach((row) => frappe.model.set_value(row.doctype, row.name, "show_on_desk", value));
	frm.refresh_field("desk_modules");
}

function ha_load_desk_modules(frm) {
	frm.call("refresh_desk_modules").then(() => {
		frm.dirty();
		frm.refresh_field("desk_modules");
		frappe.show_alert({
			message: __("Module list loaded. Untick what should not show, then save."),
			indicator: "blue",
		});
	});
}

function ha_desk_modules_help(frm) {
	const field = frm.get_field("desk_modules_help");
	if (!field) return;
	// the rows are the desk's own tiles, loaded from the server: none typed in or deleted
	frm.set_df_property("desk_modules", "cannot_add_rows", 1);
	frm.set_df_property("desk_modules", "cannot_delete_rows", 1);
	frappe
		.xcall("hrms_addon.hrms_addon.doctype.hrms_addon_branding.hrms_addon_branding.get_desk_modules_status")
		.then((status) => {
			const usable = status && status.available;
			const message = usable
				? __(
						"Untick a module to hide its tile from everyone's desk, then save. Untick an app, such as Frappe HR, to show its modules on the desk directly."
				  )
				: (status && status.message) || "";
			field.$wrapper.html(`
				<div class="text-muted small" style="margin-bottom: 10px">${frappe.utils.escape_html(message)}</div>
				${usable ? `<button type="button" class="btn btn-default btn-sm ha-load-modules">${frappe.utils.escape_html(__("Load Desk Modules"))}</button>` : ""}
			`);
			field.$wrapper.find(".ha-load-modules").on("click", () => ha_load_desk_modules(frm));
			frm.set_df_property("desk_modules", "read_only", usable ? 0 : 1);
		});
}

// Spell out the destinations. These are Frappe's own fields, and knowing
// which one is being written is the difference between "it didn't work"
// and "I was looking at the wrong screen".
function ha_branding_headline(frm) {
	if (!frm.doc.enabled) {
		frm.dashboard.set_headline(
			__("Branding is off. Website Settings and Navbar Settings are unchanged.")
		);
		return;
	}
	frm.dashboard.set_headline(
		__("On save, non-empty values are written to") +
			" <code>Website Settings</code> (app_name, app_logo, favicon, splash_image, footer_powered) " +
			__("and") +
			" <code>Navbar Settings</code> (app_logo). " +
			`<span class="text-muted">${__("Blank fields are skipped, never cleared.")}</span>`
	);
}
