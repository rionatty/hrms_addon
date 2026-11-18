// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

/* Training Sign-In (learning_attendance.py): the trainer's tablet at the door.
 *
 * Pick today's session, then scan each person's QR code or type their
 * employee number: they are marked Attended, or Late after the start. Switch
 * to Sign Out at the end of the day. The list shows who is in and who is
 * still expected; the rest are marked absent or excused from it.
 */

frappe.provide("hrms_addon");

const TSI_STYLE = `
.tsi { padding: 4px 0 24px; }
.tsi-bar { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-bottom: 12px; }
.tsi-bar .tsi-session { min-width: 280px; }
.tsi-code { display: flex; gap: 8px; margin-bottom: 12px; }
.tsi-code input { font-size: 22px; height: 54px; flex: 1; }
.tsi-code button { height: 54px; min-width: 110px; font-size: 15px; }
.tsi-mode .btn.active { background: #14395E; color: #fff; }
.tsi-last { display: flex; gap: 14px; align-items: center; background: var(--card-bg); border: 1px solid var(--border-color);
  border-radius: 12px; padding: 12px 14px; margin-bottom: 12px; min-height: 76px; }
.tsi-last .tsi-av { width: 52px; height: 52px; border-radius: 50%; background: #14395E; color: #fff; display: flex;
  align-items: center; justify-content: center; font-weight: 600; overflow: hidden; flex: none; }
.tsi-last .tsi-av img { width: 100%; height: 100%; object-fit: cover; }
.tsi-last .tsi-name { font-size: 18px; font-weight: 600; }
.tsi-tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
.tsi-tile { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 10px 12px; }
.tsi-tile small { display: block; color: var(--text-muted); font-size: 11.5px; }
.tsi-tile b { font-size: 24px; }
.tsi-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.tsi-table th { text-align: left; color: var(--text-muted); font-weight: 500; font-size: 11.5px; padding: 6px 8px;
  border-bottom: 1px solid var(--border-color); }
.tsi-table td { padding: 7px 8px; border-bottom: 1px solid var(--border-color); }
.tsi-green { color: #1F7A4D; } .tsi-amber { color: #B7791F; } .tsi-red { color: #A62B25; } .tsi-grey { color: #6B7280; }
.tsi-empty { color: var(--text-muted); padding: 8px 0; }
@media (max-width: 700px) { .tsi-tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
`;
const TSI_TONE = { Attended: "tsi-green", Late: "tsi-amber", Absent: "tsi-red", "No-show": "tsi-red", Excused: "tsi-grey",
	Invited: "tsi-grey", Registered: "tsi-grey" };
const TSI_METHOD = "hrms_addon.hrms_addon.learning_attendance.";

frappe.pages["training-sign-in"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Training Sign-In"), single_column: true });
	wrapper.training_sign_in = new hrms_addon.TrainingSignIn(page);
};

frappe.pages["training-sign-in"].on_page_show = function (wrapper) {
	const asked = frappe.get_route()[1] || (frappe.route_options || {}).training_event;
	frappe.route_options = null;
	wrapper.training_sign_in && wrapper.training_sign_in.load(asked);
};

