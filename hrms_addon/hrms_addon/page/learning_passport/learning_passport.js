// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

/* The Learning Passport (learning.passport): one employee's learning on a page.
 *
 * Who they are, their light and Training & Competency Score, the hours of
 * training this year, what the rules require of them and how far they are,
 * their certificates, and the sessions they attended. An employee opens
 * their own; a supervisor their team's; HR and managers whoever they may
 * read, picked at the top. The server checks again (learning.can_see).
 *
 * The styles live in this file, as on the Talent Board, so the page never
 * waits on `bench build`.
 */

frappe.provide("hrms_addon");

const LP_LIGHT = {
	Compliant: "lp-green",
	"Due Soon": "lp-amber",
	Overdue: "lp-red",
	"Not Applicable": "lp-grey",
	Pending: "lp-blue",
	Valid: "lp-green",
	Expired: "lp-red",
	Renewed: "lp-grey",
	Revoked: "lp-grey",
};
// the order the required training is listed in: what needs doing first
const LP_ORDER = ["Overdue", "Due Soon", "Pending", "Compliant", "Not Applicable"];
const LP_PICKERS = ["HR User", "HR Manager", "System Manager", "General Manager", "Executive Director",
	"Head of Department", "Supervisor"];
const LP_RECOMMENDERS = ["HR User", "HR Manager", "System Manager", "Head of Department", "Supervisor"];

const LP_STYLE = `
.lp { padding: 4px 0 28px; color: var(--text-color); }
.lp-bar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
.lp-bar .lp-pick { width: 280px; max-width: 100%; }
.lp-bar .lp-pick .form-group { margin: 0; }
.lp-head { display: flex; gap: 14px; align-items: center; background: var(--card-bg); border: 1px solid var(--border-color);
  border-radius: 12px; padding: 14px; margin-bottom: 12px; }
.lp-av { width: 54px; height: 54px; border-radius: 50%; background: #14395E; color: #fff; font-weight: 600; font-size: 18px;
  display: flex; align-items: center; justify-content: center; flex: none; overflow: hidden; }
.lp-av img { width: 100%; height: 100%; object-fit: cover; }
.lp-name { font-size: 18px; font-weight: 600; }
.lp-sub { color: var(--text-muted); font-size: 12.5px; margin-top: 2px; }
.lp-facts { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px 16px; margin-left: auto; font-size: 12.5px; }
.lp-facts small { display: block; color: var(--text-muted); font-size: 11px; }
.lp-tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
.lp-tile { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 12px 14px; }
.lp-tile small { display: block; color: var(--text-muted); font-size: 11.5px; margin-bottom: 4px; }
.lp-tile b { font-size: 24px; font-weight: 600; }
.lp-tile b.lp-score { color: #B8860B; }
.lp-tile em { font-style: normal; color: var(--text-muted); font-size: 12px; margin-left: 4px; }
.lp-meter { height: 7px; border-radius: 4px; background: var(--control-bg); margin-top: 8px; overflow: hidden; }
.lp-meter span { display: block; height: 100%; border-radius: 4px; }
.lp-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 12px 14px;
  margin-bottom: 12px; }
.lp-card h4 { font-size: 14px; font-weight: 600; margin: 0 0 8px; display: flex; gap: 8px; align-items: center; }
.lp-card h4 .lp-count { color: var(--text-muted); font-weight: 400; font-size: 12px; }
.lp-card h4 .lp-right { margin-left: auto; font-weight: 400; font-size: 12px; }
.lp-scroll { overflow-x: auto; }
.lp-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.lp-table .lp-date { white-space: nowrap; }
.lp-table th { text-align: left; color: var(--text-muted); font-weight: 500; font-size: 11.5px; padding: 6px 8px;
  border-bottom: 1px solid var(--border-color); }
.lp-table td { padding: 7px 8px; border-bottom: 1px solid var(--border-color); vertical-align: top; }
.lp-table tr:last-child td { border-bottom: none; }
.lp-light { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
.lp-light::before { content: ""; width: 9px; height: 9px; border-radius: 50%; background: currentColor; flex: none; }
.lp-green { color: #1F7A4D; }
.lp-amber { color: #B7791F; }
.lp-red { color: #A62B25; }
.lp-grey { color: #6B7280; }
.lp-blue { color: #14395E; }
.lp-meter .lp-green { background: #1F7A4D; }
.lp-meter .lp-amber { background: #E8A317; }
.lp-meter .lp-red { background: #A62B25; }
.lp-muted { color: var(--text-muted); }
.lp-tag { border-radius: 6px; padding: 1px 6px; font-size: 11px; background: var(--control-bg); color: var(--text-muted); }
.lp-tag.lp-checked { background: #E3F1E8; color: #1F5C3C; }
.lp-tag.lp-refused { background: #F8DADA; color: #8C2323; }
.lp-empty { color: var(--text-muted); font-size: 12.5px; padding: 6px 0; }
.lp-link { cursor: pointer; text-decoration: underline; text-decoration-color: var(--border-color); }
.lp-more { cursor: pointer; font-size: 12px; color: var(--text-muted); text-decoration: underline; }
@media (max-width: 900px) {
  .lp-tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .lp-facts { grid-template-columns: repeat(2, minmax(0, 1fr)); margin-left: 0; }
  .lp-head { flex-wrap: wrap; }
}
@media print {
  .lp-bar, .page-head, .navbar { display: none !important; }
}
`;

