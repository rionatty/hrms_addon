// HRMS Addon — My Alerts rail.
//
// A column down the right of the desk showing the logged-in user their own
// work: the assignments on their ToDo list (an onboarding task, a 30-60-90
// review, a probation evaluation, a contract coming to its end) and the
// notifications they have not read. It stays put rather than opening and
// closing, so what is due is on screen wherever they are working.
//
// WHY A COLUMN AND NOT AN OVERLAY
//
// frappe's desk lays the body out as a flex row (public/scss/desk/main.scss:
// `body { display: flex; flex-direction: row }` with `.main-section` at
// width 100%). Appending the rail to <body> makes it a third column beside
// the sidebar and the page, and the page gives up the width by itself — no
// fixed positioning, no padding pushed onto containers that Frappe may
// rearrange, and nothing of the page hidden underneath it.
//
// WHAT REFRESHES IT
//
// frappe publishes "notification" to the recipient whenever a Notification
// Log is created (frappe/desk/doctype/notification_log/notification_log.py),
// and an assignment creates one, so that single event covers both halves of
// the list. A slow poll runs as well, for a task whose due date passes while
// the page is open, and because nothing is published when somebody else
// closes a ToDo.
//
// Each alert that was not in the previous answer is announced with
// frappe.show_alert, coloured by the same band as its row.

(function () {
	if (typeof frappe === "undefined" || !frappe.boot) return;
	if (frappe.session && frappe.session.user === "Guest") return;

	const RAIL_CLASS = "ha-rail";
	const COLLAPSED = "ha-rail-collapsed";
	const STORE = "hrms_addon:alerts_collapsed";
	const POLL_MS = 5 * 60 * 1000;
	const INDICATORS = { overdue: "red", today: "orange", soon: "blue", later: "blue", none: "gray" };

	let rail = null;
	let opener = null;
	let known = null; // the keys of the last answer: null until the first one lands
	let busy = false;

	function collapsed() {
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
			/* nothing to remember it in; the rail still works for this visit */
		}
	}

	function build() {
		if (document.querySelector("." + RAIL_CLASS)) return;
		rail = document.createElement("div");
		rail.className = RAIL_CLASS;
		rail.innerHTML = `
			<div class="ha-rail-head">
				<button class="ha-rail-toggle" type="button" title="${__("Hide alerts")}" aria-label="${__("Hide alerts")}">›</button>
				<span class="ha-rail-title">${__("My Alerts")}</span>
				<span class="ha-rail-count ha-band-none">0</span>
			</div>
			<div class="ha-rail-actions">
				<button class="ha-rail-read-all" type="button">${__("Mark notifications read")}</button>
			</div>
			<div class="ha-rail-body"><div class="ha-rail-empty">${__("Nothing due.")}</div></div>`;
		document.body.appendChild(rail);

		// The tab that brings it back is a sibling, not a child: a collapsed
		// rail is width 0 with overflow hidden, and nothing inside it can be
		// clicked. Fixed, so it is not a flex item of the body row either.
		opener = document.createElement("button");
		opener.className = "ha-rail-open";
		opener.type = "button";
		opener.title = __("Show alerts");
		opener.setAttribute("aria-label", __("Show alerts"));
		opener.innerHTML = `<span class="ha-rail-open-count ha-band-none">0</span>`;
		document.body.appendChild(opener);
		if (collapsed()) document.documentElement.classList.add(COLLAPSED);

		rail.querySelector(".ha-rail-toggle").addEventListener("click", () => toggle(true));
		opener.addEventListener("click", () => toggle(false));
		rail.querySelector(".ha-rail-read-all").addEventListener("click", read_all);
		rail.querySelector(".ha-rail-body").addEventListener("click", clicked);
	}

	function toggle(hide) {
		document.documentElement.classList.toggle(COLLAPSED, hide);
		remember(hide);
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
			.then((answer) => {
				busy = false;
				render(answer || {});
			})
			.catch(() => {
				busy = false; // an offline moment is not worth an error dialog
			});
	}

	function render(answer) {
		if (!rail) return;
		const alerts = answer.alerts || [];
		const count = answer.total || 0;
		const band = answer.band || "none";

		for (const [node, base] of [
			[rail.querySelector(".ha-rail-count"), "ha-rail-count"],
			[opener.querySelector(".ha-rail-open-count"), "ha-rail-open-count"],
		]) {
			node.textContent = count > 99 ? "99+" : String(count);
			node.className = base + " ha-band-" + band;
		}

		const body = rail.querySelector(".ha-rail-body");
		if (!alerts.length) {
			body.innerHTML = `<div class="ha-rail-empty">${__("Nothing due.")}</div>`;
		} else {
			body.innerHTML = alerts.map(row_html).join("");
		}
		announce(alerts);
	}

	function row_html(alert) {
		const where = alert.doctype ? `${__(alert.doctype)}${alert.docname ? " · " + escape(alert.docname) : ""}` : "";
		const meta = [where, alert.when].filter(Boolean).join(" · ");
		return `
			<a class="ha-alert ha-band-${escape(alert.urgency)}" href="#"
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
