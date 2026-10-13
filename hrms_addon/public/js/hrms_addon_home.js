// HRMS Addon — the desk home.
//
// Frappe v16's desk opens on a page of module tiles and nothing else. This
// puts a home above them, on that same page: a greeting, the figures that
// matter today, what waits for the logged-in user, and the pages they open
// most (hrms_addon/hrms_addon/home.py fills it in one call). The tiles stay
// Frappe's own, drawn as cards under a Modules heading, so search, the
// notifications, the avatar menu and editing the desktop all work as before.
//
// Luuka, 13 Oct 2026: "the current desk is not that appealing and executive".
//
// WHAT IT MUST NEVER DO
//
// Stop the desk opening. Everything here is inside try/catch, the home is
// only ever added to the page, and a failed call leaves the tiles exactly as
// Frappe drew them. HRMS Addon Theme Settings > Desk Home > Tiles Only
// switches it off without a deploy.
//
// A plain asset in app_include_js, so a change to it needs no `bench build`:
// its styles are written into the page here for the same reason.

(function () {
	if (typeof frappe === "undefined" || !frappe.boot) return;
	if (!frappe.boot.hrms_addon_home) return;
	if (frappe.session && frappe.session.user === "Guest") return;
	frappe.provide("hrms_addon.home");

	const METHOD = "hrms_addon.hrms_addon.home.summary";
	const FRESH_MS = 60 * 1000; // how long an answer is shown before it is asked for again
	const STYLE_ID = "ha-home-style";
	let answer = null;
	let asked_at = 0;
	let asking = false;
	let tab = "items";

	const ICONS = {
		employees:
			'<path d="M16 19v-1.5a3.5 3.5 0 0 0-3.5-3.5h-5A3.5 3.5 0 0 0 4 17.5V19"/><circle cx="10" cy="8" r="3.2"/>' +
			'<path d="M20 19v-1.4a3.2 3.2 0 0 0-2.4-3.1M15.5 5a3.2 3.2 0 0 1 0 6.1"/>',
		on_site: '<path d="M12 21s7-6.1 7-11.3A7 7 0 0 0 5 9.7C5 14.9 12 21 12 21z"/><circle cx="12" cy="9.6" r="2.4"/>',
		on_leave: '<rect x="4" y="5.5" width="16" height="14.5" rx="2.2"/><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4"/>',
		waiting: '<path d="M4 13.5h4l1.5 2.5h5l1.5-2.5h4"/><path d="M6.2 5.5h11.6L20 13.5V18a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18v-4.5z"/>',
		unread: '<path d="M6.5 16.5V11a5.5 5.5 0 0 1 11 0v5.5l1.5 2h-14z"/><path d="M10 20.5a2.2 2.2 0 0 0 4 0"/>',
		contracts: '<path d="M7 3.5h7l4 4V19a1.5 1.5 0 0 1-1.5 1.5h-9.5A1.5 1.5 0 0 1 5.5 19V5A1.5 1.5 0 0 1 7 3.5z"/>' +
			'<path d="M14 3.5v4h4M9 12.5h6M9 16h4"/>',
		arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
		chevron: '<path d="M9 6l6 6-6 6"/>',
		modules: '<rect x="4" y="4" width="6.5" height="6.5" rx="1.6"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.6"/>' +
			'<rect x="4" y="13.5" width="6.5" height="6.5" rx="1.6"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.6"/>',
		page: '<path d="M5 19V9M10 19V5M15 19v-7M20 19v-11"/>',
	};

	function icon(name) {
		return (
			'<svg class="ha-home-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ' +
			`stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ICONS.page}</svg>`
		);
	}

	function esc(text) {
		return frappe.utils.escape_html(text == null ? "" : String(text));
	}

	function count(value) {
		const number = Number(value) || 0;
		try {
			return number.toLocaleString();
		} catch (e) {
			return String(number);
		}
	}

	function day_words(day) {
		try {
			const parts = String(day).split("-").map(Number);
			return new Date(parts[0], parts[1] - 1, parts[2]).toLocaleDateString(undefined, {
				weekday: "long",
				day: "numeric",
				month: "long",
			});
		} catch (e) {
			return day || "";
		}
	}

	function style() {
		if (document.getElementById(STYLE_ID)) return;
		const sheet = document.createElement("style");
		sheet.id = STYLE_ID;
		sheet.textContent = CSS;
		document.head.appendChild(sheet);
	}

	// where the home goes: inside Frappe's desk page, above its tiles
	function mount() {
		const wrapper = document.querySelector(".desktop-wrapper");
		const tiles = wrapper && wrapper.querySelector(".desktop-container");
		if (!wrapper || !tiles) return null;
		let home = wrapper.querySelector(".ha-home");
		if (!home) {
			home = document.createElement("div");
			home.className = "ha-home";
			wrapper.insertBefore(home, tiles);
			wrapper.classList.add("ha-has-home");
		}
		return home;
	}

	function skeleton() {
		const line = (width) => `<div class="ha-home-bone" style="width:${width}"></div>`;
		return (
			`<section class="ha-home-hero"><div class="ha-home-hero-text">${line("260px")}${line("180px")}</div></section>` +
			`<div class="ha-home-cards">${[1, 2, 3, 4]
				.map(() => `<div class="ha-home-card">${line("90px")}${line("60px")}${line("120px")}</div>`)
				.join("")}</div>` +
			modules_heading()
		);
	}

	function modules_heading() {
		return `<div class="ha-home-heading">${icon("modules")}<span>${__("Modules")}</span></div>`;
	}

	function hero(data) {
		const name = data.first_name || "";
		const waits = data.waiting || {};
		const action = data.action || {};
		const where = [day_words(data.today), data.company].filter(Boolean).map(esc).join(" · ");
		return (
			`<section class="ha-home-hero">` +
			`<div class="ha-home-avatar">${esc(name.trim().charAt(0).toUpperCase() || "•")}</div>` +
			`<div class="ha-home-hero-text"><h2>${esc(__(data.greeting || "Welcome"))}, ${esc(name)}</h2>` +
			`<p>${where}</p></div>` +
			`<div class="ha-home-hero-side">` +
			`<button type="button" class="ha-home-chip" data-ha-home="todo">${icon("waiting")}` +
			`<span><b>${count(waits.tasks)}</b><small>${__("Waiting for you")}</small></span></button>` +
			(action.label
				? `<button type="button" class="ha-home-action" data-ha-home="action">` +
				  `<span>${esc(__(action.label))}</span>${icon("arrow")}</button>`
				: "") +
			`</div></section>`
		);
	}

	function cards(data) {
		const all = data.cards || [];
		if (!all.length) return "";
		return (
			`<div class="ha-home-cards">` +
			all
				.map(
					(card, index) =>
						`<button type="button" class="ha-home-card ha-tone-${esc(card.tone || "navy")}" ` +
						`data-ha-home="card" data-index="${index}">` +
						`<span class="ha-home-card-top"><span class="ha-home-card-label">${esc(__(card.label))}</span>` +
						`<span class="ha-home-card-icon">${icon(card.key)}</span></span>` +
						`<span class="ha-home-card-value">${count(card.value)}</span>` +
						`<span class="ha-home-card-note">${esc(__(card.note || ""))}</span></button>`
				)
				.join("") +
			`</div>`
		);
	}

	function rows(list, empty) {
		if (!list.length) return `<div class="ha-home-empty">${esc(empty)}</div>`;
		return list
			.map(
				(row, index) =>
					`<button type="button" class="ha-home-row" data-ha-home="row" data-index="${index}">` +
					`<span class="ha-home-dot ha-band-${esc(row.band || "none")}"></span>` +
					`<span class="ha-home-row-text"><span class="ha-home-row-title">${esc(row.title)}</span>` +
					`<span class="ha-home-row-meta">${[row.doctype ? __(row.doctype) : "", row.docname, row.when ? __(row.when) : ""]
						.filter(Boolean)
						.map(esc)
						.join(" · ")}</span></span>${icon("chevron")}</button>`
			)
			.join("");
	}

	function panels(data) {
		const waits = data.waiting || {};
		const links = data.shortcuts || [];
		const shown = tab === "notes" ? waits.notes || [] : waits.items || [];
		const tabs = [
			["items", __("To Do"), waits.tasks],
			["notes", __("Notifications"), waits.unread],
		]
			.map(
				([key, label, total]) =>
					`<button type="button" class="ha-home-tab${tab === key ? " ha-on" : ""}" data-ha-home="tab" ` +
					`data-tab="${key}">${label}<i>${count(total)}</i></button>`
			)
			.join("");
		const waiting =
			`<section class="ha-home-panel"><header><span class="ha-home-panel-icon">${icon("waiting")}</span>` +
			`<h3>${__("Waiting for You")}</h3><span class="ha-home-tabs">${tabs}</span></header>` +
			`<div class="ha-home-list">${rows(
				shown,
				tab === "notes" ? __("Nothing unread.") : __("Nothing is waiting for you.")
			)}</div></section>`;
		const quick = links.length
			? `<section class="ha-home-panel ha-home-quick"><header><span class="ha-home-panel-icon">${icon("page")}</span>` +
			  `<h3>${__("Quick Access")}</h3></header><div class="ha-home-list">` +
			  links
					.map(
						(link, index) =>
							`<button type="button" class="ha-home-row" data-ha-home="link" data-index="${index}">` +
							`<span class="ha-home-row-text"><span class="ha-home-row-title">${esc(__(link.label))}</span></span>` +
							`${icon("chevron")}</button>`
					)
					.join("") +
			  `</div></section>`
			: "";
		return `<div class="ha-home-panels${quick ? "" : " ha-home-one"}">${waiting}${quick}</div>`;
	}

	// a route the server names, opened as Frappe opens it
	function go(target) {
		if (!target || !target.route) return;
		const route = target.route.slice();
		const filters = Object.assign({}, target.filters || {});
		if (target.mine && route[1] === "ToDo") Object.assign(filters, { allocated_to: frappe.session.user, status: "Open" });
		if (target.mine && route[1] === "Notification Log") Object.assign(filters, { for_user: frappe.session.user, read: 0 });
		if (route[0] === "List" && Object.keys(filters).length) frappe.route_options = filters;
		frappe.set_route(route);
	}

	function draw(home) {
		const data = answer;
		if (!data) {
			home.innerHTML = skeleton();
			return;
		}
		home.innerHTML = hero(data) + cards(data) + panels(data) + modules_heading();
		home.querySelectorAll("[data-ha-home]").forEach((element) => {
			element.addEventListener("click", () => {
				try {
					const what = element.getAttribute("data-ha-home");
					const index = Number(element.getAttribute("data-index"));
					if (what === "tab") {
						tab = element.getAttribute("data-tab");
						draw(home);
					} else if (what === "todo") go({ route: ["List", "ToDo"], mine: 1 });
					else if (what === "action") go(data.action);
					else if (what === "card") go((data.cards || [])[index]);
					else if (what === "link") go((data.shortcuts || [])[index]);
					else if (what === "row") {
						const row = ((tab === "notes" ? data.waiting.notes : data.waiting.items) || [])[index];
						if (row && row.doctype && row.docname) frappe.set_route("Form", row.doctype, row.docname);
						else go({ route: ["List", "ToDo"], mine: 1 });
					}
				} catch (error) {
					console.error(error);
				}
			});
		});
	}

	function load(home) {
		if (asking || Date.now() - asked_at < FRESH_MS) return;
		asking = true;
		// fetch, not frappe.call: a call that fails must leave the desk alone, and frappe.call would open
		// Frappe's Server Error dialog on the page everybody lands on
		fetch("/api/method/" + METHOD, { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } })
			.then((response) => (response.ok ? response.json() : null))
			.then((r) => {
				answer = (r && r.message) || answer;
			})
			.catch(() => {})
			.then(() => {
				asked_at = Date.now(); // the tiles are still there; a call that failed is tried again later, not at once
				asking = false;
				const there = mount();
				if (there && answer) draw(there);
				else if (there && !answer) there.remove(); // nothing to show: the desk as Frappe drew it
				if (there && !answer) document.querySelector(".desktop-wrapper").classList.remove("ha-has-home");
			});
	}

	function show() {
		try {
			// the last call failed: the desk stays as Frappe drew it until it is worth asking again
			if (!answer && asked_at && Date.now() - asked_at < FRESH_MS) return true;
			style();
			const home = mount();
			if (!home) return false;
			draw(home);
			load(home);
			return true;
		} catch (error) {
			console.error(error);
			return true; // do not keep trying something that throws
		}
	}

	function on_desk() {
		try {
			return (frappe.get_route() || [])[0] === "desktop" || !!document.querySelector(".desktop-wrapper");
		} catch (e) {
			return false;
		}
	}

	// Frappe draws its desk page as the route settles, so the tiles may not be
	// there yet when the page changes: look a few times, then leave it
	function arrive() {
		if (!on_desk()) return;
		let tries = 0;
		const look = () => {
			tries += 1;
			if (!show() && tries < 12) setTimeout(look, 150 * tries);
		};
		look();
	}

	const CSS = `
.ha-home {
	--ha-h-navy: var(--hra-primary, #14395E);
	--ha-h-deep: var(--hra-primary-dark, #0A2540);
	--ha-h-mid: var(--hra-primary-mid, #2A5A8C);
	--ha-h-gold: #EAA51A;
	--ha-h-line: var(--hra-border, #D7DEEA);
	--ha-h-ink: var(--text-color, #1E2A3A);
	--ha-h-muted: var(--text-muted, #5C6B82);
	--ha-h-card: var(--card-bg, #fff);
	max-width: 1220px;
	margin: 18px auto 0;
	padding: 0 20px;
	box-sizing: border-box;
	font-feature-settings: "tnum";
}
.ha-home * { box-sizing: border-box; }
.ha-home button { font: inherit; color: inherit; background: none; border: 0; padding: 0; text-align: left; cursor: pointer; }
.ha-home-icon { width: 18px; height: 18px; flex: none; }

/* the greeting */
.ha-home-hero {
	display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
	padding: 22px 26px; border-radius: 18px; color: #fff; position: relative; overflow: hidden;
	background:
		radial-gradient(520px 220px at 88% -30%, rgba(234,165,26,.26), transparent 62%),
		radial-gradient(420px 260px at 8% 130%, rgba(255,255,255,.10), transparent 60%),
		linear-gradient(118deg, var(--ha-h-deep) 0%, var(--ha-h-navy) 52%, var(--ha-h-mid) 100%);
	box-shadow: 0 10px 28px rgba(10,37,64,.20);
}
.ha-home-hero::after {
	content: ""; position: absolute; right: -60px; top: -80px; width: 260px; height: 260px; border-radius: 50%;
	border: 1px solid rgba(255,255,255,.10); box-shadow: 0 0 0 38px rgba(255,255,255,.035), 0 0 0 86px rgba(255,255,255,.025);
	pointer-events: none;
}
.ha-home-avatar {
	width: 46px; height: 46px; border-radius: 50%; flex: none; display: grid; place-items: center;
	font-weight: 700; font-size: 18px; background: rgba(255,255,255,.12);
	box-shadow: inset 0 0 0 2px var(--ha-h-gold);
}
.ha-home-hero-text { flex: 1 1 260px; min-width: 0; }
.ha-home-hero h2 { margin: 0; font-size: 22px; line-height: 1.25; font-weight: 700; letter-spacing: -.01em; color: #fff; }
.ha-home-hero p { margin: 4px 0 0; font-size: 13px; color: rgba(255,255,255,.80); }
.ha-home-hero-side { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; position: relative; z-index: 1; }
.ha-home .ha-home-chip {
	display: flex; align-items: center; gap: 10px; padding: 9px 14px; border-radius: 12px; color: #fff;
	background: rgba(255,255,255,.09); box-shadow: inset 0 0 0 1px rgba(255,255,255,.20);
}
.ha-home .ha-home-chip:hover { background: rgba(255,255,255,.16); }
.ha-home-chip span { display: flex; flex-direction: column; line-height: 1.15; }
.ha-home-chip b { font-size: 17px; font-weight: 700; }
.ha-home-chip small { font-size: 11.5px; color: rgba(255,255,255,.82); }
.ha-home-chip .ha-home-icon { color: var(--ha-h-gold); }
.ha-home .ha-home-action {
	display: inline-flex; align-items: center; gap: 8px; padding: 11px 18px; border-radius: 12px;
	background: var(--ha-h-gold); color: #1B2434; font-weight: 700; font-size: 13.5px;
	box-shadow: 0 6px 16px rgba(234,165,26,.32);
}
.ha-home .ha-home-action:hover { filter: brightness(1.06); transform: translateY(-1px); }
.ha-home .ha-home-action, .ha-home .ha-home-card, .ha-home .ha-home-row { transition: transform .12s ease, box-shadow .12s ease, background .12s ease; }

/* the figures */
.ha-home-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; margin-top: 16px; }
.ha-home .ha-home-card {
	display: flex; flex-direction: column; gap: 4px; padding: 16px 18px 15px; border-radius: 14px;
	background: var(--ha-h-card); border: 1px solid var(--ha-h-line); position: relative; overflow: hidden;
	--ha-tone: var(--ha-h-navy);
}
.ha-home .ha-home-card::before { content: ""; position: absolute; inset: 0 0 auto 0; height: 3px; background: var(--ha-tone); }
.ha-home .ha-home-card:hover { transform: translateY(-2px); box-shadow: 0 10px 22px rgba(20,57,94,.12); }
.ha-home .ha-tone-green { --ha-tone: #1F9D6B; }
.ha-home .ha-tone-amber { --ha-tone: #D98A12; }
.ha-home .ha-tone-rose { --ha-tone: #D5475B; }
.ha-home .ha-tone-blue { --ha-tone: #2F7BD1; }
.ha-home-card-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.ha-home-card-label { font-size: 12.5px; font-weight: 600; color: var(--ha-h-muted); }
.ha-home-card-icon { width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center; color: var(--ha-tone); background: color-mix(in srgb, var(--ha-tone) 12%, transparent); }
.ha-home-card-value { font-size: 28px; font-weight: 700; line-height: 1.15; color: var(--ha-h-ink); letter-spacing: -.02em; }
.ha-home-card-note { font-size: 12px; color: var(--ha-h-muted); min-height: 16px; }

/* what waits, and the pages */
.ha-home-panels { display: grid; grid-template-columns: minmax(0, 1.9fr) minmax(0, 1fr); gap: 14px; margin-top: 14px; align-items: start; }
.ha-home-panels.ha-home-one { grid-template-columns: minmax(0, 1fr); }
.ha-home-panel { background: var(--ha-h-card); border: 1px solid var(--ha-h-line); border-radius: 14px; overflow: hidden; }
.ha-home-panel header { display: flex; align-items: center; gap: 10px; padding: 13px 16px; border-bottom: 1px solid var(--ha-h-line); flex-wrap: wrap; }
.ha-home-panel h3 { margin: 0; font-size: 14.5px; font-weight: 700; color: var(--ha-h-ink); flex: 1 1 auto; }
.ha-home-panel-icon { width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center; color: #fff; background: var(--ha-h-navy); }
.ha-home-tabs { display: inline-flex; gap: 2px; padding: 3px; border-radius: 10px; background: color-mix(in srgb, var(--ha-h-navy) 7%, transparent); }
.ha-home .ha-home-tab { padding: 5px 11px; border-radius: 8px; font-size: 12.5px; font-weight: 600; color: var(--ha-h-muted); display: inline-flex; gap: 6px; align-items: center; }
.ha-home .ha-home-tab i { font-style: normal; font-size: 11px; padding: 1px 6px; border-radius: 99px; background: color-mix(in srgb, var(--ha-h-navy) 10%, transparent); }
.ha-home .ha-home-tab.ha-on { background: var(--ha-h-card); color: var(--ha-h-ink); box-shadow: 0 1px 3px rgba(20,57,94,.16); }
.ha-home-list { padding: 4px 6px 6px; }
.ha-home .ha-home-row { display: flex; align-items: center; gap: 11px; width: 100%; padding: 10px; border-radius: 10px; color: var(--ha-h-muted); }
.ha-home .ha-home-row:hover { background: color-mix(in srgb, var(--ha-h-navy) 6%, transparent); }
.ha-home-row-text { display: flex; flex-direction: column; gap: 1px; flex: 1 1 auto; min-width: 0; }
.ha-home-row-title { font-size: 13.5px; font-weight: 600; color: var(--ha-h-ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ha-home-row-meta { font-size: 12px; color: var(--ha-h-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ha-home-dot { width: 9px; height: 9px; border-radius: 50%; flex: none; background: #9AA8BC; }
.ha-home-dot.ha-band-overdue { background: #D5475B; box-shadow: 0 0 0 3px rgba(213,71,91,.16); }
.ha-home-dot.ha-band-today { background: #D98A12; box-shadow: 0 0 0 3px rgba(217,138,18,.16); }
.ha-home-dot.ha-band-soon, .ha-home-dot.ha-band-later { background: #2F7BD1; }
.ha-home-empty { padding: 26px 12px; text-align: center; font-size: 13px; color: var(--ha-h-muted); }
.ha-home-heading { display: flex; align-items: center; gap: 8px; margin: 22px 2px 10px; font-size: 12px; font-weight: 700; letter-spacing: .09em; text-transform: uppercase; color: var(--ha-h-muted); }

/* while the figures are on their way */
.ha-home-bone { height: 12px; border-radius: 6px; margin: 6px 0; background: linear-gradient(90deg, rgba(127,147,173,.16), rgba(127,147,173,.30), rgba(127,147,173,.16)); background-size: 200% 100%; animation: ha-home-shine 1.3s linear infinite; }
.ha-home-hero .ha-home-bone { background: linear-gradient(90deg, rgba(255,255,255,.14), rgba(255,255,255,.30), rgba(255,255,255,.14)); background-size: 200% 100%; }
@keyframes ha-home-shine { from { background-position: 200% 0; } to { background-position: -200% 0; } }
@media (prefers-reduced-motion: reduce) { .ha-home-bone { animation: none; } .ha-home * { transition: none !important; } }

/* Frappe's own tiles, as cards under the Modules heading. Only the tiles of
   the desk itself (child selectors all the way): a folder's thumbnails and
   the folder window keep Frappe's layout, and so does the desk while it is
   being edited. */
.desktop-wrapper.ha-has-home .desktop-container { display: block; padding: 0 20px 44px; box-sizing: border-box; }
.desktop-wrapper.ha-has-home .desktop-container > .icons-container { max-width: 1180px !important; width: 100% !important; margin: 0 auto !important; padding: 0 !important; }
.desktop-wrapper.ha-has-home:not([data-mode="Edit"]) .desktop-container > .icons-container > .icons {
	grid-template-columns: repeat(auto-fill, minmax(214px, 1fr)) !important; grid-template-rows: none !important;
	grid-auto-rows: auto !important; gap: 12px !important; justify-content: stretch !important; justify-items: stretch !important;
}
.desktop-wrapper.ha-has-home:not([data-mode="Edit"]) .desktop-container > .icons-container > .icons > .desktop-icon {
	width: auto !important; height: auto !important; min-height: 64px; box-sizing: border-box; flex-direction: row !important; align-items: center !important;
	gap: 12px !important; padding: 9px 14px !important; border: 1px solid var(--hra-border, #D7DEEA) !important;
	border-radius: 14px !important; background: var(--card-bg, #fff); transition: transform .12s ease, box-shadow .12s ease, border-color .12s ease;
}
.desktop-wrapper.ha-has-home:not([data-mode="Edit"]) .desktop-container > .icons-container > .icons > .desktop-icon:hover {
	transform: translateY(-2px); box-shadow: 0 10px 22px rgba(20,57,94,.12); border-color: var(--hra-primary-light, #3B78B5) !important;
}
.desktop-wrapper.ha-has-home:not([data-mode="Edit"]) .desktop-container > .icons-container > .icons > .desktop-icon > .icon-container { flex: none; padding: 0 !important; width: 44px !important; height: 44px !important; }
.desktop-wrapper.ha-has-home:not([data-mode="Edit"]) .desktop-container > .icons-container > .icons > .desktop-icon > .icon-container > img { width: 44px !important; height: 44px !important; }
.desktop-wrapper.ha-has-home:not([data-mode="Edit"]) .desktop-container > .icons-container > .icons > .desktop-icon > .icon-container:hover { transform: none; }
.desktop-wrapper.ha-has-home:not([data-mode="Edit"]) .desktop-container > .icons-container > .icons > .desktop-icon > .icon-caption {
	text-align: left !important; height: auto !important; text-wrap: wrap; min-width: 0; flex: 1 1 auto; max-width: none !important;
}
.desktop-wrapper.ha-has-home:not([data-mode="Edit"]) .desktop-container > .icons-container > .icons > .desktop-icon > .icon-caption .icon-title {
	white-space: normal !important; overflow: visible; font-size: 13.5px; line-height: 1.25;
}
.desktop-wrapper.ha-has-home[data-mode="Edit"] .ha-home { display: none; }

@media (max-width: 900px) {
	.ha-home-panels { grid-template-columns: minmax(0, 1fr); }
	.ha-home-hero { padding: 18px; }
	.ha-home-hero h2 { font-size: 19px; }
}
@media (max-width: 560px) {
	.ha-home { padding: 0 16px; margin-top: 12px; }
	.desktop-wrapper.ha-has-home .desktop-container { padding: 0 16px 32px; }
	.ha-home-hero-side { width: 100%; }
	.ha-home .ha-home-chip, .ha-home .ha-home-action { flex: 1 1 auto; justify-content: center; }
	.ha-home-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
	.ha-home-card-value { font-size: 24px; }
	.desktop-wrapper.ha-has-home:not([data-mode="Edit"]) .desktop-container > .icons-container > .icons { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
}
`;

	// last, once the styles above exist: the desk may already be on the page
	hrms_addon.home.show = arrive;
	$(document).on("page-change", arrive);
	$(arrive);
})();
