// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

/* The Skills Bank (competency.skills_bank): who holds a skill, or the skills a
 * word names (a machine among them), at a level or above, in a plant,
 * section or shift; whether they are on leave today; and each plant's cover
 * on each shift against the people needed.
 */

frappe.provide("hrms_addon");

const SKB_STYLE = `
.skb { padding: 4px 0 24px; }
.skb-bar { display: grid; grid-template-columns: 2fr 1fr 1fr 1fr 1fr 1fr; gap: 8px; margin-bottom: 12px; align-items: end; }
.skb-bar .form-group { margin: 0; }
.skb-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 12px 14px; margin-bottom: 12px; }
.skb-card h4 { font-size: 14px; font-weight: 600; margin: 0 0 8px; }
.skb-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.skb-table th { text-align: left; color: var(--text-muted); font-weight: 500; font-size: 11.5px; padding: 6px 8px; border-bottom: 1px solid var(--border-color); }
.skb-table td { padding: 6px 8px; border-bottom: 1px solid var(--border-color); }
.skb-pill { border-radius: 10px; padding: 1px 8px; font-size: 11px; }
.skb-red { background: #F8DADA; color: #8C2323; } .skb-amber { background: #FCEBC8; color: #7A4F08; }
.skb-green { background: #E3F1E8; color: #1F5C3C; } .skb-grey { background: var(--control-bg); color: var(--text-muted); }
.skb-empty { color: var(--text-muted); padding: 6px 0; }
@media (max-width: 900px) { .skb-bar { grid-template-columns: 1fr 1fr; } }
`;

frappe.pages["skills-bank"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Skills Bank"), single_column: true });
	wrapper.skills_bank = new hrms_addon.SkillsBank(page);
};

hrms_addon.SkillsBank = class SkillsBank {
	constructor(page) {
		this.page = page;
		if (!document.getElementById("skb-style")) $("<style id='skb-style'>").text(SKB_STYLE).appendTo(document.head);
		this.$root = $(`<div class="skb"><div class="skb-bar"></div><div class="skb-body"><div class="skb-empty">${__(
			"Type a skill or a machine, or pick a skill.")}</div></div></div>`).appendTo(page.main);
		const $bar = this.$root.find(".skb-bar");
		const make = (df) => frappe.ui.form.make_control({ parent: $("<div>").appendTo($bar), df: Object.assign({
			change: () => this.search() }, df), render_input: true });
		this.text = make({ fieldtype: "Data", fieldname: "text", label: __("Skill or Machine") });
		this.skill = make({ fieldtype: "Link", options: "Skill", fieldname: "skill", label: __("Skill") });
		this.level = make({ fieldtype: "Select", fieldname: "level", label: __("Level or Above"), options: "1\n2\n3\n4\n5",
			default: "3" });
		this.level.set_value("3");
		this.branch = make({ fieldtype: "Link", options: "Branch", fieldname: "branch", label: __("Plant") });
		this.section = make({ fieldtype: "Link", options: "Work Section", fieldname: "work_section", label: __("Section") });
		this.shift = make({ fieldtype: "Link", options: "Shift Type", fieldname: "shift", label: __("Shift") });
	}

	search() {
		const args = { text: this.text.get_value() || null, skill: this.skill.get_value() || null,
			min_level: this.level.get_value() || 3, branch: this.branch.get_value() || null,
			work_section: this.section.get_value() || null, shift: this.shift.get_value() || null };
		if (!args.text && !args.skill) return;
		frappe.xcall("hrms_addon.hrms_addon.competency.skills_bank", args).then((found) => this.render(found || {}));
	}

	render(found) {
		const esc = frappe.utils.escape_html;
		const $body = this.$root.find(".skb-body");
		if (!(found.skills || []).length) {
			$body.html(`<div class="skb-empty">${__("No skill or machine by that name.")}</div>`);
			return;
		}
		const holders = found.holders || [];
		const people = holders.length
			? `<table class="skb-table"><thead><tr><th>${__("Employee")}</th><th>${__("Skill")}</th><th>${__("Level")}</th>
				<th>${__("Plant")}</th><th>${__("Section")}</th><th>${__("Shift Today")}</th><th>${__("Today")}</th><th>${__("Due Again")}</th></tr></thead>
				<tbody>${holders.map((row) => `<tr><td><a href="/app/learning-passport/${encodeURIComponent(row.employee)}">${esc(row.employee_name || row.employee)}</a></td>
				<td>${esc(row.skill)}</td><td>${esc(String(row.level || "").split(" ")[0])}</td><td>${esc(row.branch || "")}</td>
				<td>${esc(row.work_section || "")}</td><td>${esc(row.shift || "")}</td>
				<td>${row.on_leave ? `<span class="skb-pill skb-amber">${__("On Leave")}</span>` : `<span class="skb-pill skb-green">${__("Available")}</span>`}</td>
				<td>${row.next_due ? frappe.datetime.str_to_user(row.next_due) : ""}</td></tr>`).join("")}</tbody></table>`
			: `<div class="skb-empty">${__("Nobody holds it at that level.")}</div>`;
		const cover = (found.cover || []).length
			? `<table class="skb-table"><thead><tr><th>${__("Skill")}</th><th>${__("Plant")}</th><th>${__("Needed per Shift")}</th>
				<th>${__("Competent by Shift")}</th><th>${__("Cover")}</th></tr></thead><tbody>${found.cover.map((row) => `<tr>
				<td>${esc(row.skill)}</td><td>${esc(row.branch || "")}</td><td>${row.need}</td>
				<td>${Object.entries(row.by_shift || {}).map(([shift, count]) => `${esc(shift || __("No Shift"))}: ${count}`).join(", ")}</td>
				<td><span class="skb-pill skb-${row.risk}">${__(row.status)}</span></td></tr>`).join("")}</tbody></table>`
			: `<div class="skb-empty">${__("Nobody is competent in it yet.")}</div>`;
		$body.html(`<div class="skb-card"><h4>${__("Who Holds It")} (${found.count || 0})</h4>${people}</div>
			<div class="skb-card"><h4>${__("Cover by Plant and Shift")}</h4>${cover}</div>`);
	}
};
