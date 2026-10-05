// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt
//
// A critical role and its bench (test cases 11 to 15), and what the plan
// has led to once confirmed: each successor's development plan, the
// holder's exit, and what fills the role when they go, the promotion
// drafted for a successor or the requisition for a replacement
// (talent.get_follow_through).

frappe.ui.form.on("Succession Position", {
	setup(frm) {
		// what points at a plan is cancelled on its own (talent.position_on_cancel)
		frm.ignore_doctypes_on_cancel_all = [
			...new Set([...(frm.ignore_doctypes_on_cancel_all || []),
				"Talent Program", "Employee Position Change", "Employee Separation", "Graduate Trainee Program"]),
		];
	},
	refresh(frm) {
		frm.trigger("say_coverage");
		// test case 12: successors are nominated from the finalised talent
		// pool, so the picker offers finalised placements only
		frm.fields_dict.candidates.grid.get_field("placement").get_query = () => ({
			filters: { docstatus: 1, status: "Finalised" },
		});
		if (frm.doc.job_opening) {
			frm.add_custom_button(__("Job Opening"), () =>
				frappe.set_route("Form", "Job Opening", frm.doc.job_opening)
			);
		}
		if (frm.doc.docstatus === 0 && frm.doc.gap && !frm.doc.gap_confirmed) {
			frm.dashboard.add_comment(
				__("There is nobody ready now. Confirming the gap drafts a job requisition when this is submitted."),
				"orange",
				true
			);
		}
		frm.trigger("show_follow_through");
	},
	say_coverage(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new() || !frm.doc.coverage) return;
		const colour =
			frm.doc.coverage === "Gap" ? "red" : frm.doc.coverage === "At Risk" ? "orange" : "green";
		frm.dashboard.set_headline(
			`<span class="indicator-pill ${colour}">${__(frm.doc.coverage)}</span>` +
				` <span>${__("Ready now")}: <b>${frm.doc.ready_now || 0}</b>,` +
				` ${__("in 1-2 years")}: <b>${frm.doc.ready_soon || 0}</b>,` +
				` ${__("emerging")}: <b>${frm.doc.emerging || 0}</b></span>`
		);
	},
	show_follow_through(frm) {
		if (frm.is_new()) return;
		frappe
			.call({ method: "hrms_addon.hrms_addon.talent.get_follow_through", args: { position: frm.doc.name } })
			.then((result) => {
				const html = ha_follow_through(frm, (result && result.message) || {});
				if (html) frm.dashboard.add_section(html, __("Filling the Role"), "custom ha-follow");
			});
	},
});

frappe.ui.form.on("Succession Candidate", {
	placement(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.placement) return;
		frappe.db.get_value("Talent Placement", row.placement, ["employee", "box_name"]).then((result) => {
			const found = (result && result.message) || {};
			if (found.employee && !row.employee) {
				frappe.model.set_value(cdt, cdn, "employee", found.employee);
			}
			if (found.box_name) {
				frappe.model.set_value(cdt, cdn, "box_name", found.box_name);
			}
		});
	},
});

// The plan's follow-through, a line for each thing it has led to.
function ha_follow_through(frm, data) {
	const esc = frappe.utils.escape_html;
	const link = (doctype, name) =>
		`<a href="/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}">${esc(name)}</a>`;
	const line = (label, value) =>
		`<div style="display:flex;gap:12px;padding:4px 0"><span class="text-muted" style="min-width:150px">${esc(label)}</span><span>${value}</span></div>`;
	const lines = [];
	if (frm.doc.retirement_or_exit_due) {
		const days = data.days;
		const when = days > 0 ? __("in {0} days", [days]) : days === 0 ? __("today") : __("{0} days ago", [-days]);
		const exit = data.exit;
		let text = `${esc(frm.doc.incumbent_name || frm.doc.incumbent || __("The holder"))} ${esc(
			__("leaves on {0}", [frappe.datetime.str_to_user(frm.doc.retirement_or_exit_due)])
		)} <span class="text-muted">(${esc(when)})</span>`;
		if (exit) text += ` &middot; ${esc(__(exit.custom_reason || "Exit"))} ${link("Employee Separation", exit.name)}`;
		lines.push(line(__("Holder's exit"), text));
	}
	if (data.promotion) {
		lines.push(line(__("Promotion"), `${esc(data.promotion.employee_name || data.promotion.employee)} ${link(
			"Employee Position Change", data.promotion.name)} <span class="indicator-pill ${data.promotion.docstatus ? "green" : "orange"}">${esc(
			__(data.promotion.status || "Draft"))}</span>`));
	} else if (data.successor) {
		lines.push(line(__("Ready now"), esc(data.successor.employee_name || data.successor.employee)));
	}
	if (data.requisition) {
		const state = data.requisition.workflow_state || data.requisition.status;
		lines.push(line(__("Job requisition"), `${link("Job Requisition", data.requisition.name)} <span class="indicator-pill ${
			["Rejected", "Cancelled"].includes(data.requisition.status) ? "red" : "blue"}">${esc(__(state || "Draft"))}</span>`));
	}
	if (data.opening) {
		lines.push(line(__("Job opening"), `${link("Job Opening", data.opening.name)} <span class="indicator-pill blue">${esc(
			__(data.opening.status || ""))}</span>`));
	}
	const plans = data.plans || {};
	(frm.doc.candidates || []).filter((row) => row.development_plan).forEach((row) => {
		const progress = plans[row.development_plan] || { actions: 0, done: 0, share: 0, late: 0 };
		lines.push(line(__("Plan for {0}", [row.employee_name || row.employee]), `${link("Talent Program", row.development_plan)}
			<span class="text-muted">${esc(__("{0} of {1} actions done", [progress.done, progress.actions]))}</span>
			${progress.late ? `<span class="indicator-pill red">${esc(__("{0} past their date", [progress.late]))}</span>` : ""}`));
	});
	return lines.length ? `<div class="ha-follow-lines">${lines.join("")}</div>` : "";
}
