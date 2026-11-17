// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// The quarter's HR board pack (board_pack.py): the figures from the month snapshots, shown here,
// and the deck and workbook made from them with HR's words (board_deck.py).
frappe.ui.form.on("HR Board Report", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.year) {
			const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
			frm.set_value("year", today.getFullYear());
		}
	},
	refresh(frm) {
		frm.trigger("show_figures");
		if (!frm.is_new() && frm.doc.figures_json) {
			const download = (method) =>
				window.open(`/api/method/hrms_addon.hrms_addon.board_pack.${method}?name=${encodeURIComponent(frm.doc.name)}`);
			frm.add_custom_button(__("Deck (PowerPoint)"), () => download("download_deck"), __("Download"));
			frm.add_custom_button(__("Workbook (Excel)"), () => download("download_workbook"), __("Download"));
		}
	},
	get_figures(frm) {
		const take = () =>
			frappe.xcall("hrms_addon.hrms_addon.board_pack.get_figures", { name: frm.doc.name }).then((found) => {
				const notes = [];
				if ((found.missing || []).length) {
					notes.push(__("No snapshot for {0}: build or import it.", [found.missing.join(", ")]));
				}
				if (found.last_year_missing) {
					notes.push(__("Last year's months are not in yet: import them as HR Monthly Snapshots."));
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
		const table = (head, rows) =>
			`<table class="table table-bordered table-sm" style="font-size:12px;margin-bottom:12px">
				<thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
				<tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
		const plant = (value) => esc(value || __("Total"));
		const exits = figures.exits || [];
		field.$wrapper.html(
			`<div style="font-weight:600;margin:4px 0 8px">${esc(figures.label || "")}</div>` +
				table(
					[__("Plant"), __("Permanent"), __("Casual"), __("Total"), __("Hires"), __("Exits"), __("Avg Attrition")],
					(figures.head_count || []).map((row, index) => [
						plant(row.plant), num(row.permanent), num(row.casual), num(row.total),
						num((figures.recruitment || [])[index] ? figures.recruitment[index].total : null),
						num(exits[index] ? exits[index].total : null), pct(exits[index] ? exits[index].average : null),
					])
				) +
				table(
					[__("Plant"), __("Wage Bill"), __("Revenue"), __("Staff Cost %"), __("Cost / kg"), __("Incidents")],
					(figures.labour_cost || []).map((row, index) => [
						plant(row.plant), num((figures.wage_bill || [])[index] ? figures.wage_bill[index].wage_bill : null),
						num(row.revenue), pct(row.share), num(row.cost_per_kg),
						num((figures.safety || [])[index] ? figures.safety[index].total : null),
					])
				)
		);
	},
});
