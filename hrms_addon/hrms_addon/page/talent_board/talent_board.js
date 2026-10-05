// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

/* The Talent Board — one review on one grid (talent_board.py).
 *
 * Everyone in a review sits in their nine-box cell, filtered by plant,
 * department and grade; the talent card of whoever is clicked opens beside
 * the grid. In calibration HR moves a person up or down their column by
 * dragging them, and says why: performance is the appraisal's, so a move
 * across columns is refused. The steps the board takes for everybody at
 * once — send to the council, finalise, return — are in the Actions menu,
 * each placement taken as it is on its own form.
 *
 * The styles live in this file, as on the HR Overview, so the page never
 * waits on `bench build`. Only HR and the Talent Council open it (the
 * page's roles), and the server checks again (talent_board._check_access).
 */

frappe.provide("hrms_addon");

// rows from high potential down, columns from low performance across
const TB_ORDER = [[3, 6, 9], [2, 5, 8], [1, 4, 7]];
const TB_POTENTIAL = ["High", "Moderate", "Low"];
const TB_PERFORMANCE = ["Low", "Meeting", "Exceeding"];
// box -> its column (performance band)
const TB_COLUMN = { 1: "Low", 2: "Low", 3: "Low", 4: "Meeting", 5: "Meeting", 6: "Meeting", 7: "Exceeding", 8: "Exceeding", 9: "Exceeding" };
const TB_SHOWN = 6;

const TB_STYLE = `
.tb { padding: 4px 0 28px; color: var(--text-color); }
.tb-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
.tb-title { font-size: 18px; font-weight: 600; color: var(--heading-color, var(--text-color)); }
.tb-pill { border-radius: 999px; padding: 2px 10px; font-size: 12px; background: var(--control-bg); color: var(--text-muted); }
.tb-pill.tb-live { background: #FBF1D3; color: #6B4F00; }
.tb-tiles { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }
.tb-tile { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 10px 12px; }
.tb-tile small { display: block; color: var(--text-muted); font-size: 11.5px; }
.tb-tile b { font-size: 20px; font-weight: 600; }
.tb-tile em { font-style: normal; color: var(--text-muted); font-size: 12px; margin-left: 4px; }
.tb-main { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 14px; align-items: start; }
.tb-grid { display: grid; grid-template-columns: 22px repeat(3, minmax(0, 1fr)); grid-template-rows: repeat(3, auto) 22px; gap: 8px; }
.tb-axis { color: var(--text-muted); font-size: 11.5px; display: flex; align-items: center; justify-content: center; }
.tb-axis.tb-y { writing-mode: vertical-rl; transform: rotate(180deg); }
.tb-cell { border-radius: 10px; padding: 8px; min-height: 150px; border: 2px solid transparent; transition: border-color .12s; }
.tb-cell.tb-over { border-color: #E8A317; }
.tb-cell.tb-refuse { border-color: #A62B25; }
.tb-cell-head { display: flex; justify-content: space-between; gap: 6px; font-weight: 600; font-size: 12.5px; margin-bottom: 4px; }
.tb-cell-head span:last-child { opacity: .8; }
.tb-cell-act { font-size: 11px; opacity: .8; margin-bottom: 6px; }
.tb-chip { display: flex; align-items: center; gap: 6px; background: var(--card-bg); color: var(--text-color);
  border-radius: 14px; padding: 3px 8px 3px 3px; margin-top: 5px; cursor: pointer; border: 1px solid transparent;
  white-space: nowrap; overflow: hidden; }
.tb-chip:hover { border-color: #14395E; }
.tb-chip.tb-picked { border-color: #E8A317; box-shadow: 0 0 0 1px #E8A317; }
.tb-chip.tb-drag { cursor: grab; }
.tb-chip .tb-av { width: 22px; height: 22px; border-radius: 50%; background: #14395E; color: #fff; font-size: 10px;
  display: flex; align-items: center; justify-content: center; flex: none; }
.tb-chip .tb-nm { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; font-size: 12px; }
.tb-chip .tb-sc { color: var(--text-muted); font-size: 11px; }
.tb-flag { border-radius: 6px; padding: 0 5px; font-size: 10px; font-weight: 600; }
.tb-flag.tb-pip { background: #F8DADA; color: #8C2323; }
.tb-flag.tb-risk { background: #FBF1D3; color: #8A4A12; }
.tb-flag.tb-moved { background: #DCE8F7; color: #14395E; }
.tb-more { margin-top: 6px; font-size: 11.5px; cursor: pointer; text-decoration: underline; opacity: .85; }
.tb-panel { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 14px;
  position: sticky; top: 70px; }
.tb-panel-empty { color: var(--text-muted); padding: 30px 6px; text-align: center; }
.tb-lower { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; margin-top: 14px; }
.tb-box { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 12px 14px; }
.tb-box h6 { margin: 0 0 8px; font-size: 13px; font-weight: 600; }
.tb-list { width: 100%; font-size: 12px; }
.tb-list td { padding: 5px 4px; border-top: 1px solid var(--border-color); vertical-align: top; }
.tb-list td:first-child { padding-left: 0; }
.tb-empty { color: var(--text-muted); font-size: 12px; }
.tb-start { text-align: center; padding: 60px 10px; color: var(--text-muted); }
@media (max-width: 1199px) { .tb-tiles { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
@media (max-width: 991px) {
  .tb-main, .tb-lower { grid-template-columns: minmax(0, 1fr); }
  .tb-panel { position: static; }
}
@media (max-width: 575px) { .tb-tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
`;