frappe.pages["learning-passport"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Learning Passport"), single_column: true });
	wrapper.learning_passport = new hrms_addon.LearningPassport(page);
};

frappe.pages["learning-passport"].on_page_show = function (wrapper) {
	const asked = frappe.get_route()[1] || (frappe.route_options || {}).employee;
	frappe.route_options = null;
	wrapper.learning_passport && wrapper.learning_passport.show(asked);
};

hrms_addon.LearningPassport = class LearningPassport {
	constructor(page) {
		this.page = page;
		this.employee = null;
		this.show_all = false;
		if (!document.getElementById("lp-style")) {
			$("<style id='lp-style'>").text(LP_STYLE).appendTo(document.head);
		}
		this.$root = $("<div class='lp'><div class='lp-bar'></div><div class='lp-body'></div></div>").appendTo(page.main);
		this.$body = this.$root.find(".lp-body");
		this.make_bar();
	}

	has_any(roles) {
		return roles.some((role) => frappe.user.has_role(role));
	}

	make_bar() {
		const $bar = this.$root.find(".lp-bar");
		if (this.has_any(LP_PICKERS)) {
			const $pick = $("<div class='lp-pick'></div>").appendTo($bar);
			this.picker = frappe.ui.form.make_control({
				parent: $pick,
				df: {
					fieldtype: "Link",
					options: "Employee",
					fieldname: "employee",
					placeholder: __("Employee"),
					change: () => {
						const value = this.picker.get_value();
						if (value && value !== this.employee) {
							frappe.set_route("learning-passport", value);
						}
					},
				},
				render_input: true,
			});
		}
		this.page.add_inner_button(__("Print"), () => window.print());
		if (this.has_any(LP_RECOMMENDERS)) {
			this.page.add_inner_button(__("Recommend Training"), () => {
				if (this.employee) {
					frappe.new_doc("Employee Training Requirement", { employee: this.employee });
				}
			});
		}
		if (this.has_any(["HR User", "HR Manager", "System Manager"])) {
			this.page.add_inner_button(__("Add Certificate"), () => {
				if (this.employee) {
					frappe.new_doc("Employee Certification", { employee: this.employee });
				}
			});
		}
	}

	show(employee) {
		this.$body.html(`<div class="lp-empty">${__("Loading...")}</div>`);
		frappe
			.xcall("hrms_addon.hrms_addon.learning.passport", { employee: employee || null })
			.then((data) => this.render(data || {}))
			.catch(() => this.$body.html(`<div class="lp-empty">${__("This passport could not be opened.")}</div>`));
	}

	render(data) {
		if (!data.employee) {
			this.employee = null;
			this.$body.html(`<div class="lp-empty">${__("Pick an employee to see their passport.")}</div>`);
			return;
		}
		const e = data.employee;
		this.employee = e.name;
		this.data = data;
		if (this.picker && this.picker.get_value() !== e.name) {
			this.picker.set_value(e.name);
		}
		this.page.set_title(__("Learning Passport") + ": " + e.employee_name);
		this.$body.html(this.head(e) + this.tiles(data.figures) + this.required(data.requirements) +
			this.certificates(data.certificates) + this.history(data.history));
		this.$body.find("[data-open]").on("click", (event) => {
			const $el = $(event.currentTarget);
			frappe.set_route("Form", $el.attr("data-open"), $el.attr("data-name"));
		});
		this.$body.find(".lp-toggle").on("click", () => {
			this.show_all = !this.show_all;
			this.render(this.data);
		});
	}

	head(e) {
		const esc = frappe.utils.escape_html;
		const initials = (e.employee_name || "?").split(" ").filter(Boolean).slice(0, 2).map((part) => part[0]).join("");
		const avatar = e.image ? `<img src="${esc(e.image)}" alt="">` : esc(initials.toUpperCase());
		const fact = (label, value) => `<div><small>${label}</small>${esc(value || "–")}</div>`;
		return `<div class="lp-head">
			<div class="lp-av">${avatar}</div>
			<div><div class="lp-name">${esc(e.employee_name)}</div>
			<div class="lp-sub">${esc(e.employee_number || e.name)} · ${esc([e.branch, e.department, e.designation].filter(Boolean).join(" · "))}</div></div>
			<div class="lp-facts">
				${fact(__("Grade"), e.grade)}${fact(__("Employment Type"), e.employment_type)}
				${fact(__("Joined"), e.date_of_joining ? frappe.datetime.str_to_user(e.date_of_joining) : "")}
				${fact(__("Supervisor"), e.supervisor)}
			</div></div>`;
	}

	tiles(f) {
		const light = LP_LIGHT[f.light] || "lp-grey";
		const coverage = f.coverage === null || f.coverage === undefined ? null : Math.round(f.coverage);
		const band = coverage === null ? "" : coverage >= 90 ? "lp-green" : coverage >= 60 ? "lp-amber" : "lp-red";
		const meter = coverage === null ? "" : `<div class="lp-meter"><span class="${band}" style="width:${coverage}%"></span></div>`;
		return `<div class="lp-tiles">
			<div class="lp-tile"><small>${__("Training & Competency Score")}</small>
				<b class="lp-score">${f.score === null || f.score === undefined ? "–" : f.score}</b>
				${f.assessment === null || f.assessment === undefined ? "" : `<em>${__("assessments {0}%", [Math.round(f.assessment)])}</em>`}</div>
			<div class="lp-tile"><small>${__("Status")}</small><b class="lp-light ${light}" style="font-size:16px">${__(f.light)}</b>
				<div class="lp-sub">${f.overdue ? __("{0} overdue", [f.overdue]) + " · " : ""}${f.due_soon ? __("{0} due soon", [f.due_soon]) : ""}</div></div>
			<div class="lp-tile"><small>${__("Training Hours in {0}", [f.year])}</small><b>${f.hours || 0}</b>
				<em>${__("{0} session(s)", [f.sessions || 0])}</em></div>
			<div class="lp-tile"><small>${__("Required Training Done")}</small><b>${f.done}</b><em>${__("of {0}", [f.required])}</em>${meter}</div>
		</div>`;
	}

	required(rows) {
		const esc = frappe.utils.escape_html;
		const hidden = rows.filter((row) => row.status === "Not Applicable").length;
		const shown = rows
			.filter((row) => this.show_all || row.status !== "Not Applicable")
			.sort((a, b) => LP_ORDER.indexOf(a.status) - LP_ORDER.indexOf(b.status) || String(a.due_date || "").localeCompare(String(b.due_date || "")));
		const date = (value) => (value ? frappe.datetime.str_to_user(value) : "–");
		const toggle = hidden ? `<span class="lp-right lp-more lp-toggle">${this.show_all ? __("Hide not applicable") : __("Show {0} not applicable", [hidden])}</span>` : "";
		const body = shown.length
			? `<div class="lp-scroll"><table class="lp-table"><thead><tr><th>${__("Status")}</th><th>${__("Training")}</th><th>${__("Category")}</th>
				<th>${__("Why")}</th><th>${__("Due")}</th><th>${__("Last Done")}</th><th>${__("Counts Until")}</th><th>${__("Last Result")}</th></tr></thead><tbody>
				${shown.map((row) => `<tr>
					<td><span class="lp-light ${LP_LIGHT[row.status] || "lp-grey"}">${__(row.status)}</span></td>
					<td>${this.open("Employee Training Requirement", row.name, row.training_program || row.certification)}</td>
					<td>${esc(row.training_category || "–")}</td>
					<td class="lp-muted">${esc(row.training_rule ? row.requirement_type : __("Recommended"))}</td>
					<td class="lp-date">${date(row.due_date)}</td><td class="lp-date">${date(row.completed_on)}</td><td class="lp-date">${row.completed_on ? (row.valid_until ? date(row.valid_until) : __("For good")) : "–"}</td>
					<td class="lp-muted">${esc(row.last_result || "")}</td></tr>`).join("")}</tbody></table></div>`
			: `<div class="lp-empty">${__("Nothing is required of them yet.")}</div>`;
		return `<div class="lp-card"><h4>${__("Required Training")}<span class="lp-count">${shown.length}</span>${toggle}</h4>${body}</div>`;
	}

	certificates(rows) {
		const esc = frappe.utils.escape_html;
		const date = (value) => (value ? frappe.datetime.str_to_user(value) : "–");
		const left = (row) => {
			if (row.days_to_expiry === null || row.days_to_expiry === undefined) {
				return row.expiry_date ? "" : __("Does not expire");
			}
			return row.days_to_expiry < 0 ? __("{0} day(s) ago", [-row.days_to_expiry]) : __("{0} day(s) left", [row.days_to_expiry]);
		};
		const check = { Verified: "lp-checked", Rejected: "lp-refused" };
		const body = rows.length
			? `<div class="lp-scroll"><table class="lp-table"><thead><tr><th>${__("Status")}</th><th>${__("Certificate")}</th><th>${__("Number")}</th>
				<th>${__("Issued By")}</th><th>${__("Issued")}</th><th>${__("Expires")}</th><th>${__("Time Left")}</th><th>${__("Checked")}</th></tr></thead><tbody>
				${rows.map((row) => `<tr>
					<td><span class="lp-light ${LP_LIGHT[row.status] || "lp-grey"}">${__(row.status || "")}</span></td>
					<td>${this.open("Employee Certification", row.name, row.certification)}</td>
					<td>${esc(row.certificate_no || "–")}</td><td>${esc(row.issuing_body || "–")}</td>
					<td class="lp-date">${date(row.issue_date)}</td><td class="lp-date">${date(row.expiry_date)}</td><td class="lp-muted">${left(row)}</td>
					<td><span class="lp-tag ${check[row.verification_status] || ""}">${__(row.verification_status || "Unverified")}</span></td></tr>`).join("")}</tbody></table></div>`
			: `<div class="lp-empty">${__("No certificates on file.")}</div>`;
		return `<div class="lp-card"><h4>${__("Certificates")}<span class="lp-count">${rows.length}</span></h4>${body}</div>`;
	}

	history(rows) {
		const esc = frappe.utils.escape_html;
		const body = rows.length
			? `<div class="lp-scroll"><table class="lp-table"><thead><tr><th>${__("Date")}</th><th>${__("Training")}</th><th>${__("Session")}</th>
				<th>${__("Hours")}</th><th>${__("Marks")}</th><th>${__("Result")}</th></tr></thead><tbody>
				${rows.map((row) => `<tr><td class="lp-date">${row.day ? frappe.datetime.str_to_user(row.day) : "–"}</td>
					<td>${esc(row.training_program || "–")}</td><td>${this.open("Training Event", row.event, row.event_name || row.event)}</td>
					<td>${row.hours || 0}</td><td>${row.marks === null || row.marks === undefined ? "–" : row.marks}</td>
					<td class="lp-muted">${esc(row.effective || "")}</td></tr>`).join("")}</tbody></table></div>`
			: `<div class="lp-empty">${__("No training attended yet.")}</div>`;
		return `<div class="lp-card"><h4>${__("Training Attended")}<span class="lp-count">${rows.length}</span></h4>${body}</div>`;
	}

	open(doctype, name, label) {
		const esc = frappe.utils.escape_html;
		if (name && frappe.model.can_read(doctype)) {
			return `<span class="lp-link" data-open="${esc(doctype)}" data-name="${esc(name)}">${esc(label || name)}</span>`;
		}
		return esc(label || name || "–");
	}
};
