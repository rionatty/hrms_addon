// HRMS Addon — the module pages.
//
// The desk home (hrms_addon_home.js) opens on a greeting, the day's figures and
// what waits for the user; a module opened from it was Frappe's own workspace,
// in another look. This gives every module's page the home's look: a header of
// its own (the module's picture and name, the groups of its menu, where it
// falls in an employee's time with the company, what waits for the user in it
// and the document most often made there), over Frappe's own charts, lists and
// cards, drawn as the home draws its panels.
//
// Luuka, 14 Oct 2026, seeing the desk home and then a module opened from it:
// "extend the UI acuteness to the inner modules when opened".
//
// WHAT IT MUST NEVER DO
//
// Stop a module opening, or change what is on its page. Everything here is
// inside try/catch; Frappe's blocks are restyled and never rewritten, and the
// header is added beside them. While a workspace is being edited its page is
// exactly Frappe's. HRMS Addon Theme Settings > Module Pages > Standard
// switches it off without a deploy.
//
// A plain asset in app_include_js, so a change to it needs no `bench build`:
// its styles are written into the page here for the same reason.

(function () {
	if (typeof frappe === "undefined" || !frappe.boot) return;
	if (!frappe.boot.hrms_addon_module_pages) return;
	if (frappe.session && frappe.session.user === "Guest") return;
	frappe.provide("hrms_addon.module_pages");

	const METHOD = "hrms_addon.hrms_addon.module_pages.summary";
	const FRESH_MS = 60 * 1000; // how long an answer is shown before it is asked for again
	const STYLE_ID = "ha-mod-style";
	const ON = "ha-mod-on"; // on <html>: every style below holds only while it is there
	// the modules in the order of an employee's time with the company (home_rules.MODULES)
	const MODULES = Array.isArray(frappe.boot.hrms_addon_home_modules) ? frappe.boot.hrms_addon_home_modules : [];
	// the document most often made in each module (module_pages_rules.ACTIONS)
	const ACTIONS = frappe.boot.hrms_addon_module_actions || {};
	// Frappe's workspace page, and its blocks only while the workspace is not being edited
	const PAGE = 'html.ha-mod-on .page-container[data-page-route="Workspaces"]';
	const READ = PAGE + " .layout-main-section:not(.edit-mode)";
	const answers = {}; // each workspace's answer: { data, at }
	const asking = {};
	let tab = "items";

	const ICONS = {
		waiting: '<path d="M4 13.5h4l1.5 2.5h5l1.5-2.5h4"/><path d="M6.2 5.5h11.6L20 13.5V18a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18v-4.5z"/>',
		plus: '<path d="M12 5.5v13M5.5 12h13"/>',
		chevron: '<path d="M9 6l6 6-6 6"/>',
		back: '<path d="M15 6l-6 6 6 6"/>',
		folder: '<path d="M4 7.5A1.5 1.5 0 0 1 5.5 6h4l2 2.2h7A1.5 1.5 0 0 1 20 9.7v8.8a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5z"/>',
	};
	// the pictures CSS puts on Frappe's cards, white on the module's navy
	const GLYPHS = {
		links: '<path d="M9.5 7h10M9.5 12h10M9.5 17h10"/><path d="M5 7h.01M5 12h.01M5 17h.01" stroke-width="2.8"/>',
		chart: '<path d="M5 19V10M10 19V5M15 19v-7M20 19v-11"/>',
		list: '<rect x="4" y="4.5" width="16" height="15" rx="2.2"/><path d="M8 9.5h8M8 13h8M8 16.5h5"/>',
		shortcut: '<path d="M7 17L17 7M9 7h8v8"/>',
	};

	function glyph(name) {
		const svg =
			"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='#fff' stroke-width='1.8' " +
			`stroke-linecap='round' stroke-linejoin='round'>${GLYPHS[name]}</svg>`;
		return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
	}

	function icon(name) {
		return (
			'<svg class="ha-mod-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ' +
			`stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ICONS.folder}</svg>`
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

	function style() {
		if (document.getElementById(STYLE_ID)) return;
		const sheet = document.createElement("style");
		sheet.id = STYLE_ID;
		sheet.textContent = CSS;
		document.head.appendChild(sheet);
	}

	// Frappe's workspace page as it is on the screen now
	function page_now() {
		const all = Array.from(document.querySelectorAll('.page-container[data-page-route="Workspaces"]'));
		return all.find((page) => page.offsetParent !== null) || null;
	}

	// the workspace that page shows: Frappe names it as it starts drawing it (workspace.js show_page)
	function shown() {
		const page = frappe.workspace && frappe.workspace._page;
		return page && page.name ? page : null;
	}

	// the module's own menu, as the boot carries it cut down to what the user may open (boot.get_sidebar_items)
	function menu_of(name) {
		return (frappe.boot.workspace_sidebar_item || {})[String(name).toLowerCase()] || null;
	}

	// the headings of the module's menu with something under them: what the module holds
	function groups_of(name) {
		const items = ((menu_of(name) || {}).items || []).filter((item) => item && !item.hidden);
		return items
			.filter((item, index) => item.type === "Section Break" && items[index + 1] && items[index + 1].type !== "Section Break")
			.map((item) => item.label)
			.filter(Boolean);
	}

	// a module the user may open: Frappe lists it among their workspaces
	function may_open(name) {
		const pages = (frappe.boot.workspaces && frappe.boot.workspaces.pages) || [];
		return pages.length ? pages.some((page) => page.name === name) : !!menu_of(name);
	}

	// where the module falls in an employee's time with the company, and the nearest either side the user may open
	function stage_of(name) {
		const index = MODULES.indexOf(name);
		if (index < 0) return null;
		const open = MODULES.map((module) => may_open(module));
		let before = null;
		let after = null;
		for (let at = index - 1; at >= 0 && !before; at -= 1) if (open[at]) before = MODULES[at];
		for (let at = index + 1; at < MODULES.length && !after; at += 1) if (open[at]) after = MODULES[at];
		return { index: index, open: open, before: before, after: after };
	}

	// the document most often made in the module, for somebody who may make it
	function action_of(name) {
		const doctype = ACTIONS[name];
		try {
			return doctype && frappe.model.can_create(doctype) ? doctype : null;
		} catch (error) {
			return null;
		}
	}

	// what waits for the user in the module, once the server has said: null until then, or where it could not say
	function waits_of(name) {
		const answer = answers[name];
		return answer && answer.data && answer.data.waiting ? answer.data.waiting : null;
	}

	// the module's picture: the app's own round one where it ships one, else Frappe's, else the workspace's icon
	function picture(page) {
		let address = false;
		try {
			address = frappe.utils.get_desktop_icon(page.name, "solid");
		} catch (error) {
			address = false;
		}
		if (address) return `<span class="ha-mod-picture"><img src="${esc(address)}" alt=""></span>`;
		let drawn = icon("folder");
		try {
			if (page.icon) drawn = frappe.utils.icon(page.icon, "lg");
		} catch (error) {
			drawn = icon("folder");
		}
		return `<span class="ha-mod-picture ha-mod-drawn">${drawn}</span>`;
	}

	// the modules from the first to the last, this one marked, each the user may open one click away
	function track(stage) {
		const steps = MODULES.map((module, index) => {
			const now = index === stage.index;
			const state = now ? " ha-now" : index < stage.index ? " ha-done" : "";
			const label = esc(__(module));
			return stage.open[index] && !now
				? `<button type="button" class="ha-mod-step${state}" data-ha-mod="go" data-module="${esc(module)}" ` +
						`title="${label}" aria-label="${label}"></button>`
				: `<span class="ha-mod-step${state}" title="${label}"${now ? ' aria-current="step"' : ""}></span>`;
		}).join("");
		const near = (module, back) =>
			module
				? `<button type="button" class="ha-mod-near" data-ha-mod="go" data-module="${esc(module)}">` +
				  (back ? `${icon("back")}<span>${esc(__(module))}</span>` : `<span>${esc(__(module))}</span>${icon("chevron")}`) +
				  `</button>`
				: "";
		return (
			`<div class="ha-mod-track"><span class="ha-mod-steps">${steps}</span>` +
			`<span class="ha-mod-stage">${esc(__("Stage {0} of {1}", [stage.index + 1, MODULES.length]))}</span>` +
			`<span class="ha-mod-nears">${near(stage.before, true)}${near(stage.after, false)}</span></div>`
		);
	}

	function hero(page) {
		const name = page.name;
		const groups = groups_of(name);
		const stage = stage_of(name);
		const doctype = action_of(name);
		const waits = waits_of(name);
		const chip = waits
			? `<button type="button" class="ha-mod-chip" data-ha-mod="waiting">${icon("waiting")}` +
			  `<span><b>${count(waits.tasks)}</b><small>${esc(__("Waiting for you"))}</small></span></button>`
			: answers[name]
			? ""
			: `<span class="ha-mod-chip ha-mod-asking" aria-hidden="true"><span class="ha-mod-bone"></span></span>`;
		const make = doctype
			? `<button type="button" class="ha-mod-action" data-ha-mod="new">${icon("plus")}` +
			  `<span>${esc(__("New {0}", [__(doctype)]))}</span></button>`
			: "";
		return (
			`<section class="ha-mod-hero">${picture(page)}` +
			`<div class="ha-mod-hero-text"><h2>${esc(__(page.title || name))}</h2>` +
			(groups.length ? `<p>${groups.map(esc).join(" · ")}</p>` : "") +
			(stage ? track(stage) : "") +
			`</div>` +
			(chip || make ? `<div class="ha-mod-hero-side">${chip}${make}</div>` : "") +
			`</section>`
		);
	}

	function row(item, index, list) {
		const meta = [item.doctype ? __(item.doctype) : "", item.docname, item.when ? __(item.when) : ""]
			.filter(Boolean)
			.map(esc)
			.join(" · ");
		return (
			`<button type="button" class="ha-mod-row" data-ha-mod="row" data-list="${list}" data-index="${index}">` +
			`<span class="ha-mod-dot ha-band-${esc(item.band || "none")}"></span>` +
			`<span class="ha-mod-row-text"><span class="ha-mod-row-title">${esc(item.title)}</span>` +
			`<span class="ha-mod-row-meta">${meta}</span></span>${item.doctype && item.docname ? icon("chevron") : ""}</button>`
		);
	}

	// what waits for the user among the module's documents, as the desk home lists it; nothing when nothing waits
	function panel(page) {
		const waits = waits_of(page.name);
		if (!waits || !(waits.tasks || waits.unread)) return "";
		const lists = { items: waits.items || [], notes: waits.notes || [] };
		const which = lists[tab] && lists[tab].length ? tab : lists.items.length ? "items" : "notes";
		const tabs = [
			["items", __("To Do"), waits.tasks],
			["notes", __("Notifications"), waits.unread],
		]
			.map(
				([key, label, total]) =>
					`<button type="button" class="ha-mod-tab${which === key ? " ha-on" : ""}" data-ha-mod="tab" ` +
					`data-tab="${key}">${esc(label)}<i>${count(total)}</i></button>`
			)
			.join("");
		const total = which === "items" ? waits.tasks : waits.unread;
		const more =
			total > lists[which].length
				? `<div class="ha-mod-more"><button type="button" class="ha-mod-all" data-ha-mod="all" data-list="${which}">` +
				  `<span>${esc(__("See all {0}", [count(total)]))}</span>${icon("chevron")}</button></div>`
				: "";
		return (
			`<section class="ha-mod-panel"><header><span class="ha-mod-panel-icon">${icon("waiting")}</span>` +
			`<h3>${esc(__("Waiting for You"))}</h3><span class="ha-mod-tabs">${tabs}</span></header>` +
			`<div class="ha-mod-list">${lists[which].map((item, index) => row(item, index, which)).join("")}</div>` +
			`${more}</section>`
		);
	}

	// the module's header, drawn afresh only when what it shows has changed
	function redraw(force) {
		const element = page_now();
		const page = shown();
		const holder = element && element.querySelector(".layout-main-section > .ha-mod");
		if (!holder || !page) return;
		const answer = answers[page.name];
		const mark = [page.name, page.title || "", answer ? answer.at : 0, tab].join("|");
		if (!force && holder.getAttribute("data-mark") === mark) return;
		holder.setAttribute("data-mark", mark);
		holder.innerHTML = hero(page) + panel(page);
	}

	// the user's own list of what waits, kept to the module's documents
	function all(which, name) {
		const answer = answers[name];
		const doctypes = (answer && answer.data && answer.data.doctypes) || [];
		const user = frappe.session.user;
		if (which === "notes") {
			frappe.route_options = Object.assign({ for_user: user, read: 0 }, doctypes.length ? { document_type: ["in", doctypes] } : {});
			frappe.set_route("List", "Notification Log");
		} else {
			frappe.route_options = Object.assign(
				{ allocated_to: user, status: "Open" },
				doctypes.length ? { reference_type: ["in", doctypes] } : {}
			);
			frappe.set_route("List", "ToDo");
		}
	}

	// another module, opened as Frappe opens a workspace, with its own menu down the left
	function open_module(name) {
		if (!name || !may_open(name)) return;
		frappe.route_options = { sidebar: name };
		frappe.set_route(frappe.router.slug(name));
	}

	function act(element) {
		const what = element.getAttribute("data-ha-mod");
		const page = shown();
		if (!page) return;
		if (what === "go") open_module(element.getAttribute("data-module"));
		else if (what === "new") {
			const doctype = action_of(page.name);
			if (doctype) frappe.new_doc(doctype);
		} else if (what === "waiting") {
			if (element.closest(".ha-mod").querySelector(".ha-mod-panel")) {
				tab = "items";
				redraw(true);
				const list = page_now() && page_now().querySelector(".ha-mod-panel");
				if (list && list.scrollIntoView) list.scrollIntoView({ behavior: "smooth", block: "nearest" });
			} else all("items", page.name);
		} else if (what === "tab") {
			tab = element.getAttribute("data-tab") === "notes" ? "notes" : "items";
			redraw(true);
		} else if (what === "row") {
			const waits = waits_of(page.name) || {};
			const list = element.getAttribute("data-list") === "notes" ? waits.notes : waits.items;
			const item = (list || [])[Number(element.getAttribute("data-index"))];
			if (item && item.doctype && item.docname) frappe.set_route("Form", item.doctype, item.docname);
		} else if (what === "all") all(element.getAttribute("data-list"), page.name);
	}

	// where the header goes: first in Frappe's workspace body, which Frappe only ever adds its skeleton to and
	// takes it from again (workspace.js); CSS keeps the header above the skeleton
	function mount(element) {
		const body = element.querySelector(".layout-main-section");
		if (!body) return null;
		let holder = body.querySelector(":scope > .ha-mod");
		if (!holder) {
			holder = document.createElement("div");
			holder.className = "ha-mod";
			body.insertBefore(holder, body.firstChild);
			holder.addEventListener("click", (event) => {
				const target = event.target.closest("[data-ha-mod]");
				if (!target) return;
				try {
					act(target);
				} catch (error) {
					console.error(error);
				}
			});
		}
		return holder;
	}

	function load(name) {
		const answer = answers[name];
		if (asking[name] || (answer && Date.now() - answer.at < FRESH_MS)) return;
		asking[name] = true;
		// fetch, not frappe.call: a call that fails must leave the module alone, and frappe.call would open
		// Frappe's Server Error dialog over it
		fetch("/api/method/" + METHOD + "?workspace=" + encodeURIComponent(name), {
			credentials: "same-origin",
			cache: "no-store",
			headers: { Accept: "application/json" },
		})
			.then((response) => (response.ok ? response.json() : null))
			.then((r) => (r && r.message) || null)
			.catch(() => null)
			.then((data) => {
				// one that failed keeps what was shown before, and is asked again later, not at once
				answers[name] = { data: data || (answer && answer.data) || null, at: Date.now() };
				asking[name] = false;
				redraw(false);
			});
	}

	function show() {
		try {
			const element = page_now();
			const page = shown();
			if (!element || !page) return false;
			if (!mount(element)) return false;
			redraw(false);
			load(page.name);
			return true;
		} catch (error) {
			console.error(error);
			return true; // do not keep trying something that throws
		}
	}

	function on_workspace() {
		try {
			return (frappe.get_route() || [])[0] === "Workspaces";
		} catch (e) {
			return false;
		}
	}

	// Frappe says "page-change" first and names the workspace it shows a moment after, as it starts drawing it:
	// look a few times, each time drawing the header for whichever workspace is shown, then leave it
	function arrive() {
		if (!on_workspace()) return;
		let tries = 0;
		const look = () => {
			tries += 1;
			const there = show();
			if (tries < 10 && (!there || tries < 4)) setTimeout(look, 120 * tries);
		};
		look();
	}

	const CSS = `
/* the module page's own values: the desk home's */
${PAGE} {
	--ha-m-navy: var(--hra-primary, #14395E);
	--ha-m-deep: var(--hra-primary-dark, #0A2540);
	--ha-m-mid: var(--hra-primary-mid, #2A5A8C);
	--ha-m-gold: #EAA51A;
	--ha-m-line: var(--hra-border, #D7DEEA);
	--ha-m-ink: var(--text-color, #1E2A3A);
	--ha-m-muted: var(--text-muted, #5C6B82);
	--ha-m-card: var(--card-bg, #fff);
	--ha-m-wash: color-mix(in srgb, var(--ha-m-navy) 6%, transparent);
}
html.ha-mod-on[data-theme="dark"] .page-container[data-page-route="Workspaces"] { --ha-m-line: var(--border-color, #343B46); }

/* one canvas from the head of the page to its foot, the desk home's */
html.ha-mod-on:not([data-theme="dark"]) .page-container[data-page-route="Workspaces"],
html.ha-mod-on:not([data-theme="dark"]) .page-container[data-page-route="Workspaces"] .page-head,
html.ha-mod-on:not([data-theme="dark"]) .page-container[data-page-route="Workspaces"] .page-head-content {
	background: var(--hra-wash, #F5F8FC) !important;
}
${PAGE} .page-head { border-bottom: 0 !important; box-shadow: none !important; }

/* the header first, above Frappe's loading skeleton too, in line with the cards; gone while the workspace is edited */
${PAGE} .layout-main-section:not(.edit-mode) { display: flex; flex-direction: column; }
${PAGE} .layout-main-section > .ha-mod { order: -1; margin: 2px 3px 0; }
${PAGE} .layout-main-section.edit-mode > .ha-mod { display: none; }

.ha-mod { font-feature-settings: "tnum"; }
.ha-mod * { box-sizing: border-box; }
.ha-mod button { font: inherit; color: inherit; background: none; border: 0; padding: 0; text-align: left; cursor: pointer; }
.ha-mod-icon { width: 18px; height: 18px; flex: none; }

/* the header: the module's picture and name, its groups, its place among the modules */
.ha-mod-hero {
	display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
	padding: 20px 24px; border-radius: 18px; color: #fff; position: relative; overflow: hidden;
	background:
		radial-gradient(520px 220px at 88% -30%, rgba(234,165,26,.26), transparent 62%),
		radial-gradient(420px 260px at 8% 130%, rgba(255,255,255,.10), transparent 60%),
		linear-gradient(118deg, var(--ha-m-deep) 0%, var(--ha-m-navy) 52%, var(--ha-m-mid) 100%);
	box-shadow: 0 10px 28px rgba(10,37,64,.20);
}
.ha-mod-hero::after {
	content: ""; position: absolute; right: -60px; top: -80px; width: 260px; height: 260px; border-radius: 50%;
	border: 1px solid rgba(255,255,255,.10); box-shadow: 0 0 0 38px rgba(255,255,255,.035), 0 0 0 86px rgba(255,255,255,.025);
	pointer-events: none;
}
.ha-mod-picture {
	width: 58px; height: 58px; border-radius: 50%; flex: none; display: grid; place-items: center; position: relative; z-index: 1;
	box-shadow: 0 0 0 5px rgba(255,255,255,.07), 0 8px 18px rgba(0,0,0,.18);
}
.ha-mod-picture > img { width: 58px; height: 58px; border-radius: 50%; display: block; object-fit: cover; }
.ha-mod-picture.ha-mod-drawn { background: rgba(255,255,255,.10); box-shadow: inset 0 0 0 2px var(--ha-m-gold), 0 0 0 5px rgba(255,255,255,.06); }
.ha-mod-picture.ha-mod-drawn > svg { width: 26px; height: 26px; color: #fff; stroke: #fff; --icon-stroke: #fff; --icon-fill: none; }
.ha-mod-hero-text { flex: 1 1 300px; min-width: 0; position: relative; z-index: 1; }
.ha-mod-hero h2 { margin: 0; font-size: 22px; line-height: 1.25; font-weight: 700; letter-spacing: -.01em; color: #fff; }
.ha-mod-hero p { margin: 4px 0 0; font-size: 13px; color: rgba(255,255,255,.80); }
.ha-mod-track { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 12px; margin-top: 12px; }
.ha-mod-steps { display: inline-flex; align-items: center; gap: 3px; }
.ha-mod .ha-mod-step { width: 20px; height: 16px; display: grid; place-items: center; border-radius: 6px; }
.ha-mod .ha-mod-step::before { content: ""; width: 100%; height: 5px; border-radius: 99px; background: rgba(255,255,255,.22); transition: background .12s ease; }
.ha-mod .ha-mod-step.ha-done::before { background: rgba(255,255,255,.55); }
.ha-mod .ha-mod-step.ha-now { width: 32px; }
.ha-mod .ha-mod-step.ha-now::before { background: var(--ha-m-gold); box-shadow: 0 0 0 3px rgba(234,165,26,.22); }
.ha-mod button.ha-mod-step:hover::before, .ha-mod button.ha-mod-step:focus-visible::before { background: #fff; }
.ha-mod button.ha-mod-step:focus-visible { outline: none; }
.ha-mod span.ha-mod-step:not(.ha-now) { opacity: .5; }
.ha-mod-stage { font-size: 12px; font-weight: 600; color: rgba(255,255,255,.82); }
.ha-mod-nears { display: inline-flex; gap: 6px; flex-wrap: wrap; }
.ha-mod .ha-mod-near {
	display: inline-flex; align-items: center; gap: 4px; padding: 3px 9px; border-radius: 8px; font-size: 12px;
	color: rgba(255,255,255,.92); background: rgba(255,255,255,.08); transition: background .12s ease;
}
.ha-mod .ha-mod-near:hover, .ha-mod .ha-mod-near:focus-visible { background: rgba(255,255,255,.17); color: #fff; outline: none; }
.ha-mod .ha-mod-near .ha-mod-icon { width: 14px; height: 14px; }
.ha-mod-hero-side { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; position: relative; z-index: 1; }
.ha-mod .ha-mod-chip {
	display: flex; align-items: center; gap: 10px; padding: 9px 14px; border-radius: 12px; color: #fff; min-height: 50px;
	background: rgba(255,255,255,.09); box-shadow: inset 0 0 0 1px rgba(255,255,255,.20); transition: background .12s ease;
}
.ha-mod button.ha-mod-chip:hover, .ha-mod button.ha-mod-chip:focus-visible { background: rgba(255,255,255,.16); outline: none; }
.ha-mod-chip > span { display: flex; flex-direction: column; line-height: 1.15; }
.ha-mod-chip b { font-size: 17px; font-weight: 700; }
.ha-mod-chip small { font-size: 11.5px; color: rgba(255,255,255,.82); }
.ha-mod-chip .ha-mod-icon { color: var(--ha-m-gold); }
.ha-mod .ha-mod-chip.ha-mod-asking { width: 140px; }
.ha-mod .ha-mod-action {
	display: inline-flex; align-items: center; gap: 8px; padding: 11px 18px; border-radius: 12px;
	background: var(--ha-m-gold); color: #1B2434; font-weight: 700; font-size: 13.5px;
	box-shadow: 0 6px 16px rgba(234,165,26,.32); transition: transform .12s ease, filter .12s ease;
}
.ha-mod .ha-mod-action:hover, .ha-mod .ha-mod-action:focus-visible { filter: brightness(1.06); transform: translateY(-1px); outline: none; }
.ha-mod-bone { display: block; height: 12px; width: 100%; border-radius: 6px; background: linear-gradient(90deg, rgba(255,255,255,.14), rgba(255,255,255,.30), rgba(255,255,255,.14)); background-size: 200% 100%; animation: ha-mod-shine 1.3s linear infinite; }
@keyframes ha-mod-shine { from { background-position: 200% 0; } to { background-position: -200% 0; } }

/* what waits for the user in the module */
.ha-mod-panel { margin-top: 14px; background: var(--ha-m-card); border: 1px solid var(--ha-m-line); border-radius: 14px; }
.ha-mod-panel header { display: flex; align-items: center; gap: 10px; padding: 13px 16px; border-bottom: 1px solid var(--ha-m-line); flex-wrap: wrap; }
.ha-mod-panel h3 { margin: 0; font-size: 14.5px; font-weight: 700; color: var(--ha-m-ink); flex: 1 1 auto; }
.ha-mod-panel-icon { width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center; color: #fff; background: var(--ha-m-navy); flex: none; }
.ha-mod-tabs { display: inline-flex; gap: 2px; padding: 3px; border-radius: 10px; background: color-mix(in srgb, var(--ha-m-navy) 7%, transparent); }
.ha-mod .ha-mod-tab { padding: 5px 11px; border-radius: 8px; font-size: 12.5px; font-weight: 600; color: var(--ha-m-muted); display: inline-flex; gap: 6px; align-items: center; }
.ha-mod .ha-mod-tab i { font-style: normal; font-size: 11px; padding: 1px 6px; border-radius: 99px; background: color-mix(in srgb, var(--ha-m-navy) 10%, transparent); }
.ha-mod .ha-mod-tab.ha-on { background: var(--ha-m-card); color: var(--ha-m-ink); box-shadow: 0 1px 3px rgba(20,57,94,.16); }
.ha-mod-list { padding: 4px 6px 6px; }
.ha-mod .ha-mod-row { display: flex; align-items: center; gap: 11px; width: 100%; padding: 10px; border-radius: 10px; color: var(--ha-m-muted); transition: background .12s ease; }
.ha-mod .ha-mod-row:hover, .ha-mod .ha-mod-row:focus-visible { background: var(--ha-m-wash); outline: none; }
.ha-mod-row-text { display: flex; flex-direction: column; gap: 1px; flex: 1 1 auto; min-width: 0; }
.ha-mod-row-title { font-size: 13.5px; font-weight: 600; color: var(--ha-m-ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ha-mod-row-meta { font-size: 12px; color: var(--ha-m-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ha-mod-dot { width: 9px; height: 9px; border-radius: 50%; flex: none; background: #9AA8BC; }
.ha-mod-dot.ha-band-overdue { background: #D5475B; box-shadow: 0 0 0 3px rgba(213,71,91,.16); }
.ha-mod-dot.ha-band-today { background: #D98A12; box-shadow: 0 0 0 3px rgba(217,138,18,.16); }
.ha-mod-dot.ha-band-soon, .ha-mod-dot.ha-band-later { background: #2F7BD1; }
.ha-mod-dot.ha-band-good { background: #1F9D6B; }
.ha-mod-more { display: flex; justify-content: flex-end; padding: 0 10px 10px; }
.ha-mod .ha-mod-all { display: inline-flex; align-items: center; gap: 4px; padding: 6px 10px; border-radius: 8px; font-size: 12.5px; font-weight: 600; color: var(--ha-m-mid); }
.ha-mod .ha-mod-all:hover, .ha-mod .ha-mod-all:focus-visible { background: var(--ha-m-wash); outline: none; }
.ha-mod .ha-mod-all .ha-mod-icon { width: 14px; height: 14px; }

/* Frappe's own blocks as the desk home draws its panels: white cards on the canvas, a heading with a picture
   over each, and rows rather than links. Only while the workspace is not being edited, and only Frappe's card
   kinds by name: a bare .widget is also each heading and spacer of the page. */
${READ} .widget.links-widget-box,
${READ} .widget.shortcut-widget-box,
${READ} .widget.number-widget-box,
${READ} .widget.dashboard-widget-box,
${READ} .widget.quick-list-widget-box {
	background: var(--ha-m-card) !important; border: 1px solid var(--ha-m-line) !important; border-radius: 14px !important;
	box-shadow: none !important;
}
${READ} .widget.links-widget-box,
${READ} .widget.dashboard-widget-box,
${READ} .widget.quick-list-widget-box { padding: 0 !important; }
${READ} .widget.links-widget-box > .widget-head,
${READ} .widget.dashboard-widget-box > .widget-head,
${READ} .widget.quick-list-widget-box > .widget-head {
	min-height: 56px; padding: 12px 14px 12px 16px !important; border-bottom: 1px solid var(--ha-m-line); gap: 10px; align-items: center;
}
${READ} .widget.links-widget-box > .widget-head .widget-title,
${READ} .widget.dashboard-widget-box > .widget-head .widget-title,
${READ} .widget.quick-list-widget-box > .widget-head .widget-title {
	gap: 10px; font-size: 14.5px !important; font-weight: 700 !important; line-height: 1.3 !important; color: var(--ha-m-ink) !important;
	text-transform: none !important; letter-spacing: 0 !important;
}
${READ} .widget.links-widget-box > .widget-head .widget-title::before,
${READ} .widget.dashboard-widget-box > .widget-head .widget-title::before,
${READ} .widget.quick-list-widget-box > .widget-head .widget-title::before {
	content: ""; flex: none; width: 30px; height: 30px; border-radius: 9px; background: var(--ha-m-navy) center / 17px 17px no-repeat;
}
${READ} .widget.links-widget-box > .widget-head .widget-title::before { background-image: ${glyph("links")}; }
${READ} .widget.dashboard-widget-box > .widget-head .widget-title::before { background-image: ${glyph("chart")}; }
${READ} .widget.quick-list-widget-box > .widget-head .widget-title::before { background-image: ${glyph("list")}; }

/* a card of links: each a row that opens what it names */
${READ} .widget.links-widget-box > .widget-body { padding: 6px 6px 8px !important; }
${READ} .widget.links-widget-box .link-item {
	display: flex !important; align-items: center; gap: 10px; margin: 0 !important; padding: 9px 10px !important;
	border-radius: 10px !important; font-size: 13.5px !important; font-weight: 500 !important; line-height: 1.3 !important;
	color: var(--ha-m-ink) !important; text-decoration: none !important; transition: background .12s ease, color .12s ease;
}
${READ} .widget.links-widget-box .link-item:hover,
${READ} .widget.links-widget-box .link-item:focus-visible {
	background: var(--ha-m-wash) !important; color: var(--ha-m-navy) !important; text-decoration: none !important; outline: none;
}
${READ} .widget.links-widget-box .link-item .link-content { flex: 1 1 auto; min-width: 0; color: inherit !important; }
${READ} .widget.links-widget-box .link-item .link-content > svg { display: none; }
${READ} .widget.links-widget-box .link-item::after {
	content: ""; flex: none; width: 7px; height: 7px; margin-right: 5px; border-top: 1.6px solid currentColor;
	border-right: 1.6px solid currentColor; transform: rotate(45deg); opacity: .45;
}
${READ} .widget.links-widget-box .link-item.disabled-link,
${READ} .widget.links-widget-box .link-item .disabled-link { color: var(--ha-m-muted) !important; }

/* a chart: its own controls quiet beside the heading */
${READ} .widget.dashboard-widget-box > .widget-head .widget-subtitle { margin-top: 2px; font-size: 12px; color: var(--ha-m-muted) !important; }
${READ} .widget.dashboard-widget-box > .widget-body { padding: 10px 14px 6px !important; }
${READ} .widget.dashboard-widget-box .widget-control .btn {
	border: 0 !important; border-radius: 8px !important; background: var(--ha-m-wash) !important; color: var(--ha-m-ink) !important;
}
${READ} .widget.dashboard-widget-box .chart-loading-state {
	border-radius: 10px !important; background: color-mix(in srgb, var(--ha-m-navy) 4%, transparent) !important; color: var(--ha-m-muted) !important;
}

/* a list of documents: rows as the home's, an empty one said quietly, and the way to the whole list beneath */
${READ} .widget.quick-list-widget-box > .widget-head .widget-label { padding-left: 0 !important; }
${READ} .widget.quick-list-widget-box > .widget-body { margin: 0 !important; padding: 6px !important; min-height: 0 !important; }
${READ} .widget.quick-list-widget-box .quick-list-item {
	gap: 10px; margin: 0 !important; padding: 9px 10px !important; border-radius: 10px !important; transition: background .12s ease;
}
${READ} .widget.quick-list-widget-box .quick-list-item:hover { background: var(--ha-m-wash) !important; }
${READ} .widget.quick-list-widget-box .quick-list-item .title { font-size: 13.5px; font-weight: 600; color: var(--ha-m-ink); }
${READ} .widget.quick-list-widget-box .quick-list-item .timestamp { font-size: 12px !important; color: var(--ha-m-muted) !important; }
${READ} .widget.quick-list-widget-box .list-loading-state,
${READ} .widget.quick-list-widget-box .list-no-data-state {
	height: auto !important; min-height: 132px; padding: 24px 12px; font-size: 13px; color: var(--ha-m-muted) !important;
}
${READ} .widget.quick-list-widget-box > .widget-footer { display: flex; justify-content: flex-end; padding: 0 10px 10px; }
${READ} .widget.quick-list-widget-box .see-all {
	display: inline-flex !important; align-items: center; gap: 7px; width: auto !important; height: auto !important;
	padding: 6px 10px !important; border-radius: 8px !important; background: none !important; box-shadow: none !important;
	font-size: 12.5px !important; font-weight: 600 !important; color: var(--ha-m-mid) !important;
}
${READ} .widget.quick-list-widget-box .see-all:hover { background: var(--ha-m-wash) !important; }
${READ} .widget.quick-list-widget-box .see-all::after {
	content: ""; width: 6px; height: 6px; border-top: 1.6px solid currentColor; border-right: 1.6px solid currentColor; transform: rotate(45deg);
}

/* a figure: the desk home's card, its band across the top */
${READ} .widget.number-widget-box {
	padding: 16px 18px 14px !important; box-shadow: inset 0 3px 0 var(--ha-m-navy) !important;
	transition: transform .12s ease, box-shadow .12s ease !important;
}
${READ} .widget.number-widget-box:hover {
	transform: translateY(-2px) !important; box-shadow: inset 0 3px 0 var(--ha-m-navy), 0 10px 22px rgba(20,57,94,.12) !important;
}
${READ} .widget.number-widget-box .widget-head .widget-title {
	font-size: 12.5px !important; font-weight: 600 !important; color: var(--ha-m-muted) !important; text-transform: none !important; letter-spacing: 0 !important;
}
${READ} .widget.number-widget-box .widget-content { padding-top: 8px !important; }
${READ} .widget.number-widget-box .widget-content .number {
	font-size: 28px !important; font-weight: 700 !important; line-height: 1.15 !important; letter-spacing: -.02em; color: var(--ha-m-ink) !important;
}

/* a shortcut: a row of its own, its count beside it */
${READ} .widget.shortcut-widget-box {
	padding: 12px 14px !important; transition: border-color .12s ease, box-shadow .12s ease, transform .12s ease !important;
}
${READ} .widget.shortcut-widget-box:hover {
	border-color: color-mix(in srgb, var(--ha-m-navy) 35%, var(--ha-m-line)) !important; box-shadow: 0 8px 18px rgba(20,57,94,.10) !important;
	transform: translateY(-1px) !important;
}
${READ} .widget.shortcut-widget-box .widget-head .widget-title {
	gap: 10px; font-size: 13.5px !important; font-weight: 600 !important; color: var(--ha-m-ink) !important;
}
${READ} .widget.shortcut-widget-box .widget-head .widget-title::before {
	content: ""; flex: none; width: 28px; height: 28px; border-radius: 8px; background: var(--ha-m-navy) ${glyph("shortcut")} center / 15px 15px no-repeat;
}
${READ} .widget.shortcut-widget-box .widget-control > svg { display: none; }
${READ} .widget.shortcut-widget-box .indicator-pill { border-radius: 99px !important; font-weight: 600; }

/* a heading between the blocks: the desk's gold mark, and a rule to the edge */
${READ} .ce-block .ce-header { display: flex !important; align-items: center; gap: 10px; padding-top: 10px; color: var(--ha-m-ink) !important; }
${READ} .ce-block .ce-header::before { content: ""; flex: none; width: 4px; height: 18px; border-radius: 4px; background: var(--ha-m-gold); }
${READ} .ce-block .ce-header::after { content: ""; flex: 1 1 auto; height: 1px; background: var(--ha-m-line); }
${READ} .ce-block .ce-header .h4,
${READ} .ce-block .ce-header .h5,
${READ} .ce-block .ce-header span,
${READ} .ce-block .ce-header b {
	font-size: 15.5px !important; font-weight: 700 !important; line-height: 1.3 !important; color: var(--ha-m-ink) !important;
	text-transform: none !important; letter-spacing: -.005em !important;
}
${READ} .ce-block .ce-paragraph { color: var(--ha-m-muted) !important; }
/* a spacer is a widget a pixel tall in the card's colour, drawn past the page's edges: a stray line on the canvas */
${READ} .widget.spacer { background: transparent !important; }

@media (prefers-reduced-motion: reduce) { .ha-mod-bone { animation: none; } .ha-mod * { transition: none !important; } }
@media (max-width: 900px) {
	.ha-mod-hero { padding: 18px; }
	.ha-mod-hero h2 { font-size: 19px; }
}
@media (max-width: 560px) {
	.ha-mod-hero { gap: 14px; }
	.ha-mod-picture, .ha-mod-picture > img { width: 48px; height: 48px; }
	.ha-mod-hero-text { flex-basis: 200px; }
	.ha-mod-hero-side { width: 100%; }
	.ha-mod .ha-mod-chip, .ha-mod .ha-mod-action { flex: 1 1 auto; justify-content: center; }
}
`;

	// last, once the styles above exist: on <html> at once, so a workspace is never seen in another look first
	try {
		style();
		document.documentElement.classList.add(ON);
	} catch (error) {
		console.error(error);
	}
	hrms_addon.module_pages.show = arrive;
	$(document).on("page-change", arrive);
	$(arrive);
})();
