// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// A month's build for the HR board pack (board_facts.py): built again on the long queue, its progress shown as it
// runs, and the rows it is made of one click away.
frappe.ui.form.on("HR Monthly Snapshot", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.source === "Imported") {
			frm.set_intro(__("Import the month's rows in HR Employee Month, HR Pay Fact and HR Safety Fact."), "blue");
		} else if (frm.doc.status === "Failed") {
			frm.set_intro(__("The last build failed. Build it again once the cause is put right."), "red");
		} else if (frm.doc.locked) {
			frm.set_intro(__("Locked by an approved board report: its figures stand."), "green");
		}
		const month = frm.doc.month_start;
		const open = (doctype) => frappe.set_route("List", doctype, { company: frm.doc.company, month: month });
		frm.add_custom_button(__("Employee Months"), () => open("HR Employee Month"), __("Rows"));
		frm.add_custom_button(__("Movements"), () => open("HR Movement"), __("Rows"));
		frm.add_custom_button(__("Pay Lines"), () => open("HR Pay Fact"), __("Rows"));
		frm.add_custom_button(__("Safety Lines"), () => open("HR Safety Fact"), __("Rows"));
		if (frm.doc.source === "Imported") {
			frm.add_custom_button(__("Refresh Totals"), () =>
				frappe
					.xcall("hrms_addon.hrms_addon.board_facts.refresh_totals", { name: frm.doc.name })
					.then(() => frm.reload_doc())
			);
		}
		if (!frm.hra_listening) {
			frm.hra_listening = true;
			frappe.realtime.on("progress", (data) => {
				if (data && data.doctype === "HR Monthly Snapshot" && data.docname === frm.doc.name && data.percent >= 100) {
					frm.reload_doc();
				}
			});
		}
	},
	build(frm) {
		frappe.xcall("hrms_addon.hrms_addon.board_facts.build", { name: frm.doc.name }).then(() => {
			frappe.show_alert({ message: __("Building {0} in the background", [frm.doc.name]), indicator: "blue" });
			frm.reload_doc();
		});
	},
});