hrms_addon.TrainingSignIn = class TrainingSignIn {
	constructor(page) {
		this.page = page;
		this.mode = "in";
		if (!document.getElementById("tsi-style")) $("<style id='tsi-style'>").text(TSI_STYLE).appendTo(document.head);
		this.$root = $(`<div class="tsi">
			<div class="tsi-bar"><select class="form-control tsi-session"></select>
				<div class="btn-group tsi-mode"><button class="btn btn-default btn-sm active" data-mode="in">${__("Sign In")}</button>
				<button class="btn btn-default btn-sm" data-mode="out">${__("Sign Out")}</button></div></div>
			<div class="tsi-code"><input class="form-control" autocomplete="off" placeholder="${__("Scan the QR code or type the employee number")}">
				<button class="btn btn-primary tsi-go">${__("Enter")}</button>
				<button class="btn btn-default tsi-scan">${__("Camera")}</button></div>
			<div class="tsi-last"><div class="tsi-empty">${__("Nobody signed in yet.")}</div></div>
			<div class="tsi-tiles"></div><div class="tsi-roll"></div></div>`).appendTo(page.main);
		this.$input = this.$root.find(".tsi-code input");
		this.$root.find(".tsi-go").on("click", () => this.enter());
		this.$input.on("keydown", (event) => event.key === "Enter" && this.enter());
		this.$root.find(".tsi-scan").on("click", () => this.camera());
		this.$root.find(".tsi-mode .btn").on("click", (event) => {
			this.mode = $(event.currentTarget).attr("data-mode");
			this.$root.find(".tsi-mode .btn").removeClass("active");
			$(event.currentTarget).addClass("active");
			this.$input.focus();
		});
		this.$root.find(".tsi-session").on("change", () => this.show_roll());
		page.add_inner_button(__("Mark the Rest Absent"), () => this.close_day());
		this.timer = setInterval(() => this.event && this.show_roll(true), 30000);
	}

	load(asked) {
		frappe.xcall(TSI_METHOD + "sessions_today").then((events) => {
			const $select = this.$root.find(".tsi-session").empty();
			if (!(events || []).length) {
				$select.append(`<option value="">${__("No session today")}</option>`);
				this.event = null;
				this.$root.find(".tsi-roll").html(`<div class="tsi-empty">${__("No session you take attendance for runs today.")}</div>`);
				return;
			}
			for (const event of events) {
				const label = `${event.event_name || event.name} · ${frappe.datetime.str_to_user(event.start_time).split(" ")[1] || ""} · ${event.signed_in}/${event.expected}`;
				$select.append($("<option>").val(event.name).text(label));
			}
			if (asked && events.some((event) => event.name === asked)) $select.val(asked);
			this.show_roll();
		});
	}

	show_roll(quiet) {
		this.event = this.$root.find(".tsi-session").val();
		if (!this.event) return;
		frappe.xcall(TSI_METHOD + "roll", { training_event: this.event }).then((data) => {
			this.data = data;
			const c = data.counts;
			this.$root.find(".tsi-tiles").html(
				[[__("Expected"), c.expected], [__("Signed In"), c.signed_in], [__("Late"), c.late], [__("Not In"), c.not_in]]
					.map(([label, value]) => `<div class="tsi-tile"><small>${label}</small><b>${value}</b></div>`).join("")
			);
			const esc = frappe.utils.escape_html;
			const rows = data.rows || [];
			this.$root.find(".tsi-roll").html(rows.length
				? `<table class="tsi-table"><thead><tr><th>${__("Employee")}</th><th>${__("Department")}</th><th>${__("Status")}</th>
					<th>${__("In")}</th><th>${__("Out")}</th><th></th></tr></thead><tbody>${rows.map((row) => `<tr>
					<td>${esc(row.employee_name || row.employee)}</td><td>${esc(row.department || "")}</td>
					<td class="${TSI_TONE[row.status] || ""}">${__(row.status)}</td><td>${esc((row.time_in || "").slice(0, 5))}</td>
					<td>${esc((row.time_out || "").slice(0, 5))}</td>
					<td>${["Invited", "Registered"].includes(row.status) ? `<button class="btn btn-xs btn-default" data-mark="Excused" data-employee="${esc(row.employee)}">${__("Excused")}</button>` : ""}</td></tr>`).join("")}</tbody></table>`
				: `<div class="tsi-empty">${__("Nobody is booked for this session.")}</div>`);
			this.$root.find("[data-mark]").on("click", (event) => {
				const $button = $(event.currentTarget);
				this.mark([{ employee: $button.attr("data-employee"), status: $button.attr("data-mark") }]);
			});
			if (!quiet) this.$input.focus();
		});
	}

	enter(code) {
		code = code || this.$input.val();
		if (!this.event || !(code || "").trim()) return;
		this.$input.val("");
		frappe
			.xcall(TSI_METHOD + "sign_in", { training_event: this.event, code: code, method: this.scanned ? "QR" : "Employee Number",
				sign_out: this.mode === "out" ? 1 : 0 }, "POST")
			.then((person) => {
				this.scanned = false;
				this.last(person);
				this.show_roll(true);
			})
			.catch(() => this.$input.focus());
		this.$input.focus();
	}

	last(person) {
		const esc = frappe.utils.escape_html;
		const initials = (person.employee_name || "?").split(" ").filter(Boolean).slice(0, 2).map((part) => part[0]).join("");
		const avatar = person.image ? `<img src="${esc(person.image)}" alt="">` : esc(initials.toUpperCase());
		const when = this.mode === "out" ? __("Out at {0}", [(person.time_out || "").slice(0, 5)]) : __("In at {0}", [(person.time_in || "").slice(0, 5)]);
		this.$root.find(".tsi-last").html(`<div class="tsi-av">${avatar}</div><div><div class="tsi-name">${esc(person.employee_name)}</div>
			<div class="${TSI_TONE[person.status] || ""}">${__(person.status)} · ${when}${person.message ? " · " + esc(person.message) : ""}</div></div>`);
	}

	camera() {
		if (!frappe.ui.Scanner) {
			frappe.msgprint(__("Use a QR scanner, or type the employee number."));
			return;
		}
		new frappe.ui.Scanner({
			dialog: true,
			multiple: true,
			on_scan: (data) => {
				this.scanned = true;
				this.enter(data && (data.decodedText || data.text || data));
			},
		});
	}

	mark(rows) {
		frappe
			.xcall(TSI_METHOD + "mark_many", { training_event: this.event, day: this.data.day, rows: JSON.stringify(rows) }, "POST")
			.then(() => this.show_roll(true));
	}

	close_day() {
		if (!this.data) return;
		const rest = (this.data.rows || []).filter((row) => ["Invited", "Registered"].includes(row.status));
		if (!rest.length) {
			frappe.show_alert({ message: __("Everyone is marked."), indicator: "green" });
			return;
		}
		frappe.confirm(__("Mark the {0} not signed in as absent?", [rest.length]), () =>
			this.mark(rest.map((row) => ({ employee: row.employee, status: "Absent" })))
		);
	}
};
