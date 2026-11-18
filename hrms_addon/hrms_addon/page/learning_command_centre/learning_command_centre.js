// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

/* The Learning Command Centre (learning_centre.centre): the company's, a
 * plant's or a department's learning on one page (figures that open their
 * reports, the Learning Health Score and its nine parts, the plants side by
 * side, twelve months of trends, certificates running out and the insights),
 * a supervisor's team, or the employee's own learning. The server decides
 * what each user may see.
 */

frappe.provide("hrms_addon");

const LCC_STYLE = `
.lcc { padding: 4px 0 28px; color: var(--text-color); }
.lcc-bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: flex-end; margin-bottom: 12px; }
.lcc-bar .lcc-field { width: 190px; } .lcc-bar .form-group { margin: 0; }
.lcc-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
.lcc-tile { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 12px 14px; cursor: pointer; }
.lcc-tile small { display: block; color: var(--text-muted); font-size: 11.5px; margin-bottom: 4px; }
.lcc-tile b { font-size: 22px; font-weight: 600; } .lcc-tile em { font-style: normal; color: var(--text-muted); font-size: 11.5px; display: block; }
.lcc-row { display: grid; grid-template-columns: 1fr 2fr; gap: 12px; margin-bottom: 12px; }
.lcc-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 12px 14px; margin-bottom: 12px; min-width: 0; }
.lcc-card h4 { font-size: 14px; font-weight: 600; margin: 0 0 8px; }
.lcc-score { font-size: 40px; font-weight: 700; color: #B8860B; } .lcc-sub { color: var(--text-muted); font-size: 12px; }
.lcc-part { margin: 6px 0; font-size: 12px; } .lcc-part span { float: right; }
.lcc-meter { height: 6px; border-radius: 3px; background: var(--control-bg); overflow: hidden; margin-top: 3px; }
.lcc-meter i { display: block; height: 100%; }
.lcc-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.lcc-table th { text-align: left; color: var(--text-muted); font-weight: 500; font-size: 11.5px; padding: 6px 8px; border-bottom: 1px solid var(--border-color); }
.lcc-table td { padding: 6px 8px; border-bottom: 1px solid var(--border-color); }
.lcc-pill { border-radius: 10px; padding: 1px 8px; font-size: 11px; white-space: nowrap; }
.lcc-High, .lcc-red { background: #F8DADA; color: #8C2323; } .lcc-Medium, .lcc-amber { background: #FCEBC8; color: #7A4F08; }
.lcc-Low, .lcc-grey { background: var(--control-bg); color: var(--text-muted); } .lcc-green { background: #E3F1E8; color: #1F5C3C; }
.lcc-link { cursor: pointer; text-decoration: underline; text-decoration-color: var(--border-color); }
.lcc-empty { color: var(--text-muted); font-size: 12.5px; padding: 6px 0; }
.lcc-scroll { overflow-x: auto; }
@media (max-width: 900px) { .lcc-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .lcc-row { grid-template-columns: 1fr; } }
`;
const LCC_PARTS = [["mandatory", "Mandatory Compliance"], ["certification", "Certification Compliance"], ["coverage", "Training Coverage"],
	["competency", "Competency Coverage"], ["attendance", "Attendance"], ["assessment", "Assessment Performance"],
	["effectiveness", "Training Effectiveness"], ["budget_use", "Budget Utilisation"], ["critical", "Critical Skills Coverage"]];
const LCC_METHOD = "hrms_addon.hrms_addon.learning_centre.";

frappe.pages["learning-command-centre"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Learning Command Centre"), single_column: true });
	wrapper.learning_centre = new hrms_addon.LearningCentre(page);
};

frappe.pages["learning-command-centre"].on_page_show = function (wrapper) {
	wrapper.learning_centre && wrapper.learning_centre.load();
};

