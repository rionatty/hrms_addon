// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// The quarter's HR board pack (board_pack.py): the figures from the facts of its months, the KPIs and ratings worked
// out, the board actions it carries, and the deck and workbook made from them with HR's words (board_deck.py).
frappe.ui.form.on("HR Board Report", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.year) {
			const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
			frm.set_value("year", today.getFullYear());
		}
	},
	refresh(frm) {
		frm.trigger("show_figures");
		frm.trigger("show_actions");
		if ((frm.doc.text_flags || []).length) {
			frm.set_intro(__("Some of the words go against the figures: see Words Against the Figures."), "orange");
		}
		if (!frm.is_new() && frm.doc.figures_json) {
			const download = (method) =>
				window.open(`/api/method/hrms_addon.hrms_addon.board_pack.${method}?name=${encodeURIComponent(frm.doc.name)}`);
			frm.add_custom_button(__("Deck (PowerPoint)"), () => download("download_deck"), __("Download"));
			frm.add_custom_button(__("Workbook (Excel)"), () => download("download_workbook"), __("Download"));
		}
		if (!frm.is_new()) {
			frm.add_custom_button(__("Board Dashboard"), () => frappe.set_route("board-dashboard"), __("View"));
			frm.add_custom_button(__("New Board Action"), () =>
				frappe.new_doc("Board Action", {
					company: frm.doc.company,
					raised_year: frm.doc.year,
					raised_quarter: frm.doc.quarter,
				})
			);
		}
	},
	get_figures(frm) {
		const take = () =>
			frappe.xcall("hrms_addon.hrms_addon.board_pack.get_figures", { name: frm.doc.name }).then((found) => {
				const notes = [];
				if ((found.missing || []).length) {
					notes.push(__("Not built yet: {0}. Build them in HR Monthly Snapshot.", [found.missing.join(", ")]));
				}
				if (found.last_year_missing) {
					notes.push(__("Last year's months are not in yet: import them into HR Employee Month."));
				}
				if (notes.length) {
					frappe.msgprint(notes.join("<br>"), __("Figures"));
				}
				frm.reload_doc();
			});
		if (frm.is_new() || frm.is_dirty()) {
			frm.save().then(take);
		} else {
			take();
		}
	},
	show_actions(frm) {
		const field = frm.get_field("actions_html");
		if (!field || frm.is_new()) return;
		frappe.xcall("hrms_addon.hrms_addon.board_pack.report_actions", { name: frm.doc.name }).then((rows) => {
			const esc = frappe.utils.escape_html;
			if (!(rows || []).length) {
				field.$wrapper.html(`<div class="text-muted">${__("No board actions for this quarter yet.")}</div>`);
				return;
			}
			field.$wrapper.html(
				`<table class="table table-bordered table-sm" style="font-size:12px">
					<thead><tr><th>${__("Business Imperative")}</th><th>${__("Owner")}</th><th>${__("Due")}</th>
					<th>${__("Status")}</th><th>${__("Progress")}</th></tr></thead>
					<tbody>${rows
						.map(
							(row) => `<tr><td><a href="/app/board-action/${encodeURIComponent(row.name)}">${esc(
								row.imperative || ""
							)}</a></td><td>${esc(row.action_owner_name || "")}</td><td>${esc(
								`${row.due_quarter || ""} ${row.due_year || ""}`
							)}</td><td>${esc(row.status || "")}</td><td>${esc(String(Math.round(row.progress || 0)))}%</td></tr>`
						)
						.join("")}</tbody></table>`
			);
		});
	},
	show_figures(frm) {
		const field = frm.get_field("figures_preview");
		if (!field) {
			return;
		}
		let figures = {};
		try {
			figures = JSON.parse(frm.doc.figures_json || "{}");
		} catch (e) {
			figures = {};
		}
		if (!figures.head_count) {
			field.$wrapper.html(`<div class="text-muted">${__("Get the figures to see the quarter here.")}</div>`);
			return;
		}
		const esc = frappe.utils.escape_html;
		const num = (value) => (value === null || value === undefined ? "–" : format_number(value, null, 0));
		const pct = (value) => (value === null || value === undefined ? "–" : `${format_number(value, null, 1)}%`);
		const colours = { "On Track": "#1F7A4D", Watch: "#B7791F", "Action Needed": "#A62B25" };
		const light = (value) =>
			`<span style="display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;background:${
				colours[value] || "#D1D5DB"
			}"></span>${esc(value || "")}`;
		const table = (head, rows) =>
			`<table class="table table-bordered table-sm" style="font-size:12px;margin-bottom:12px">
				<thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
				<tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
		const plant = (value) => esc(value || __("Total"));
		const exits = figures.exits || [];
		const recon = figures.reconciliation || [];
		field.$wrapper.html(
			`<div style="font-weight:600;margin:4px 0 8px">${esc(figures.label || "")}</div>` +
				table(
					[__("Plant"), __("Permanent"), __("Casual"), __("Total"), __("Hires"), __("Exits"), __("Avg Attrition"),
						__("Variance")],
					(figures.head_count || []).map((row, index) => [
						plant(row.plant), num(row.permanent), num(row.casual), num(row.total),
						num((figures.recruitment || [])[index] ? figures.recruitment[index].total : null),
						num(exits[index] ? exits[index].total : null), pct(exits[index] ? exits[index].average : null),
						num(recon[index] ? recon[index].variance : null),
					])
				) +
				table(
					[__("Plant"), __("Wage Bill"), __("Revenue"), __("Staff Cost %"), __("Cost / kg"), __("Incidents"),
						__("Near Misses")],
					(figures.labour_cost || []).map((row, index) => [
						plant(row.plant), num((figures.wage_bill || [])[index] ? figures.wage_bill[index].wage_bill : null),
						num(row.revenue), pct(row.share), num(row.cost_per_kg),
						num((figures.safety || [])[index] ? figures.safety[index].total : null),
						num((figures.safety || [])[index] ? figures.safety[index].near_misses : null),
					])
				) +
				table(
					[__("KPI"), __("Reading"), __("Light")],
					(figures.kpis || []).map((row) => [esc(row.name || ""), esc(row.reading || ""), light(row.light)])
				)
		);
	},
});
