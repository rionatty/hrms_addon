// HRMS Addon — the talent card (talent_board.get_card).
//
// One employee's talent at a glance: where they sit on the nine-box and
// why, the year as their appraisals hold it, the potential and the
// competency evidence, the box over the years, the benches they are on,
// their development plan, flight risk and improvement plan. Drawn on the
// Talent Board beside the grid, and as a section of the Employee and the
// Appraisal forms for those who may see the boxes (HR and the Talent
// Council); for anybody else the server answers allowed: 0 and nothing is
// drawn. Loaded on every desk page (hooks.py app_include_js), so the board
// and both forms draw it the same way.

(function () {
	frappe.provide("hrms_addon.talent_card");

	// the nine-box colours: background, ink
	const TINTS = {
		Red: ["#F8DADA", "#8C2323"],
		Orange: ["#FCE5D2", "#8A4A12"],
		Yellow: ["#FBF1D3", "#6B4F00"],
		Blue: ["#DCE8F7", "#14395E"],
		Green: ["#D7F0DC", "#1E6B34"],
	};
	const STYLE = `
.ha-tc { font-size: 12.5px; color: var(--text-color); line-height: 1.4; }
.ha-tc-head { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; }
.ha-tc-avatar { width: 40px; height: 40px; border-radius: 50%; flex: none; background: #14395E; color: #fff;
  display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 14px; overflow: hidden; }
.ha-tc-avatar img { width: 100%; height: 100%; object-fit: cover; }
.ha-tc-name { font-weight: 600; font-size: 14px; }
.ha-tc-sub { color: var(--text-muted); font-size: 12px; }
.ha-tc-box { border-radius: 8px; padding: 7px 10px; margin-bottom: 10px; font-weight: 600; }
.ha-tc-box span { font-weight: 400; }
.ha-tc-none { border-radius: 8px; padding: 7px 10px; margin-bottom: 10px; background: var(--control-bg);
  color: var(--text-muted); }
.ha-tc-row { display: flex; justify-content: space-between; gap: 10px; padding: 6px 0;
  border-top: 1px solid var(--border-color); }
.ha-tc-row > span:first-child { color: var(--text-muted); flex: none; }
.ha-tc-row > span:last-child { text-align: right; min-width: 0; }
.ha-tc-label { color: var(--text-muted); padding: 8px 0 4px; border-top: 1px solid var(--border-color); }
.ha-tc-bar { display: grid; grid-template-columns: minmax(0, 1fr) 90px 28px; gap: 8px; align-items: center;
  padding: 2px 0; }
.ha-tc-bar em { font-style: normal; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ha-tc-bar i { display: block; height: 6px; border-radius: 3px; background: var(--border-color); overflow: hidden; }
.ha-tc-bar i b { display: block; height: 100%; background: #14395E; border-radius: 3px; }
.ha-tc-bar s { text-decoration: none; text-align: right; font-weight: 600; }
.ha-tc-quarters { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.ha-tc-quarters a { border: 1px solid var(--border-color); border-radius: 6px; padding: 1px 6px; color: inherit; }
.ha-tc-red { color: #A62B25; font-weight: 600; }
.ha-tc-amber { color: #B45309; font-weight: 600; }
.ha-tc-progress { height: 6px; border-radius: 3px; background: var(--border-color); margin-top: 5px; overflow: hidden; }
.ha-tc-progress b { display: block; height: 100%; background: #E8A317; }
.ha-tc-links { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
.ha-tc-links a { border: 1px solid var(--border-color); border-radius: 6px; padding: 3px 9px; color: inherit; }
html[data-theme="dark"] .ha-tc-bar i b { background: #5B8FC7; }
`;

	hrms_addon.talent_card.tints = TINTS;

	hrms_addon.talent_card.style = function () {
		if (!document.getElementById("ha-talent-card-style")) {
			$('<style id="ha-talent-card-style"></style>').text(STYLE).appendTo("head");
		}
	};

	hrms_addon.talent_card.initials = function (name) {
		return String(name || "?")
			.split(/\s+/)
			.filter(Boolean)
			.slice(0, 2)
			.map((word) => word[0].toUpperCase())
			.join("");
	};

	function number(value, places) {
		if (value === undefined || value === null || value === "") return "";
		return format_number(value, null, places === undefined ? 0 : places);
	}

	function link(doctype, name, text) {
		if (!name) return "";
		const route = `/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}`;
		return `<a href="${route}">${frappe.utils.escape_html(text || name)}</a>`;
	}

	// The card as HTML, from what talent_board.get_card returns.
	hrms_addon.talent_card.render = function (card) {
		const esc = frappe.utils.escape_html;
		const person = (card && card.employee) || {};
		const placed = (card && card.placement) || null;
		const avatar = person.image
			? `<img src="${esc(person.image)}" alt="">`
			: esc(hrms_addon.talent_card.initials(person.employee_name));
		const where = [person.designation, person.branch].filter(Boolean).map(esc).join(" · ");
		let html = `<div class="ha-tc"><div class="ha-tc-head"><div class="ha-tc-avatar">${avatar}</div>
			<div><div class="ha-tc-name">${esc(person.employee_name || person.name || "")}</div>
			<div class="ha-tc-sub">${where}</div></div></div>`;
		if (placed && placed.box) {
			const tint = TINTS[placed.colour] || ["var(--control-bg)", "var(--text-color)"];
			html += `<div class="ha-tc-box" style="background:${tint[0]};color:${tint[1]}">${placed.box} · ${esc(
				__(placed.box_name || "")
			)} <span>· ${esc(__(placed.action || ""))}</span></div>`;
		} else if (placed) {
			html += `<div class="ha-tc-none">${esc(
				placed.performance === null || placed.performance === undefined
					? __("No completed appraisal this year yet")
					: __("Potential not rated yet")
			)} · ${esc(__(placed.state))}</div>`;
		} else {
			html += `<div class="ha-tc-none">${esc(__("Not in a talent review"))}</div>`;
		}
		const row = (label, value) => (value ? `<div class="ha-tc-row"><span>${esc(label)}</span><span>${value}</span></div>` : "");
		if (placed) {
			const band = placed.performance_band ? ` · ${esc(__(placed.performance_band))}` : "";
			const rating = placed.appraisal_band ? ` <span class="text-muted">(${esc(__(placed.appraisal_band))})</span>` : "";
			html += row(__("Performance, year to date"), placed.performance !== null && placed.performance !== undefined
				? `${number(placed.performance, 1)}${band}${rating}` : "");
			if ((placed.quarters || []).length) {
				html += row(__("Quarters"), `<span class="ha-tc-quarters">${placed.quarters
					.map((q) => `<a href="/app/appraisal/${encodeURIComponent(q.appraisal)}">${esc(q.quarter)} ${number(q.total)}</a>`)
					.join("")}</span>`);
			}
			let potential = "";
			if (placed.potential !== null && placed.potential !== undefined) {
				potential = `${number(placed.potential)} · ${esc(__(placed.potential_band || ""))}`;
				if (placed.calibrated_potential) {
					potential += ` <span class="ha-tc-amber">→ ${esc(__(placed.calibrated_potential))}</span>`;
				}
			}
			html += row(__("Potential"), potential);
			const dims = placed.dimensions || {};
			if (["ability", "aspiration", "engagement"].some((name) => dims[name] !== null && dims[name] !== undefined)) {
				html += row(__("Ability, aspiration, engagement"),
					["ability", "aspiration", "engagement"].map((name) => number(dims[name], 1) || "–").join(" · "));
			}
			if ((placed.competencies || []).length) {
				html += `<div class="ha-tc-label">${esc(__("Competencies, from the appraisals"))}</div>`;
				html += placed.competencies
					.map((c) => `<div class="ha-tc-bar"><em title="${esc(c.competency)}">${esc(c.competency)}</em>
						<i><b style="width:${Math.max(0, Math.min(100, (c.level || 0) * 10))}%"></b></i><s>${number(c.level, 1)}</s></div>`)
					.join("");
			}
			if (placed.flight_risk) {
				const tone = placed.flight_risk === "High" ? "ha-tc-red" : placed.flight_risk === "Medium" ? "ha-tc-amber" : "";
				html += row(__("Flight risk"), `<span class="${tone}">${esc(__(placed.flight_risk))}</span>${
					placed.impact_of_loss ? ` <span class="text-muted">· ${esc(__("impact {0}", [__(placed.impact_of_loss).toLowerCase()]))}</span>` : ""}`);
			}
			if (placed.management_decision) {
				html += row(__("Management's decision"), esc(__(placed.management_decision)));
			}
		}
		if (card && card.improvement_plan) {
			html += row(__("Improvement plan"), `<span class="ha-tc-red">${link("Performance Improvement Plan", card.improvement_plan)}</span>`);
		}
		if ((card && card.history || []).length) {
			html += row(__("Box over the years"), card.history
				.map((h) => `${esc(String(h.year || ""))}: ${h.box || "–"}`)
				.join(" · "));
		}
		(card && card.successor_for || []).forEach((s) => {
			html += row(__("Successor for"), `${link("Succession Position", s.position, s.role || s.position)} · ${esc(__(s.readiness || ""))}`);
		});
		(card && card.holds || []).forEach((h) => {
			html += row(__("Holds a critical role"), `${link("Succession Position", h.name, h.designation)} · ${esc(__(h.coverage || ""))}`);
		});
		if (card && card.plan) {
			const plan = card.plan;
			const share = plan.actions ? Math.round((100 * plan.completed) / plan.actions) : 0;
			html += `<div class="ha-tc-row" style="display:block"><div style="display:flex;justify-content:space-between;gap:10px">
				<span class="text-muted">${esc(__("Development plan"))}</span>
				<span>${link("Talent Program", plan.name, __(plan.program_type))} · ${esc(__("{0} of {1} done", [plan.completed, plan.actions]))}</span></div>
				<div class="ha-tc-progress"><b style="width:${share}%"></b></div></div>`;
		}
		if (card && card.trainee) {
			html += row(__("Graduate trainee"), `${link("Graduate Trainee Program", card.trainee.name, card.trainee.cohort)} · ${esc(__(card.trainee.workflow_state || ""))}`);
		}
		const links = [];
		if (placed) links.push(link("Talent Placement", placed.name, __("Open placement")));
		if (placed && placed.appraisal) links.push(link("Appraisal", placed.appraisal, __("Latest appraisal")));
		if (person.name) links.push(link("Employee", person.name, __("Employee")));
		html += `<div class="ha-tc-links">${links.join("")}</div></div>`;
		return html;
	};

	// The card as a section of a form, for those who may see it.
	hrms_addon.talent_card.attach = function (frm, employee) {
		if (!employee || frm.is_new() || !frm.dashboard) return;
		hrms_addon.talent_card.style();
		frappe
			.xcall("hrms_addon.hrms_addon.talent_board.get_card", { employee: employee })
			.then((card) => {
				if (!card || !card.allowed || !card.employee || frm.doc.name === undefined) return;
				if (!card.placement && !card.plan && !(card.history || []).length && !card.trainee
					&& !(card.successor_for || []).length) {
					return;
				}
				frm.$wrapper.find(".form-dashboard-section.ha-talent").remove();
				frm.dashboard.add_section(hrms_addon.talent_card.render(card), __("Talent"), "custom ha-talent");
			})
			.catch(() => {});
	};
})();
