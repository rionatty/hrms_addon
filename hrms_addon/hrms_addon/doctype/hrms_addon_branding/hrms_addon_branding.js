// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The form's job beyond the fields themselves: say plainly where each
// value is going to land, and let someone re-push without saving.

frappe.ui.form.on("HRMS Addon Branding", {
	refresh(frm) {
		ha_branding_headline(frm);

		frm.add_custom_button(__("Apply Now"), () => {
			frappe.call({
				method: "hrms_addon.hrms_addon.doctype.hrms_addon_branding.hrms_addon_branding.apply_now",
				freeze: true,
				freeze_message: __("Applying branding…"),
				callback(r) {
					const changed = (r.message && r.message.changed) || [];
					if (!changed.length) {
						frappe.show_alert({
							message: __("Nothing to change — everything already matches."),
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
							message: __("Placeholder set — save, then replace it with the real logo."),
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

// Spell out the destinations. These are Frappe's own fields, and knowing
// which one is being written is the difference between "it didn't work"
// and "I was looking at the wrong screen".
function ha_branding_headline(frm) {
	if (!frm.doc.enabled) {
		frm.dashboard.set_headline(
			__("Branding is off — Website Settings and Navbar Settings are left exactly as they are.")
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
