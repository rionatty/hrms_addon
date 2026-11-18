// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// A section's people against its skills (learning_sheets.py): Get Employees
// fills the rows, the grid gives each a level, Submit makes the assessments.
const LMSX_LEVELS = ["", "1 Awareness", "2 Basic Understanding", "3 Works Under Supervision", "4 Competent Independently",
	"5 Can Train and Supervise"];

frappe.ui.form.on("Skills Assessment Sheet", {
	setup(frm) {
		frm.set_query("assessor", () => ({ filters: { status: "Active" } }));
		frm.set_query("work_section", () => ({ filters: frm.doc.branch ? { branch: frm.doc.branch } : {} }));
		frm.set_query("skill", "skills", () => ({ filters: { custom_skill_type: ["is", "set"] } }));
	},
	refresh(frm) {
		hrms_addon.sheet_progress(frm);
		lmsx_skills_grid(frm);
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Employees"), () => lmsx_get_skill_rows(frm)).addClass("btn-primary");
		}
	},
	rows_remove: lmsx_skills_grid,
});

frappe.ui.form.on("Skills Assessment Sheet Row", {
	level(frm) {
		lmsx_skills_grid(frm);
	},
});

function lmsx_get_skill_rows(frm) {
	const skills = (frm.doc.skills || []).map((row) => row.skill).filter(Boolean);
	if (!skills.length) {
		frappe.msgprint(__("Pick the skills first."));
		return;
	}
	frappe
		.xcall("hrms_addon.hrms_addon.learning_sheets.skill_rows", {
			company: frm.doc.company || null,
			branch: frm.doc.branch || null,
			work_section: frm.doc.work_section || null,
			department: frm.doc.department || null,
			skills: JSON.stringify(skills),
			have: JSON.stringify((frm.doc.rows || []).map((row) => [row.employee, row.skill])),
		})
		.then((rows) => {
			(rows || []).forEach((row) => frm.add_child("rows", row));
			frm.refresh_field("rows");
			lmsx_skills_grid(frm);
			frm.dirty();
			frappe.show_alert({ message: __("{0} rows added.", [(rows || []).length]), indicator: "green" });
		});
}

// the rows as a grid: an employee a line, a skill a column, a level in each cell
function lmsx_skills_grid(frm) {
	const field = frm.fields_dict.grid_html;
	if (!field) return;
	const rows = frm.doc.rows || [];
	if (!rows.length) {
		field.$wrapper.html(`<div class="text-muted small">${__("Pick the skills, then Get Employees.")}</div>`);
		return;
	}
	const esc = frappe.utils.escape_html;
	const skills = [...new Set(rows.map((row) => row.skill))];
	const people = [];
	const cells = {};
	rows.forEach((row) => {
		if (!people.some((person) => person.employee === row.employee)) people.push(row);
		cells[row.employee + "\u0001" + row.skill] = row;
	});
	const locked = frm.doc.docstatus !== 0;
	const cell = (row) => {
		if (!row) return "<td></td>";
		const now = row.current_level ? `<div class="text-muted small">${esc(String(row.current_level).split(" ")[0])} ${__("now")}</div>` : "";
		if (locked) return `<td>${esc(row.level || "")}${now}</td>`;
		return `<td><select class="form-control input-xs" data-row="${esc(row.name)}">${LMSX_LEVELS.map((level) =>
			`<option value="${esc(level)}" ${level === (row.level || "") ? "selected" : ""}>${esc(level ? level.split(" ")[0] : "")}</option>`).join("")}</select>${now}</td>`;
	};
	field.$wrapper.html(`<div style="overflow-x:auto;max-height:520px"><table class="table table-bordered table-condensed small">
		<thead><tr><th>${__("Employee")}</th>${skills.map((skill) => `<th>${esc(skill)}</th>`).join("")}</tr></thead>
		<tbody>${people.map((person) => `<tr><td>${esc(person.employee_name || person.employee)}</td>${skills
			.map((skill) => cell(cells[person.employee + "\u0001" + skill])).join("")}</tr>`).join("")}</tbody></table></div>`);
	field.$wrapper.find("select[data-row]").on("change", (event) => {
		const $select = $(event.currentTarget);
		frappe.model.set_value("Skills Assessment Sheet Row", $select.attr("data-row"), "level", $select.val());
	});
}
