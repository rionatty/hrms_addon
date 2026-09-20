// HRMS Addon — My Alerts.
//
// A small panel floating at the bottom right of the desk with the logged-in
// user's own work: the assignments on their ToDo list (an onboarding task, a
// 30-60-90 review, a probation evaluation, a contract coming to its end) and
// their notifications, newest first. It can be shrunk to its header bar and
// opened again, and stays as it was left.
//
// WHY IT FLOATS
//
// It is fixed to the window rather than put in the page, so it is in the same
// place on a form, a list and a workspace, and nothing is pushed aside to
// make room for it: Frappe rebuilds the page as you move between routes, and
// a panel in the page goes with it.
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
	const MINIMISED = "ha-alerts-minimised";
	const STORE = "hrms_addon:alerts_minimised";
	const POLL_MS = 5 * 60 * 1000;
	const INDICATORS = { overdue: "red", today: "orange", soon: "blue", later: "blue", none: "gray" };

	let panel = null;
	let answer = null; // the last one from the server
	let known = null; // the keys of that answer: null until the first one lands
	let busy = false;

	function minimised() {
		try {
			return window.localStorage.getItem(STORE) === "1";
		} catch (e) {
			return false; // private windows and blocked storage: open is the default
		}
	}

	function remember(state) {
		try {
			window.localStorage.setItem(STORE, state ? "1" : "0");
		} catch (e) {
			/* nothing to remember it in; the panel still works for this visit */
		}
	}

	function build() {
		if (document.querySelector("." + PANEL)) return;
		panel = document.createElement("div");
		panel.className = PANEL + (minimised() ? " " + MINIMISED : "");
		panel.innerHTML = `
			<button class="ha-alerts-head" type="button" title="${__("Minimise")}" aria-expanded="true">
				<span class="ha-alerts-title">${__("My Alerts")}</span>
				<span class="ha-alerts-count ha-band-none">0</span>
				<span class="ha-alerts-toggle" aria-hidden="true"></span>
			</button>
			<div class="ha-alerts-body"><div class="ha-alerts-empty">${__("Nothing due.")}</div></div>
			<div class="ha-alerts-foot"><button class="ha-alerts-read-all" type="button">${__("Mark notifications read")}</button></div>`;
		document.body.appendChild(panel);
		panel.querySelector(".ha-alerts-head").addEventListener("click", toggle);
		panel.querySelector(".ha-alerts-body").addEventListener("click", clicked);
		panel.querySelector(".ha-alerts-read-all").addEventListener("click", read_all);
		if (answer) render(answer);
	}

	function toggle() {
		const now = !panel.classList.contains(MINIMISED);
		panel.classList.toggle(MINIMISED, now);
		panel.querySelector(".ha-alerts-head").setAttribute("aria-expanded", now ? "false" : "true");
		panel.querySelector(".ha-alerts-head").title = now ? __("Show alerts") : __("Minimise");
		remember(now);
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
				const body = panel && panel.querySelector(".ha-alerts-body");
				if (body) body.innerHTML = `<div class="ha-alerts-empty">${__("Alerts could not be loaded.")}</div>`;
				console.error("hrms_addon: my_alerts failed", error);
			});
	}

	function render(data) {
		if (!panel) return;
		const alerts = data.alerts || [];
		const count = data.total || 0;
		const badge = panel.querySelector(".ha-alerts-count");
		badge.textContent = count > 99 ? "99+" : String(count);
		badge.className = "ha-alerts-count ha-band-" + (data.band || "none");
		const body = panel.querySelector(".ha-alerts-body");
		body.innerHTML = alerts.length
			? alerts.map(row_html).join("")
			: `<div class="ha-alerts-empty">${__("Nothing due.")}</div>`;
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
		build();
		load();
		// the desk replaces the body's contents on some routes: put it back
		if (frappe.router && frappe.router.on) {
			frappe.router.on("change", () => setTimeout(build, 100));
		}
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