hrms_addon.LearningCentre = class LearningCentre {
	constructor(page) {
		this.page = page;
		if (!document.getElementById("lcc-style")) $("<style id='lcc-style'>").text(LCC_STYLE).appendTo(document.head);
		this.$root = $(`<div class="lcc"><div class="lcc-bar"></div><div class="lcc-body"></div></div>`).appendTo(page.main);
		this.$body = this.$root.find(".lcc-body");
		const $bar = this.$root.find(".lcc-bar");
		const make = (df) => frappe.ui.form.make_control({ parent: $("<div class='lcc-field'>").appendTo($bar),
			df: Object.assign({ change: () => this.load() }, df), render_input: true });
		const manager = frappe.user.has_role(["HR User", "HR Manager", "System Manager", "General Manager", "Executive Director",
			"Management Viewer", "Auditor", "Head of Department", "Supervisor"]);
		if (manager) {
			this.view = make({ fieldtype: "Select", fieldname: "view", label: __("View"),
				options: ["", "Company", "Plant", "Department", "My Team", "My Learning"].join("\n") });
			this.company = make({ fieldtype: "Link", options: "Company", fieldname: "company", label: __("Company") });
			this.branch = make({ fieldtype: "Link", options: "Branch", fieldname: "branch", label: __("Plant") });
			this.month = make({ fieldtype: "Date", fieldname: "month", label: __("Month") });
			page.add_inner_button(__("PowerPoint"), () => window.open(frappe.urllib.get_full_url("/api/method/" + LCC_METHOD +
				"download_deck?" + $.param({ company: this.value("company") || "", month: this.value("month") || "", branch: this.value("branch") || "" }))));
			page.add_inner_button(__("Print"), () => this.print());
		}
	}

	value(name) {
		return this[name] ? this[name].get_value() : null;
	}

	load() {
		this.$body.html(`<div class="lcc-empty">${__("Loading...")}</div>`);
		frappe
			.xcall(LCC_METHOD + "centre", { company: this.value("company") || null, branch: this.value("branch") || null,
				month: this.value("month") || null, view: this.value("view") || null })
			.then((data) => this.render(data || {}))
			.catch(() => this.$body.html(`<div class="lcc-empty">${__("This view could not be opened.")}</div>`));
	}

	print() {
		frappe.xcall(LCC_METHOD + "build_now", { company: this.value("company") || null, month: this.value("month") || null }, "POST")
			.then((name) => window.open(frappe.urllib.get_full_url("/printview?" + $.param({ doctype: "Learning Snapshot", name: name,
				format: "Learning Snapshot Summary", no_letterhead: 0 }))));
	}

	render(data) {
		this.data = data;
		this.page.set_title(data.view === "My Learning" ? __("My Learning") : data.view === "My Team" ? __("My Team")
			: __("Learning Command Centre"));
		if (data.view === "My Learning") return this.render_mine(data);
		if (data.view === "My Team") return this.render_team(data);
		const f = data.figures || {};
		const pct = (value) => (value === null || value === undefined ? "–" : `${value}%`);
		const num = (value) => (value === null || value === undefined ? "–" : format_number(value, null, 0));
		const branch = this.value("branch") || "";
		const tiles = [
			[__("Required Training Done"), pct(f.compliance), __("{0} overdue", [f.overdue]), ["query-report", "Training Compliance", { branch }]],
			[__("Mandatory Compliance"), pct(f.mandatory), "", ["query-report", "Training Matrix", { branch }]],
			[__("Certificates Valid"), pct(f.certification), __("{0} run out, {1} expiring", [f.expired, f.expiring]), ["query-report", "Certification Expiry", { branch }]],
			[__("Trained in 12 Months"), pct(f.coverage), __("{0} of {1} employees", [f.trained, f.headcount]), ["query-report", "Session Attendance", { branch, view: "Plant" }]],
			[__("Training Hours This Month"), num(f.hours), __("attendance {0}", [pct(f.attendance)]), ["query-report", "Session Attendance", { branch }]],
			[__("Assessment Pass Rate"), pct(f.pass_rate), "", ["query-report", "Training Effectiveness", { branch }]],
			[__("Spend This Month"), num(f.spend), __("{0} of the month's budget", [pct(f.budget_used)]), ["query-report", "Training Budget vs Actual", { branch }]],
			[__("Competency Coverage"), pct(f.competency), "", ["query-report", "Skills Cover", { branch }]],
		];
		this.$body.html(`<div class="lcc-grid">${tiles.map((tile, index) => `<div class="lcc-tile" data-tile="${index}">
			<small>${tile[0]}</small><b>${tile[1]}</b><em>${tile[2] || "&nbsp;"}</em></div>`).join("")}</div>
			<div class="lcc-row"><div class="lcc-card">${this.health(data.health || {})}</div>
			<div class="lcc-card"><h4>${__("Insights")}</h4>${this.insights(data.insights || [])}</div></div>
			<div class="lcc-row"><div class="lcc-card"><h4>${__("Certificates Running Out")}</h4>${this.alerts(data.alerts || [])}</div>
			<div class="lcc-card"><h4>${__("Plants Side by Side")}</h4><div class="lcc-plants-chart"></div>${this.plants(data.plants || [])}</div></div>
			<div class="lcc-card"><h4>${__("Twelve Months")}</h4><div class="lcc-trend"></div></div>
			<div class="lcc-card"><h4>${__("Departments")}</h4>${this.departments(data.departments || [])}</div>`);
		this.$body.find("[data-tile]").on("click", (event) => {
			const route = tiles[$(event.currentTarget).attr("data-tile")][3];
			frappe.route_options = route[2];
			frappe.set_route(route[0], route[1]);
		});
		this.$body.find("[data-insight]").on("click", (event) => {
			const item = (data.insights || [])[$(event.currentTarget).attr("data-insight")];
			frappe.route_options = item.filters || {};
			frappe.set_route(...item.route);
		});
		this.charts(data);
	}

	health(h) {
		const parts = h.parts || {};
		const colour = (value) => (value >= 85 ? "#1F7A4D" : value >= 65 ? "#E8A317" : "#A62B25");
		return `<h4>${__("Learning Health Score")}</h4><div class="lcc-score">${h.score === null || h.score === undefined ? "–" : h.score + "%"}</div>
			<div class="lcc-sub">${__(h.status || "")}</div>${LCC_PARTS.map(([key, label]) => {
				const value = parts[key];
				return `<div class="lcc-part">${__(label)}<span>${value === null || value === undefined ? "–" : value + "%"}</span>
					<div class="lcc-meter"><i style="width:${value || 0}%;background:${colour(value || 0)}"></i></div></div>`;
			}).join("")}`;
	}

	insights(items) {
		const esc = frappe.utils.escape_html;
		return items.length
			? `<table class="lcc-table"><tbody>${items.slice(0, 15).map((item, index) => `<tr><td><span class="lcc-pill lcc-${item.severity}">${__(item.severity)}</span></td>
				<td><span class="lcc-link" data-insight="${index}">${esc(item.text)}</span></td></tr>`).join("")}</tbody></table>`
			: `<div class="lcc-empty">${__("Nothing stands out.")}</div>`;
	}

	alerts(rows) {
		const esc = frappe.utils.escape_html;
		return rows.length
			? `<table class="lcc-table"><tbody>${rows.map((row) => `<tr><td><a href="/app/employee-certification/${encodeURIComponent(row.name)}">${esc(row.employee_name || row.employee)}</a>
				<div class="lcc-sub">${esc(row.certification)} · ${esc(row.branch || "")}</div></td>
				<td><span class="lcc-pill ${row.days_left < 0 ? "lcc-red" : row.days_left <= 30 ? "lcc-red" : "lcc-amber"}">${row.days_left < 0
					? __("{0} days over", [-row.days_left]) : __("{0} days", [row.days_left])}</span></td></tr>`).join("")}</tbody></table>`
			: `<div class="lcc-empty">${__("None running out.")}</div>`;
	}

	plants(rows) {
		const esc = frappe.utils.escape_html;
		const pct = (value) => (value === null || value === undefined ? "–" : value + "%");
		return `<div class="lcc-scroll"><table class="lcc-table"><thead><tr><th>${__("Plant")}</th><th>${__("Health")}</th><th>${__("Done")}</th>
			<th>${__("Mandatory")}</th><th>${__("Certificates")}</th><th>${__("Trained")}</th><th>${__("Hours")}</th><th>${__("Spend")}</th><th>${__("Overdue")}</th></tr></thead>
			<tbody>${rows.map((row) => `<tr><td>${esc(row.branch)}</td><td>${pct(row.health)}</td><td>${pct(row.compliance)}</td><td>${pct(row.mandatory)}</td>
			<td>${pct(row.certification)}</td><td>${pct(row.coverage)}</td><td>${row.hours}</td><td>${format_number(row.spend, null, 0)}</td><td>${row.overdue}</td></tr>`).join("")}</tbody></table></div>`;
	}

	departments(rows) {
		const esc = frappe.utils.escape_html;
		const pct = (value) => (value === null || value === undefined ? "–" : value + "%");
		return rows.length
			? `<div class="lcc-scroll"><table class="lcc-table"><thead><tr><th>${__("Plant")}</th><th>${__("Department")}</th><th>${__("People")}</th>
				<th>${__("Health")}</th><th>${__("Done")}</th><th>${__("Overdue")}</th><th>${__("Certificates")}</th></tr></thead><tbody>${rows
					.sort((a, b) => (a.compliance ?? 101) - (b.compliance ?? 101)).map((row) => `<tr><td>${esc(row.branch)}</td><td>${esc(row.department)}</td>
				<td>${row.headcount}</td><td>${pct(row.health)}</td><td>${pct(row.compliance)}</td><td>${row.overdue}</td><td>${pct(row.certification)}</td></tr>`).join("")}</tbody></table></div>`
			: `<div class="lcc-empty">${__("No departments.")}</div>`;
	}

	charts(data) {
		const plants = data.plants || [];
		if (plants.length && frappe.Chart) {
			new frappe.Chart(this.$body.find(".lcc-plants-chart")[0], { type: "bar", height: 200, colors: ["#14395E", "#E8A317"],
				data: { labels: plants.map((row) => row.branch), datasets: [
					{ name: __("Done %"), values: plants.map((row) => row.compliance || 0) },
					{ name: __("Health"), values: plants.map((row) => row.health || 0) }] } });
		}
		const months = data.trends || [];
		if (months.length && frappe.Chart) {
			new frappe.Chart(this.$body.find(".lcc-trend")[0], { type: "line", height: 220, colors: ["#14395E", "#1F7A4D", "#E8A317"],
				data: { labels: months.map((row) => row.month), datasets: [
					{ name: __("Done %"), values: months.map((row) => row.compliance || 0) },
					{ name: __("Certificates %"), values: months.map((row) => row.certification || 0) },
					{ name: __("Health"), values: months.map((row) => row.health || 0) }] } });
		} else {
			this.$body.find(".lcc-trend").html(`<div class="lcc-empty">${__("The trend fills as months are kept.")}</div>`);
		}
	}

	render_team(data) {
		const esc = frappe.utils.escape_html;
		const table = (head, rows) => rows.length
			? `<div class="lcc-scroll"><table class="lcc-table"><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows
				.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
			: `<div class="lcc-empty">${__("None.")}</div>`;
		const team = data.team || [];
		const skills = [...new Set((data.skills || []).map((row) => row.skill))];
		const level = {};
		(data.skills || []).forEach((row) => (level[row.employee + "\u0001" + row.skill] = String(row.level || "").split(" ")[0]));
		this.$body.html(`<div class="lcc-card"><h4>${__("My Team's Training")}</h4>${table([__("Employee"), __("Required"), __("Done %"), __("Overdue"), __("Due Soon")],
				team.map((row) => [`<a href="/app/learning-passport/${encodeURIComponent(row.name)}">${esc(row.employee_name)}</a>`, row.required,
					row.compliance === null ? "–" : row.compliance + "%", row.overdue, row.due_soon]))}</div>
			<div class="lcc-row"><div class="lcc-card"><h4>${__("Waiting on Me")}</h4>${table([__("Review Sheet"), __("Training"), __("Due")],
				(data.waiting || []).map((row) => [`<a href="/app/application-review-sheet/${encodeURIComponent(row.name)}">${esc(row.name)}</a>`,
					esc(row.training_program || ""), row.due_on ? frappe.datetime.str_to_user(row.due_on) : ""]))}</div>
			<div class="lcc-card"><h4>${__("Sessions Coming Up")}</h4>${table([__("Employee"), __("Session"), __("When"), __("As")],
				(data.upcoming || []).map((row) => [esc(row.employee_name), esc(row.event_name || row.name),
					frappe.datetime.str_to_user(row.start_time), __(row.place)]))}</div></div>
			<div class="lcc-row"><div class="lcc-card"><h4>${__("Certificates Running Out")}</h4>${table([__("Employee"), __("Certificate"), __("Expires")],
				(data.certificates || []).map((row) => [esc(row.employee_name), esc(row.certification), row.expiry_date ? frappe.datetime.str_to_user(row.expiry_date) : ""]))}</div>
			<div class="lcc-card"><h4>${__("Missing Competencies")}</h4>${table([__("Employee"), __("Skill"), __("Level"), __("Needed"), __("Status")],
				(data.gaps || []).map((row) => [esc(row.employee_name), esc(row.skill), esc(String(row.level || "").split(" ")[0]),
					esc(String(row.required_level || "").split(" ")[0]), __(row.status)]))}</div></div>
			<div class="lcc-card"><h4>${__("Team Skills")}</h4>${table([__("Employee")].concat(skills.map(esc)),
				team.map((row) => [esc(row.employee_name)].concat(skills.map((skill) => level[row.name + "\u0001" + skill] || ""))))}</div>
			<div class="lcc-card"><h4>${__("Development Needs")}</h4>${table([__("Employee"), __("Training"), __("Due"), __("Status")],
				(data.needs || []).map((row) => [esc(row.employee_name), esc(row.training_program || ""),
					row.due_date ? frappe.datetime.str_to_user(row.due_date) : "", __(row.status)]))}</div>`);
	}

	render_mine(data) {
		if (!data.employee) {
			this.$body.html(`<div class="lcc-empty">${__("Your user is not linked to an employee.")}</div>`);
			return;
		}
		const esc = frappe.utils.escape_html;
		const f = data.figures || {};
		const table = (head, rows) => rows.length
			? `<div class="lcc-scroll"><table class="lcc-table"><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows
				.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
			: `<div class="lcc-empty">${__("None.")}</div>`;
		const date = (value) => (value ? frappe.datetime.str_to_user(value) : "");
		this.$body.html(`<div class="lcc-grid">
			<div class="lcc-tile"><small>${__("My Status")}</small><b>${__(f.light || "")}</b><em>${__("{0} of {1} done", [f.done, f.required])}</em></div>
			<div class="lcc-tile"><small>${__("Training & Competency Score")}</small><b>${f.score ?? "–"}</b><em>&nbsp;</em></div>
			<div class="lcc-tile"><small>${__("Training Hours in {0}", [f.year])}</small><b>${f.hours || 0}</b><em>${__("CPD {0} hours", [f.cpd_hours || 0])}</em></div>
			<div class="lcc-tile" data-open-passport="1"><small>${__("My Learning Passport")}</small><b>${__("Open")}</b><em>${__("and print my transcript")}</em></div></div>
			<div class="lcc-card"><h4>${__("My Mandatory and Required Training")}</h4>${table([__("Status"), __("Training"), __("Due"), __("Booked")],
				(data.requirements || []).filter((row) => row.status !== "Not Applicable").map((row) => [__(row.status),
					esc(row.training_program || row.certification || ""), date(row.due_date), row.booked_for ? date(row.booked_for) : __(row.booking_status || "")]))}</div>
			<div class="lcc-card"><h4>${__("My Learning Content")}</h4>${table([__("Title"), __("Type"), __("Due"), __("Status"), ""],
				(data.assignments || []).map((row) => [esc(row.content_title), esc(row.content_type), date(row.due_date), __(row.status),
					["Completed", "Passed"].includes(row.status) ? "" : `<button class="btn btn-xs btn-primary" data-content="${esc(row.name)}">${row.content_type === "Quiz" ? __("Take the Quiz") : __("Open")}</button>`]))}</div>
			<div class="lcc-row"><div class="lcc-card"><h4>${__("My Upcoming Training")}</h4>${table([__("Session"), __("When"), __("Where"), __("As"), ""],
				(data.upcoming || []).map((row) => [esc(row.event_name || row.name), date(row.start_time), esc(row.venue || ""), __(row.place),
					`<button class="btn btn-xs btn-default" data-withdraw="${esc(row.name)}">${__("Withdraw")}</button>
					 <button class="btn btn-xs btn-default" data-signin="${esc(row.name)}">${__("Sign In")}</button>`]))}</div>
			<div class="lcc-card"><h4>${__("Sessions Open to Me")}</h4>${table([__("Session"), __("When"), __("Seats Left"), ""],
				(data.open_sessions || []).map((row) => [esc(row.event_name || row.name), date(row.start_time),
					row.custom_capacity ? row.custom_seats_left : __("No limit"), `<button class="btn btn-xs btn-primary" data-register="${esc(row.name)}">${__("Register")}</button>`]))}</div></div>
			<div class="lcc-row"><div class="lcc-card"><h4>${__("My Certificates")}</h4>${table([__("Certificate"), __("Expires"), __("Status"), ""],
				(data.certificates || []).map((row) => [esc(row.certification), date(row.expiry_date), __(row.status || ""),
					row.attachment ? `<a href="${esc(row.attachment)}" target="_blank">${__("Download")}</a>` : ""]))}</div>
			<div class="lcc-card"><h4>${__("My Skills")}</h4>${table([__("Skill"), __("Level"), __("Needed"), __("Status")],
				(data.skills || []).map((row) => [esc(row.skill), esc(String(row.level || "").split(" ")[0]), esc(String(row.required_level || "").split(" ")[0]), __(row.status)]))}</div></div>
			<div class="lcc-card"><h4>${__("My Training History")}</h4>${table([__("Date"), __("Training"), __("Hours"), __("Marks")],
				(data.history || []).map((row) => [date(row.day), esc(row.training_program || ""), row.hours, row.marks ?? ""]))}
				<button class="btn btn-xs btn-default" data-cpd="1">${__("Log CPD")}</button></div>`);
		const reload = () => this.load();
		const seat = (method, event) =>
			frappe.xcall("hrms_addon.hrms_addon.learning_attendance." + method, { training_event: event }, "POST").then((found) => {
				frappe.show_alert({ message: __(found.status || found.message || ""), indicator: "green" });
				reload();
			});
		this.$body.find("[data-content]").on("click", (event) => hrms_addon.open_content($(event.currentTarget).attr("data-content"), reload));
		this.$body.find("[data-register]").on("click", (event) => seat("register", $(event.currentTarget).attr("data-register")));
		this.$body.find("[data-withdraw]").on("click", (event) => seat("withdraw", $(event.currentTarget).attr("data-withdraw")));
		this.$body.find("[data-signin]").on("click", (event) => seat("self_sign_in", $(event.currentTarget).attr("data-signin")));
		this.$body.find("[data-open-passport]").on("click", () => frappe.set_route("learning-passport", data.employee.name));
		this.$body.find("[data-cpd]").on("click", () => frappe.new_doc("CPD Log", { employee: data.employee.name }));
	}
};