frappe.pages["talent-board"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Talent Board"), single_column: true });
	wrapper.talent_board = new hrms_addon.TalentBoard(page);
};

frappe.pages["talent-board"].on_page_show = function (wrapper) {
	if (wrapper.talent_board) wrapper.talent_board.refresh();
};

hrms_addon.TalentBoard = class TalentBoard {
	constructor(page) {
		this.page = page;
		if (!document.getElementById("tb-style")) {
			$('<style id="tb-style"></style>').text(TB_STYLE).appendTo("head");
		}
		hrms_addon.talent_card.style();
		const field = (fieldname, options, label) =>
			page.add_field({
				fieldname, fieldtype: "Link", options, label: __(label),
				change: () => {
					if (!this.quiet) this.refresh();
				},
			});
		this.fields = {
			review: field("review", "Talent Review", "Talent Review"),
			branch: field("branch", "Branch", "Plant"),
			department: field("department", "Department", "Department"),
			grade: field("grade", "Employee Grade", "Grade"),
		};
		this.body = $('<div class="tb"></div>').appendTo(page.main);
		page.set_secondary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.picked = null;
		this.open = {};
	}

	args() {
		const args = {};
		Object.entries(this.fields).forEach(([name, control]) => {
			const value = control.get_value();
			if (value) args[name] = value;
		});
		return args;
	}

	refresh() {
		return frappe
			.xcall("hrms_addon.hrms_addon.talent_board.get_board", this.args())
			.then((data) => this.render(data || {}));
	}

	render(data) {
		this.data = data;
		const esc = frappe.utils.escape_html;
		this.page.clear_inner_toolbar();
		if (!data.review) {
			this.body.html(`<div class="tb-start"><p>${esc(__("No talent review yet."))}</p>
				<button class="btn btn-primary btn-sm tb-new">${esc(__("New Talent Review"))}</button></div>`);
			this.body.find(".tb-new").on("click", () => frappe.new_doc("Talent Review"));
			return;
		}
		if (this.fields.review.get_value() !== data.review.name) {
			this.quiet = true;
			this.fields.review.set_value(data.review.name).then(() => (this.quiet = false));
		}
		const board = data.board || { cells: [], unplaced: [], total: 0 };
		const strips = data.strips || {};
		const states = data.states || {};
		const waiting = (board.unplaced || []).length;
		const tile = (label, value, extra) =>
			`<div class="tb-tile"><small>${esc(label)}</small><b>${value}</b>${extra ? `<em>${extra}</em>` : ""}</div>`;
		const strip = (name) => (strips[name] || { count: 0, share: 0 });
		const live = ["Open", "In Calibration"].includes(data.review.status);
		this.body.html(`
			<div class="tb-head">
				<span class="tb-title">${esc(data.review.title || data.review.name)}</span>
				<span class="tb-pill ${live ? "tb-live" : ""}">${esc(__(data.review.status || "Draft"))}</span>
				${data.review.appraisal_plan ? `<a class="tb-pill" href="/app/appraisal-plan/${encodeURIComponent(data.review.appraisal_plan)}">${esc(__("Appraisal Plan {0}", [data.review.appraisal_plan]))}</a>` : ""}
				<span class="tb-pill">${esc(__("{0} in calibration, {1} with the council, {2} finalised", [
					states["In Calibration"] || 0, states["Council Review"] || 0, states["Finalised"] || 0]))}</span>
			</div>
			<div class="tb-tiles">
				${tile(__("Placed"), board.total, waiting ? __("{0} waiting", [waiting]) : "")}
				${tile(__("Top talent"), strip("top").count, `${strip("top").share}%`)}
				${tile(__("Core"), strip("core").count, `${strip("core").share}%`)}
				${tile(__("Needs attention"), strip("attention").count, `${strip("attention").share}%`)}
				${tile(__("Top talent at risk"), data.flight_risk || 0)}
				${tile(__("On an improvement plan"), data.on_pip || 0)}
				${tile(__("Moved in calibration"), (data.movers || []).length)}
			</div>
			<div class="tb-main">
				<div class="tb-grid">${this.grid(board)}</div>
				<div class="tb-panel"><div class="tb-panel-empty">${esc(__("Click a person to see their talent card."))}</div></div>
			</div>
			<div class="tb-lower">
				<div class="tb-box"><h6>${esc(__("Waiting to be placed"))}</h6>${this.waiting(board.unplaced || [])}</div>
				<div class="tb-box"><h6>${esc(__("Moved in calibration"))}</h6>${this.movers(data.movers || [])}</div>
			</div>`);
		this.bind();
		this.actions(data);
		if (this.picked) this.show_card(this.picked);
	}

	grid(board) {
		const esc = frappe.utils.escape_html;
		const cells = {};
		(board.cells || []).forEach((cell) => (cells[cell.box] = cell));
		let html = "";
		TB_ORDER.forEach((row, index) => {
			html += `<div class="tb-axis tb-y">${esc(__("{0} potential", [__(TB_POTENTIAL[index])]))}</div>`;
			row.forEach((box) => {
				const cell = cells[box] || { box, name: "", colour: "", action: "", people: [] };
				const tint = hrms_addon.talent_card.tints[cell.colour] || ["var(--control-bg)", "var(--text-color)"];
				const people = cell.people || [];
				const shown = this.open[box] ? people : people.slice(0, TB_SHOWN);
				html += `<div class="tb-cell" data-box="${box}" style="background:${tint[0]};color:${tint[1]}">
					<div class="tb-cell-head"><span>${box} · ${esc(__(cell.name))}</span><span>${people.length}</span></div>
					<div class="tb-cell-act">${esc(__(cell.action))}</div>
					${shown.map((person) => this.chip(person)).join("")}
					${people.length > TB_SHOWN ? `<div class="tb-more" data-more="${box}">${esc(this.open[box]
						? __("Show fewer") : __("{0} more", [people.length - TB_SHOWN]))}</div>` : ""}
				</div>`;
			});
		});
		html += `<div></div>` + TB_PERFORMANCE.map((name) =>
			`<div class="tb-axis">${esc(__("{0} performance", [__(name)]))}</div>`).join("");
		return html;
	}

	chip(person) {
		const esc = frappe.utils.escape_html;
		const draggable = this.data.can_move && person.state === "In Calibration";
		const flags = [];
		if (person.on_pip) flags.push(`<span class="tb-flag tb-pip" title="${esc(__("On an improvement plan"))}">${esc(__("PIP"))}</span>`);
		if (person.top_talent && ["High", "Medium"].includes(person.flight_risk)) {
			flags.push(`<span class="tb-flag tb-risk" title="${esc(__("Flight risk {0}", [__(person.flight_risk)]))}">${esc(__("Risk"))}</span>`);
		}
		if (person.moved) flags.push(`<span class="tb-flag tb-moved" title="${esc(__("Moved in calibration"))}">${esc(__("Moved"))}</span>`);
		const score = person.performance_score !== null && person.performance_score !== undefined
			? format_number(person.performance_score, null, 0) : "";
		return `<div class="tb-chip ${draggable ? "tb-drag" : ""} ${this.picked === person.employee ? "tb-picked" : ""}"
			data-employee="${esc(person.employee)}" data-placement="${esc(person.name)}" data-box="${person.box}"
			${draggable ? 'draggable="true"' : ""}
			title="${esc([person.designation, person.branch, __(person.state)].filter(Boolean).join(" · "))}">
			<span class="tb-av">${esc(hrms_addon.talent_card.initials(person.employee_name))}</span>
			<span class="tb-nm">${esc(person.employee_name || person.employee)}</span>${flags.join("")}
			<span class="tb-sc">${score}</span></div>`;
	}

	waiting(rows) {
		const esc = frappe.utils.escape_html;
		if (!rows.length) return `<div class="tb-empty">${esc(__("Everyone in the review is placed."))}</div>`;
		return `<table class="tb-list">${rows.map((row) => `<tr>
			<td><a href="/app/talent-placement/${encodeURIComponent(row.name)}">${esc(row.employee_name || row.employee)}</a></td>
			<td>${esc(row.designation || "")}</td>
			<td>${esc(row.performance_score === null || row.performance_score === undefined
				? __("No completed appraisal this year") : __("Potential not rated"))}</td></tr>`).join("")}</table>`;
	}

	movers(rows) {
		const esc = frappe.utils.escape_html;
		if (!rows.length) return `<div class="tb-empty">${esc(__("Nobody has been moved."))}</div>`;
		return `<table class="tb-list">${rows.map((row) => `<tr>
			<td>${esc(row.employee_name || row.employee)}</td>
			<td>${row.from_box} → ${row.to_box}</td>
			<td>${esc(row.reason || "")}</td>
			<td class="text-muted">${esc(frappe.user.full_name(row.moved_by) || row.moved_by || "")}</td></tr>`).join("")}</table>`;
	}

	bind() {
		this.body.find(".tb-chip").on("click", (event) => {
			this.picked = $(event.currentTarget).attr("data-employee");
			this.body.find(".tb-chip").removeClass("tb-picked");
			this.body.find(`.tb-chip[data-employee="${CSS.escape(this.picked)}"]`).addClass("tb-picked");
			this.show_card(this.picked);
		});
		this.body.find("[data-more]").on("click", (event) => {
			const box = $(event.currentTarget).attr("data-more");
			this.open[box] = !this.open[box];
			this.render(this.data);
		});
		this.body.find(".tb-chip[draggable]").on("dragstart", (event) => {
			const chip = $(event.currentTarget);
			this.dragging = { placement: chip.attr("data-placement"), box: parseInt(chip.attr("data-box"), 10),
				name: chip.find(".tb-nm").text() };
			event.originalEvent.dataTransfer.setData("text/plain", this.dragging.placement);
		});
		this.body.find(".tb-cell")
			.on("dragover", (event) => {
				if (!this.dragging) return;
				const box = parseInt($(event.currentTarget).attr("data-box"), 10);
				const same = TB_COLUMN[box] === TB_COLUMN[this.dragging.box];
				$(event.currentTarget).toggleClass("tb-over", same).toggleClass("tb-refuse", !same);
				if (same) event.preventDefault();
			})
			.on("dragleave drop", (event) => $(event.currentTarget).removeClass("tb-over tb-refuse"))
			.on("drop", (event) => {
				event.preventDefault();
				const box = parseInt($(event.currentTarget).attr("data-box"), 10);
				const moving = this.dragging;
				this.dragging = null;
				if (moving && box !== moving.box) this.move(moving, box);
			});
		this.body.find(".tb-chip[draggable]").on("dragend", () => {
			this.dragging = null;
			this.body.find(".tb-cell").removeClass("tb-over tb-refuse");
		});
	}

	show_card(employee) {
		const panel = this.body.find(".tb-panel");
		frappe
			.xcall("hrms_addon.hrms_addon.talent_board.get_card", { employee, review: this.data.review.name })
			.then((card) => {
				if (this.picked !== employee) return;
				panel.html(card && card.allowed && card.employee ? hrms_addon.talent_card.render(card) : "");
			});
	}

	move(moving, box) {
		const cell = (this.data.board.cells || []).find((each) => each.box === box) || {};
		frappe.prompt(
			[{ fieldname: "reason", fieldtype: "Small Text", label: __("Why they move"), reqd: 1 }],
			(values) =>
				frappe
					.xcall("hrms_addon.hrms_addon.talent_board.move", {
						placement: moving.placement, to_box: box, reason: values.reason,
					})
					.then((result) => {
						frappe.show_alert({ message: __("{0} moved to {1}", [moving.name, `${result.box} · ${__(result.box_name)}`]), indicator: "green" });
						this.refresh();
					}),
			__("Move {0} to {1}", [moving.name, `${box} · ${__(cell.name || "")}`]),
			__("Move")
		);
	}

	actions(data) {
		(data.actions || []).forEach((action) => {
			this.page.add_inner_button(__(action), () => this.advance(action), __("Actions"));
		});
	}

	advance(action) {
		const returning = action === "Return" || action === "Return to Calibration";
		const go = (remarks) =>
			frappe
				.xcall("hrms_addon.hrms_addon.talent_board.advance", Object.assign({ action, remarks }, this.args(),
					{ review: this.data.review.name }))
				.then((result) => {
					const left = result.left || [];
					frappe.msgprint({
						title: __(action),
						indicator: left.length ? "orange" : "green",
						message: __("{0} placement(s) done.", [result.done]) + (left.length
							? "<br><br>" + __("Left as they were:") + "<ul>" + left.map(([who, why]) =>
								`<li>${frappe.utils.escape_html(who)}: ${frappe.utils.escape_html(why)}</li>`).join("") + "</ul>"
							: ""),
					});
					this.refresh();
				});
		if (returning) {
			frappe.prompt([{ fieldname: "remarks", fieldtype: "Small Text", label: __("What they must have before they come back"), reqd: 1 }],
				(values) => go(values.remarks), __(action), __(action));
		} else {
			frappe.confirm(__("{0} every placement on the board that is ready for it?", [__(action)]), () => go());
		}
	}
};
