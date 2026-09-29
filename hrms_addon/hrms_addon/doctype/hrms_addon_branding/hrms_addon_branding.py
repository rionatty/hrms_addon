# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""HRMS Addon Branding (Single).

Thin shell. All the reasoning about where each value lands lives in
hrms_addon/hrms_addon/branding.py — read that first. The Desk Modules tab
(which tiles show on the desk) is desk_modules.py.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from hrms_addon.hrms_addon import desk_modules, login_rules
from hrms_addon.hrms_addon.branding import PLACEHOLDER_LOGO, apply_branding


class HRMSAddonBranding(Document):
    def validate(self):
        if self.product_name:
            self.product_name = self.product_name.strip()
        if self.footer_powered:
            self.footer_powered = self.footer_powered.strip()

        # A logo taller than the navbar overflows it — frappe's own
        # #brand-logo rule is `width: auto` with no height cap. Our
        # stylesheet caps it, but warn if the source is wildly off so
        # nobody wonders why their banner looks like a stamp.
        if self.company_logo and self.has_value_changed("company_logo"):
            frappe.msgprint(
                _("Logo saved. A square logo works best in the navbar."),
                indicator="blue",
                alert=True,
            )

        # The sign-in page is seen before anyone signs in, so a private file
        # never loads there (login_rules.IMAGE_SOURCES).
        if self.login_image and self.has_value_changed("login_image") \
                and not login_rules.safe_image(self.login_image):
            frappe.msgprint(
                _("The sign-in page cannot show this picture. Attach a public file."),
                indicator="orange",
            )

    def on_update(self):
        changed = apply_branding()
        if desk_modules.apply():
            changed.append("Desktop Icon.hidden")
        if changed:
            frappe.msgprint(
                _("Branding applied to: {0}").format(", ".join(sorted(set(changed)))),
                indicator="green",
                alert=True,
            )

    @frappe.whitelist()
    def refresh_desk_modules(self):
        """Load Desk Modules: the table brought in line with the desk's
        current tiles, keeping the choices already made."""
        frappe.only_for(("System Manager", "Administrator"))
        desk_modules.refresh_rows(self)


@frappe.whitelist()
def apply_now():
    """Push the values again without saving — the form's Apply button.

    Useful after someone has edited Website Settings by hand and wants
    this screen to win again, or after an update brought back a tile
    taken off the desk.
    """
    frappe.only_for(("System Manager", "Administrator"))
    changed = apply_branding(force=True)
    if desk_modules.apply():
        changed.append("Desktop Icon.hidden")
    return {"changed": sorted(set(changed))}


@frappe.whitelist()
def get_desk_modules_status():
    """Whether the Desk Modules tab can be used on this site, and why not."""
    frappe.only_for(("System Manager", "Administrator"))
    return desk_modules.status()


@frappe.whitelist()
def get_placeholder_logo():
    """Path of the shipped placeholder mark, for the 'Use Placeholder'
    button on the form."""
    frappe.only_for(("System Manager", "Administrator"))
    return PLACEHOLDER_LOGO
