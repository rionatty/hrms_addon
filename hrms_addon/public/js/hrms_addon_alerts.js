// HRMS Addon — My Alerts.
//
// A panel in the page's right-hand sidebar, under what Frappe already puts
// there (Assign, Attachments, Tags, Share, who edited it), showing the
// logged-in user their own work: the assignments on their ToDo list (an
// onboarding task, a 30-60-90 review, a probation evaluation, a contract
// coming to its end) and their notifications, newest first.
//
// WHERE IT GOES
//
// Into `.layout-side-section` — the column Frappe builds for the sidebar on
// forms and on list views (frappe/public/js/frappe/views/page.js). It is
// rebuilt as you move between pages, so the panel is put back on every route
// change, and never twice on the same one.
//
// WHAT REFRESHES IT
//
// frappe publishes "notification" to the recipient whenever a Notification
// Log is created (frappe/desk/doctype/notification_log/notification_log.py),
// and an assignment creates one, so that single event covers both halves of
// the list. A slow poll runs as well, for a task whose due date passes while
// the page is open, and because nothing is published when somebody else
// closes a ToDo. Each alert that was not in the previous answer is announced
// with frappe.show_alert, coloured by the same band as its row.

(function () {
	if (typeof frappe === "undefined" || !frappe.boot) return;
	if (frappe.session && frappe.session.user === "Guest") return;

	const PANEL = "ha-alerts";
	const POLL_MS = 5 * 60 * 1000;
	const INDICATORS = { overdue: "red", today: "orange", soon: "blue", later: "blue", none: "gray" };

	let answer = null; // the last one from the server, so a new page draws at once
	let known = null; // the keys of that answer: null until the first one lands
	let busy = false;

	function panel_html() {
		return `
			<div class="ha-alerts-head">
				<span class="ha-alerts-title">${__("My Alerts")}</span>
				<span class="ha-alerts-count ha-band-none">0</span>
			</div>
			<div class="ha-alerts-body"><div class="ha-alerts-empty">${__("Nothing due.")}</div></div>
			<div class="ha-alerts-foot"><button class="ha-alerts-read-all" type="button">${__("Mark notifications read")}</button></div>`;
	}

	// The sidebar is rebuilt page by page: put the panel back where it is missing.
	function mount() {
		const sides = document.querySelectorAll(".layout-side-section");
		for (const side of sides) {
			if (side.querySelector("." + PANEL)) continue;
			const panel = document.createElement("div");
			panel.className = PANEL;
			panel.innerHTML = panel_html();
			side.appendChild(panel);
			panel.querySelector(".ha-alerts-body").addEventListener("click", clicked);
			panel.querySelector(".ha-alerts-read-all").addEventListener("click", read_all);
		}
		if (sides.length) {
			if (answer) render(answer);
			else load();
		}
	}

	function clicked(event) {
		const row = event.target.closest(".ha-alert");
		if (!row) return;
		event.preventDefault();
		const { kind, key, doctype, docname } = row.dataset;
		if (kind === "notification") {
			frappe.xcall("hrms_addon.hrms_addon.alerts.mark_read", { name: key }).then(load);
		}
		if (doctype && docname) {
			frappe.set_route("Form", doctype, docname);
		}
	}

	function read_all() {
		frappe.xcall("hrms_addon.hrms_addon.alerts.mark_all_read").then(load);
	}

	function load() {
		if (busy) return;
		busy = true;
		frappe
			.xcall("hrms_addon.hrms_addon.alerts.my_alerts")
			.then((fresh) => {
				busy = false;
				answer = fresh || {};
				render(answer);
			})
			.catch((error) => {
				busy = false;
				// say so in the panel rather than leaving an empty one that
				// looks like there is nothing to do
				for (const body of document.querySelectorAll("." + PANEL + " .ha-alerts-body")) {
					body.innerHTML = `<div class="ha-alerts-empty">${__("Alerts could not be loaded.")}</div>`;
				}
				console.error("hrms_addon: my_alerts failed", error);
			});
	}

	function render(data) {
		const alerts = data.alerts || [];
		const count = data.total || 0;
		const band = data.band || "none";
		for (const panel of document.querySelectorAll("." + PANEL)) {
			const badge = panel.querySelector(".ha-alerts-count");
			badge.textContent = count > 99 ? "99+" : String(count);
			badge.className = "ha-alerts-count ha-band-" + band;
			const body = panel.querySelector(".ha-alerts-body");
			body.innerHTML = alerts.length
				? alerts.map(row_html).join("")
				: `<div class="ha-alerts-empty">${__("Nothing due.")}</div>`;
		}
		announce(alerts);
	}

	function row_html(alert) {
		const where = alert.doctype ? `${__(alert.doctype)}${alert.docname ? " · " + escape(alert.docname) : ""}` : "";
		const meta = [where, alert.when].filter(Boolean).join(" · ");
		const unread = alert.kind === "assignment" || alert.unread ? " ha-alert-unread" : "";
		return `
			<a class="ha-alert ha-band-${escape(alert.urgency)}${unread}" href="#"
				data-kind="${escape(alert.kind)}" data-key="${escape(alert.key)}"
				data-doctype="${escape(alert.doctype || "")}" data-docname="${escape(alert.docname || "")}">
				<span class="ha-alert-dot"></span>
				<span class="ha-alert-text">
					<span class="ha-alert-title">${escape(alert.title)}</span>
					<span class="ha-alert-meta">${meta}</span>
				</span>
			</a>`;
	}

	// Anything that was not in the previous answer has just arrived.
	function announce(alerts) {
		const keys = alerts.map((alert) => alert.key);
		if (known === null) {
			known = keys; // the first load is the state of things, not news
			return;
		}
		const seen = new Set(known);
		for (const alert of alerts.filter((alert) => !seen.has(alert.key))) {
			frappe.show_alert(
				{
					message: alert.title,
					subtitle: [alert.doctype, alert.when].filter(Boolean).join(" · "),
					indicator: INDICATORS[alert.urgency] || "blue",
				},
				7
			);
		}
		known = keys;
	}

	function escape(value) {
		return frappe.utils.escape_html(String(value == null ? "" : value));
	}

	function start() {
		mount();
		if (frappe.router && frappe.router.on) {
			frappe.router.on("change", () => setTimeout(mount, 100));
		}
		$(document).on("page-change form-refresh", () => setTimeout(mount, 100));
		if (frappe.realtime && frappe.realtime.on) {
			frappe.realtime.on("notification", load);
		}
		setInterval(load, POLL_MS);
	}

	// app_ready fires once the desk is up; if this file lands after it did
	// (a cached bundle, a slow route), start straight away instead.
	if (frappe.app) {
		start();
	} else {
		$(document).on("app_ready", start);
	}
})();
