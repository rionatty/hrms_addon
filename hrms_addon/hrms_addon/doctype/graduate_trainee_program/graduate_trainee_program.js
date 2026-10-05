// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Graduate Trainee Program", {
	refresh(frm) {
		frm.trigger("say_where");
		ha_trainee_journey(frm);
		if (frm.doc.employee) {
			frm.add_custom_button(__("Employee"), () =>
				frappe.set_route("Form", "Employee", frm.doc.employee)
			);
		}
		if (frm.doc.placement) {
			frm.add_custom_button(__("Nine-Box Placement"), () =>
				frappe.set_route("Form", "Talent Placement", frm.doc.placement)
			);
		}
	},
	say_where(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new()) return;
		const parts = [`<span>${__("Cohort")} <b>${frappe.utils.escape_html(frm.doc.cohort || "")}</b></span>`];
		const rotations = (frm.doc.rotations || []).length;
		if (rotations) {
			const done = (frm.doc.rotations || []).filter((row) => row.completed).length;
			parts.push(`<span>${__("Rotations")}: <b>${done}/${rotations}</b></span>`);
		}
		const milestones = (frm.doc.milestones || []).length;
		if (milestones) {
			parts.push(
				`<span>${__("Milestones passed")}: <b>${frm.doc.milestones_passed || 0}/${milestones}</b></span>`
			);
		}
		if (frm.doc.average_score) {
			const colour = frm.doc.average_score < 60 ? "red" : "green";
			parts.push(
				`<span class="indicator-pill ${colour}">${__("Average")} ${frm.doc.average_score}</span>`
			);
		}
		frm.dashboard.set_headline(parts.join(" &nbsp;|&nbsp; "));
	},
});

frappe.ui.form.on("Trainee Rotation", {
	// a trainee is in one place at a time, so the next stint starts after
	// the last one ends
	rotations_add(frm, cdt, cdn) {
		const rows = frm.doc.rotations || [];
		const previous = rows[rows.length - 2];
		if (previous && previous.to_date) {
			frappe.model.set_value(cdt, cdn, "from_date", frappe.datetime.add_days(previous.to_date, 1));
		}
	},
});

frappe.ui.form.on("Trainee Milestone", {
	// a score typed in reads as the server reads it (talent_rules
	// .final_milestone): the milestone due as the programme ends is the
	// final one; with no end set, the last
	score(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.score === undefined || row.score === null || row.result) return;
		const rows = frm.doc.milestones || [];
		const last = rows.length && rows[rows.length - 1].name === cdn;
		const final = frm.doc.end_date && row.due_on ? row.due_on >= frm.doc.end_date : last;
		frappe.model.set_value(cdt, cdn, "result", row.score < 60 ? "Fail" : final ? "Final Pass" : "Pass");
	},
});

// The trainee's journey, start to finish: taken on, each rotation, each
// milestone and its appraisal, and how it ended.
function ha_trainee_journey(frm) {
	frm.$wrapper.find(".form-dashboard-section.ha-journey").remove();
	if (frm.is_new()) return;
	const esc = frappe.utils.escape_html;
	const day = (value) => (value ? frappe.datetime.str_to_user(value) : "");
	const steps = [];
	steps.push({
		done: !!frm.doc.employee,
		title: __("Taken on"),
		text: [day(frm.doc.start_date), frm.doc.mentor_name ? __("mentor {0}", [frm.doc.mentor_name]) : ""]
			.filter(Boolean).join(" · "),
	});
	(frm.doc.rotations || []).forEach((row) => {
		steps.push({
			done: !!row.completed,
			title: row.department || row.branch || __("Rotation"),
			text: [`${day(row.from_date)} – ${day(row.to_date)}`, row.score ? __("scored {0}", [row.score]) : ""]
				.filter(Boolean).join(" · "),
		});
	});
	(frm.doc.milestones || []).forEach((row) => {
		const result = row.result
			? `<b style="color:${row.result === "Fail" ? "#A62B25" : "#1E6B34"}">${esc(__(row.result))}</b>` : "";
		const appraisal = row.appraisal
			? `<a href="/app/appraisal/${encodeURIComponent(row.appraisal)}">${esc(__("appraisal"))}</a>` : "";
		steps.push({
			done: !!row.result,
			title: row.milestone || __("Milestone"),
			html: [esc(day(row.due_on)), row.score ? esc(String(row.score)) : "", result, appraisal].filter(Boolean).join(" · "),
		});
	});
	const state = frm.doc.workflow_state || frm.doc.status;
	if (state === "Confirmed") {
		steps.push({ done: true, title: __("Confirmed"), text: [day(frm.doc.confirmed_on), frm.doc.confirmed_employment_type].filter(Boolean).join(" · ") });
	} else if (state === "Exited") {
		steps.push({ done: true, bad: true, title: __("Left the programme"), text: frm.doc.exit_reason || "" });
	} else {
		steps.push({ done: false, title: __("Confirmation"), text: day(frm.doc.end_date) });
	}
	const html = `<div style="display:flex;gap:0;overflow-x:auto;padding:4px 0 2px">${steps.map((step, index) => `
		<div style="flex:1;min-width:130px;position:relative;padding:0 10px 0 0">
			<div style="display:flex;align-items:center">
				<span style="width:14px;height:14px;border-radius:50%;flex:none;background:${step.bad ? "#A62B25" : step.done ? "#14395E" : "var(--card-bg)"};
					border:2px solid ${step.bad ? "#A62B25" : "#14395E"}"></span>
				${index < steps.length - 1 ? `<span style="flex:1;height:2px;background:${step.done ? "#14395E" : "var(--border-color)"}"></span>` : ""}
			</div>
			<div style="font-weight:600;font-size:12.5px;margin-top:6px">${esc(step.title)}</div>
			<div class="text-muted" style="font-size:12px">${step.html || esc(step.text || "")}</div>
		</div>`).join("")}</div>`;
	frm.dashboard.add_section(html, __("Journey"), "custom ha-journey");
}
