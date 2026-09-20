// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// The same signpost on the list, which is where Frappe HR's own sidebar
// entry lands. doctype_list_js, read from disk when the list loads.

frappe.listview_settings["Appraisal Template"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Open the LPL PMS Template"), () =>
			frappe.set_route("List", "BSC Appraisal Template")
		);
		if (listview.page.main.find(".ha-stock-template-note").length) return;
		listview.page.main.prepend(
			$("<div class='ha-stock-template-note'></div>")
				.addClass("alert alert-warning")
				.css({ margin: "10px 0" })
				.text(
					__(
						"This is Frappe HR's own template. Luuka's are one per role, under Appraisal Template (LPL PMS)."
					)
				)
		);
	},
};
