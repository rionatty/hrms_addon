// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Disciplinary Case", {
	refresh(frm) {
		frm.trigger("show_ladder");
		// the panel is who decides, so the officer who gathered the
		// evidence must not be selectable onto it
		frm.fields_dict.panel.grid.get_field("member").get_query = () => ({
			filters: { name: ["!=", frm.doc.investigating_officer || ""] },
		});
		if (frm.doc.docstatus === 1 && !frm.doc.appeal_filed) {
			frm.add_custom_button(__("File Appeal"), () =>
				frappe.prompt(
					[
						{
							fieldname: "authority",
							fieldtype: "Link",
							options: "User",
							label: __("Heard By"),
							reqd: 1,
							description: __("Someone who has not already acted in this case."),
						},
						{ fieldname: "grounds", fieldtype: "Small Text", label: __("Grounds"), reqd: 1 },
					],
					(values) =>
						frappe
							.xcall("hrms_addon.hrms_addon.discipline.file_appeal", {
								case: frm.doc.name,
								grounds: values.grounds,
								authority: values.authority,
							})
							.then(() => frm.reload_doc()),
					__("Appeal this decision"),
					__("File")
				)
			);
		}
	},
	// The ladder is the whole chart, so say where this case sits on it.
	show_ladder(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new() || !frm.doc.employee) return;
		const parts = [];
		if (frm.doc.starts_at) {
			parts.push(`${__("Starts at")} <b>${frm.doc.starts_at}</b>`);
		}
		if (frm.doc.severity) {
			parts.push(`${__("Severity")} <b>${frm.doc.severity}</b>`);
		}
		if (frm.doc.hearing_notice_hours) {
			const enough = frm.doc.hearing_notice_hours >= 48;
			parts.push(
				`<span class="indicator-pill ${enough ? "green" : "red"}">${__(
					"{0} hours' notice",
					[frm.doc.hearing_notice_hours]
				)}</span>`
			);
		}
		if (!parts.length) return;
		frm.dashboard.set_headline(
			parts.join(" &nbsp;|&nbsp; ") +
				(frm.doc.live_sanctions
					? ` <span class="text-muted">${frappe.utils.escape_html(frm.doc.live_sanctions)}</span>`
					: "")
		);
	},
	investigating_officer(frm) {
		const on_panel = (frm.doc.panel || []).filter(
			(row) => row.member === frm.doc.investigating_officer
		);
		if (on_panel.length) {
			frappe.show_alert({
				message: __("The investigating officer is on the panel. They cannot decide the case they investigated."),
				indicator: "red",
			});
		}
	},
	action_type(frm) {
		if (!frm.doc.letter_issued_on) {
			frm.set_value("letter_issued_on", frappe.datetime.get_today());
		}
	},
});
