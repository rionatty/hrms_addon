// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// The settings' Guide: the KPI dictionary, who enters what, and the rules HR
// keeps to (excellence.guide).
frappe.ui.form.on("Manufacturing Excellence Settings", {
	refresh(frm) {
		frappe.xcall("hrms_addon.hrms_addon.excellence.guide").then((guide) => {
			frm.get_field("guide_html").$wrapper.html(me_guide_html(guide));
		});
	},
});

function me_guide_html(guide) {
	const esc = (text) => frappe.utils.escape_html(text || "");
	const table = (heads, rows) =>
		`<table class="table table-bordered table-condensed" style="font-size:12px"><thead><tr>${heads
			.map((head) => `<th>${esc(__(head))}</th>`)
			.join("")}</tr></thead><tbody>${rows
			.map((row) => `<tr>${row.map((cell) => `<td>${esc(cell)}</td>`).join("")}</tr>`)
			.join("")}</tbody></table>`;
	return [
		`<h5>${esc(__("Indicators"))}</h5>`,
		table(["Indicator", "Pillar", "How It Is Worked Out", "Source", "Owner", "Target"], guide.kpis),
		`<h5>${esc(__("Who Enters What"))}</h5>`,
		table(["Document", "Entered By", "What", "When", "Checked By", "Used For"], guide.guide),
		`<h5>${esc(__("Rules"))}</h5>`,
		table(["Rule", "What Happens"], guide.governance),
	].join("");
}
