# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""HRMS Addon Branding (Single).

Thin shell. All the reasoning about where each value lands lives in
hrms_addon/hrms_addon/branding.py — read that first.
"""

import frappe
from frappe import _
from frappe.model.document import Document

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
                _("Logo saved. It is scaled to fit the 52px navbar — a square or near-square mark reads best there."),
                indicator="blue",
                alert=True,
            )

    def on_update(self):
        changed = apply_branding()
        if changed:
            frappe.msgprint(
                _("Branding applied to: {0}").format(", ".join(sorted(set(changed)))),
                indicator="green",
                alert=True,
            )


@frappe.whitelist()
def apply_now():
    """Push the values again without saving — the form's Apply button.

    Useful after someone has edited Website Settings by hand and wants
    this screen to win again.
    """
    frappe.only_for(("System Manager", "Administrator"))
    changed = apply_branding(force=True)
    return {"changed": sorted(set(changed))}


@frappe.whitelist()
def get_placeholder_logo():
    """Path of the shipped placeholder mark, for the 'Use Placeholder'
    button on the form."""
    frappe.only_for(("System Manager", "Administrator"))
    return PLACEHOLDER_LOGO
