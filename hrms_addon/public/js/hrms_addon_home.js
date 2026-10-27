// HRMS Addon — the desk home.
//
// Frappe v16's desk opens on a page of module tiles and nothing else. This
// puts a home beside them, on that same page: a greeting, the figures that
// matter today, what waits for the logged-in user, and the pages they open
// most (hrms_addon/hrms_addon/home.py fills it in one call). The tiles stay
// Frappe's own, drawn as a list of modules down the left in the order of an
// employee's time with the company, so search, the notifications, the avatar
// menu and editing the desktop all work as before.
//
// Luuka, 13 Oct 2026: "the current desk is not that appealing and executive",
// and, seeing it live, "put the modules on the left side vertically in
// chronological order starting with recruitment all the way to exit".
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
//
// THE TABS
//
// Above what the home shows, a tab for each HR module the user's work is
// about (dashboards_rules.py): Overview is the home as it was, and each
// module's tab has its figures, what needs attention in it, its charts and
// lists, and the reports a decision is made from, read as the tab is first
// opened (dashboards.py). Luuka, 27 Oct 2026, of the ERPNext desk's module
// tabs: "create such dashboards for every module be smart", "but for HR
// specific". The tab last opened is the one the desk opens on, and a module
// page's Dashboard button opens the desk on that module's.

(function () {
	if (typeof frappe === "undefined" || !frappe.boot) return;
	if (!frappe.boot.hrms_addon_home) return;
	if (frappe.session && frappe.session.user === "Guest") return;
	frappe.provide("hrms_addon.home");

	const METHOD = "hrms_addon.hrms_addon.home.summary";
	// the figures of one part of the home, the overview's panels or a module's tab, asked for as it is opened
	// (dashboards.py)
	const FIGURES_METHOD = "hrms_addon.hrms_addon.dashboards.figures";
	const FRESH_MS = 60 * 1000; // how long an answer is shown before it is asked for again
	const STYLE_ID = "ha-home-style";
	// the tab last opened, remembered in this browser
	const TAB_KEY = "hrms_addon:home_tab";
	const OVERVIEW = "overview";
	// how many colours a ring of parts takes in turn (the --ha-slice-* of the styles)
	const SLICES = 7;
	// the modules in the order of an employee's time with the company (home_rules.MODULES)
	const MODULES = Array.isArray(frappe.boot.hrms_addon_home_modules) ? frappe.boot.hrms_addon_home_modules : [];
	// Frappe's tiles on the desk itself, and never while the desk is being edited
	const RAIL = '.desktop-wrapper.ha-has-home:not([data-mode="Edit"]) > .desktop-container';
	const TILES = RAIL + " > .icons-container > .icons";
	// how far in a padded page may hold the desk and still be drawn out to the window's edges
	const MOST_INSET = 64;
	// what bleed() measures and CSS reads
	const MEASURED = ["--ha-bleed-l", "--ha-bleed-r", "--ha-bleed-t", "--ha-bleed-b"];
	let answer = null;
	let asked_at = 0;
	let asking = false;
	// each part's figures as the server read them, by tab: {cards, panels, badges, at, currency, time}
	const parts = {};
	const parts_asking = {};
	let current = OVERVIEW; // the tab open now
	let requested = null; // a tab a module page's Dashboard button asked for, until it is opened
	let tab = "items"; // the list open in Waiting for You
	let open_module = null; // the module whose own menu is open in the list
	const shown_groups = new Set(); // the headings of a module's menu that are open, as "module|heading"

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
		page: '<path d="M5 19V9M10 19V5M15 19v-7M20 19v-11"/>',
		// the panels under what waits (home_panels.py)
		payroll: '<rect x="3.5" y="6.5" width="17" height="11" rx="2"/><circle cx="12" cy="12" r="2.4"/><path d="M6.5 9.5v5M17.5 9.5v5"/>',
		plants: '<path d="M3.5 20h17M5 20V10.5l4.5 2.8v-2.8l4.5 2.8V7l5 3v10"/>',
		output: '<circle cx="9" cy="12" r="5.5"/><circle cx="9" cy="12" r="1.6"/><path d="M9 17.5h11M20 17.5V14"/>',
		movement: '<path d="M7.5 18V6M4.5 9l3-3 3 3M16.5 6v12M13.5 15l3 3 3-3"/>',
		deadlines: '<circle cx="12" cy="13" r="7"/><path d="M12 9.5V13l2.5 1.6M9.5 3.5h5"/>',
		recruitment: '<circle cx="10.5" cy="10.5" r="5.5"/><path d="M14.5 14.5l5 5M8 10.5h5M10.5 8v5"/>',
		data_health: '<path d="M12 3.5l7 3v5.2c0 4.3-3 7.7-7 8.8-4-1.1-7-4.5-7-8.8V6.5z"/><path d="M8.8 12.2l2.2 2.2 4.2-4.4"/>',
		// a step of Payroll Readiness, by where it stands
		done: '<path d="M6.5 12.5l3.5 3.5 7.5-8"/>',
		open: '<circle cx="12" cy="12" r="7.5"/><path d="M12 8.2V12l2.6 1.6"/>',
		late: '<circle cx="12" cy="12" r="8"/><path d="M12 7.5v5.5M12 16.2v.3"/>',
		todo: '<circle cx="12" cy="12" r="7.5"/>',
		up: '<path d="M7 14l5-5 5 5"/>',
		down: '<path d="M7 10l5 5 5-5"/>',
		// the tabs (dashboards_rules.TABS)
		overview:
			'<rect x="4" y="4" width="7" height="7" rx="1.6"/><rect x="13" y="4" width="7" height="7" rx="1.6"/>' +
			'<rect x="4" y="13" width="7" height="7" rx="1.6"/><rect x="13" y="13" width="7" height="7" rx="1.6"/>',
		attendance:
			'<rect x="4" y="5.5" width="16" height="14.5" rx="2.2"/><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4M9 14.8l2 2 4-4"/>',
		leave:
			'<circle cx="12" cy="12" r="3.6"/><path d="M12 3.5v2.3M12 18.2v2.3M3.5 12h2.3M18.2 12h2.3M6 6l1.6 1.6M16.4 16.4L18 18' +
			'M6 18l1.6-1.6M16.4 7.6L18 6"/>',
		loans: '<path d="M4 10l8-5 8 5"/><path d="M6 10v7M10 10v7M14 10v7M18 10v7M4 19.5h16"/>',
		expenses:
			'<path d="M6.5 3.5h11v17l-2.2-1.5-2.1 1.5-2.2-1.5-2.2 1.5-2.3-1.5z"/><path d="M9 8h6M9 11.5h6M9 15h3.5"/>',
		performance: '<path d="M4 19.5h16"/><path d="M6.5 15.5l4-4 3 3 5-6"/><path d="M15 8.5h3.5V12"/>',
		training: '<path d="M3 9.5l9-4.5 9 4.5-9 4.5z"/><path d="M7 11.5v4c0 1.4 2.2 2.5 5 2.5s5-1.1 5-2.5v-4M21 9.5v5"/>',
		relations: '<path d="M12 4v16M7.5 20h9M5 7.5h14"/><path d="M5 7.5l-2.5 6h5zM19 7.5l-2.5 6h5z"/>',
		tenure: '<path d="M13.5 4.5H6.5v15h7"/><path d="M10.5 12h9M16.5 9l3 3-3 3"/>',
		// on a module's tab
		attention: '<path d="M12 4l9 16H3z"/><path d="M12 10v4.2M12 17.2v.3"/>',
		reports:
			'<path d="M7 3.5h7l4 4V19a1.5 1.5 0 0 1-1.5 1.5h-9.5A1.5 1.5 0 0 1 5.5 19V5A1.5 1.5 0 0 1 7 3.5z"/>' +
			'<path d="M9 13.5v3M12 11v5.5M15 14.5v2"/>',
		refresh: '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4.5v4h-4"/>',
		trend: '<path d="M4 19.5h16"/><path d="M6.5 16V12M10.5 16V8.5M14.5 16v-5M18.5 16V6"/>',
		ring: '<circle cx="12" cy="12" r="7.5"/><path d="M12 4.5V12l5.3 5.3"/>',
		money: '<rect x="3.5" y="6.5" width="17" height="11" rx="2"/><circle cx="12" cy="12" r="2.4"/>',
		clock: '<circle cx="12" cy="12" r="8"/><path d="M12 7.5V12l3 2"/>',
	};
	// the cards of a manager's and an employee's desk, drawn with the pictures of HR's
	const SAME_AS = {
		team: "employees",
		team_in: "on_site",
		team_leave: "on_leave",
		leave_left: "on_leave",
		present: "on_site",
		requests: "contracts",
		calendar: "on_leave",
	};

	function icon(name) {
		return (
			'<svg class="ha-home-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ' +
			`stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ICONS[SAME_AS[name]] || ICONS.page}</svg>`
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

	// a sum of money as the panels write it: its currency, then the figure shortened (84.7M)
	function money(value, currency) {
		const number = Number(value) || 0;
		let figure;
		try {
			figure = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(number);
		} catch (e) {
			figure = count(Math.round(number));
		}
		return (currency ? currency + " " : "") + figure;
	}

	// hours, to a tenth where they are not whole
	function hours(value) {
		return count(Math.round((Number(value) || 0) * 10) / 10) + " h";
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

	// Frappe keeps its own order of the tiles, in the page and while the desk is
	// edited; CSS shows them in ours. A tile that is not one of the modules named
	// keeps Frappe's place, after them.
	function order_rules() {
		// window.CSS: the styles below are a constant named CSS in this script
		const escape = window.CSS && window.CSS.escape;
		if (!escape) return "";
		return MODULES.map(
			(label, index) => `\n${TILES} > .desktop-icon[data-id=${escape(String(label))}] { order: ${index + 1}; }`
		).join("");
	}

	function style() {
		if (document.getElementById(STYLE_ID)) return;
		const sheet = document.createElement("style");
		sheet.id = STYLE_ID;
		sheet.textContent = CSS + order_rules();
		document.head.appendChild(sheet);
	}

	// Frappe's desk page as it is on the screen now. Frappe empties and draws it again every time the page is
	// shown (desktop.js: on_page_show -> make), so what was put on it before is gone and it is looked for afresh.
	function desk() {
		const all = Array.from(document.querySelectorAll(".desktop-wrapper"));
		return all.find((wrapper) => wrapper.offsetParent !== null) || all[0] || null;
	}

	// whether the home is on that desk already
	function present() {
		const wrapper = desk();
		const home = wrapper && wrapper.querySelector(".ha-home");
		return !!(home && home.childElementCount && wrapper.classList.contains("ha-has-home"));
	}

	// where the home goes: inside Frappe's desk page, before its tiles
	function mount() {
		const wrapper = desk();
		const tiles = wrapper && wrapper.querySelector(".desktop-container");
		if (!wrapper || !tiles) return null;
		let home = wrapper.querySelector(".ha-home");
		if (!home) {
			home = document.createElement("div");
			home.className = "ha-home";
			wrapper.insertBefore(home, tiles);
			wrapper.classList.add("ha-has-home");
		}
		// the heading of the list of modules, which CSS writes above Frappe's tiles
		wrapper.style.setProperty("--ha-rail-title", JSON.stringify(__("Modules")));
		bleed(wrapper);
		menus(wrapper);
		return home;
	}

	// The page Frappe puts the desk in is padded, so the navbar stopped short of the window's edges and the
	// home sat in from them. How far in the desk sits is measured, and CSS draws it out by that much; at the
	// foot too, so the padding under it does not lengthen the page and push the list of modules up under the
	// navbar at its end. Past MOST_INSET something else holds it (a sidebar), and on that side it is left
	// where it is.
	function bleed(wrapper) {
		try {
			MEASURED.forEach((name) => wrapper.style.removeProperty(name));
			const box = wrapper.getBoundingClientRect();
			if (!box.width) return;
			// what the desk may be drawn out to: the pane that scrolls, whose scrollbar it must stop at, or
			// something inside the pane that would cut off whatever is drawn past it
			const pane = wrapper.closest(".main-section");
			let frame = pane;
			let holder = wrapper; // the part of the frame that holds the desk
			for (let node = wrapper.parentElement; node && node !== pane && node !== document.body; node = node.parentElement) {
				const cut = getComputedStyle(node);
				if (cut.overflowX !== "visible" || cut.overflowY !== "visible") {
					frame = node;
					break;
				}
				holder = node;
			}
			const edge = frame ? frame.getBoundingClientRect() : null;
			const left = frame ? edge.left + frame.clientLeft : -window.scrollX;
			const top = frame ? edge.top + frame.clientTop - frame.scrollTop : -window.scrollY;
			const width = (frame || document.documentElement).clientWidth;
			// the top from the desk's own page: what Frappe shows above the page (its navbar, until the desk hides
			// it a moment after it is drawn; an announcement) is not the page's padding
			const page = wrapper.closest(".page-container");
			const inset = {
				l: box.left - left,
				r: left + width - box.right,
				t: box.top - Math.max(top, page ? page.getBoundingClientRect().top : top),
				b: holder.getBoundingClientRect().bottom - box.bottom,
			};
			Object.keys(inset).forEach((side) => {
				const drawn_out = inset[side] > 0.5 && inset[side] <= MOST_INSET;
				wrapper.style.setProperty("--ha-bleed-" + side, (drawn_out ? Math.round(inset[side]) : 0) + "px");
			});
		} catch (error) {
			console.error(error);
		}
	}

	// where an entry of a module's menu goes, as Frappe's own sidebar works it out (sidebar_item.js get_path)
	function path_of(item) {
		try {
			if (item.link_type === "URL") return item.url || null;
			if (item.link_type === "Workspace") {
				if (item.route) return item.route;
				const slug = frappe.router.slug(item.link_to);
				const workspace = (frappe.workspaces || {})[slug];
				return (workspace && workspace.public ? "/desk/" : "/desk/private/") + slug;
			}
			const args = { type: item.link_type, name: item.link_to };
			if (item.link_type === "Report") {
				if (!item.report) return null;
				args.is_query_report =
					item.report.report_type === "Query Report" || item.report.report_type === "Script Report";
				args.report_ref_doctype = item.report.ref_doctype;
			} else if (item.link_type === "Page" && item.route_options) {
				args.route_options = JSON.parse(item.route_options);
			} else {
				args.tab = item.tab;
				// a list opened on the entry's own filters
				const filtered = item.link_type === "DocType" && (item.filters ? list_filters(item.filters) : item.route_options);
				if (filtered) {
					args.doc_view = "List";
					args.route_options = typeof filtered === "string" ? JSON.parse(filtered) : filtered;
				}
			}
			return frappe.utils.generate_route(args) || null;
		} catch (error) {
			return null;
		}
	}

	// an entry's filters as the list takes them: each field's value, without its operator
	function list_filters(filters) {
		const found = JSON.parse(frappe.utils.get_filter_as_json(JSON.parse(filters)) || "null");
		if (!found) return null;
		Object.keys(found).forEach((field) => {
			if (Array.isArray(found[field])) found[field] = found[field][1];
		});
		return found;
	}

	// a module's own menu, as its sidebar lists it: the headings and the entries under them
	function entries(label) {
		const sidebar = (frappe.boot.workspace_sidebar_item || {})[String(label).toLowerCase()];
		const all = [];
		((sidebar && sidebar.items) || []).forEach((item) => {
			if (!item || item.hidden) return;
			if (item.type === "Section Break") all.push({ heading: item.label });
			else if (item.type === "Link") {
				const path = path_of(item);
				// an address of the entry's own opens beside the desk, as it does from Frappe's sidebar
				if (path && item.label) all.push({ label: item.label, path: path, outside: item.link_type === "URL" });
			}
		});
		// a heading with nothing under it says nothing
		return all.filter((row, index) => !row.heading || (all[index + 1] && !all[index + 1].heading));
	}

	// An entry opened as Frappe's router opens a link of its own (router.js, a click on an <a>): what follows
	// the ? as route options, what follows the # as the tab. The module's sidebar is asked for by name, as
	// Frappe's tile asks for it, but only where nothing else rides on the route options: Frappe's sidebar
	// clears them all once it has read its own, and a list's filters would go with it.
	function follow(path, module, outside) {
		const url = new URL(path, window.location.origin);
		if (outside || url.origin !== window.location.origin || !frappe.router.is_app_route(url.pathname)) {
			window.open(url.href, "_blank", "noopener");
			return;
		}
		const options = {};
		url.searchParams.forEach((value, key) => {
			options[key] = value;
		});
		frappe.route_options = Object.keys(options).length ? options : { sidebar: module };
		if (url.hash) frappe.route_hash = url.hash;
		frappe.set_route(url.pathname);
	}

	function open_state(wrapper) {
		wrapper.querySelectorAll(".desktop-icon.ha-has-menu").forEach((tile) => {
			const open = tile.getAttribute("data-id") === open_module;
			tile.classList.toggle("ha-open", open);
			const toggle = tile.querySelector(".ha-rail-toggle");
			if (toggle) toggle.setAttribute("aria-expanded", open ? "true" : "false");
		});
	}

	// Each module in the list opens to its own menu, so an entry is one click from the desk. The row itself
	// is still Frappe's tile and opens the module as before; the arrow and the menu are added inside it,
	// which keeps them out of Frappe's count of the tiles when the desk is edited.
	function menus(wrapper) {
		try {
			wrapper
				.querySelectorAll(":scope > .desktop-container > .icons-container > .icons > .desktop-icon[data-id]")
				.forEach((tile) => {
					if (tile.querySelector(".ha-rail-menu")) return;
					const module = tile.getAttribute("data-id");
					const list = entries(module);
					if (!list.length) return;
					tile.insertAdjacentHTML(
						"beforeend",
						`<span class="ha-rail-toggle" role="button" tabindex="0" aria-expanded="false" ` +
							`title="${esc(__("Show menu"))}">${icon("chevron")}</span>` +
							`<span class="ha-rail-menu">${menu_html(list, module)}</span>`
					);
					tile.classList.add("ha-has-menu");
					// neither the arrow nor the menu is the tile: a click on them does not open the module
					const mine = (event) => {
						event.preventDefault();
						event.stopPropagation();
					};
					const flip = (event) => {
						mine(event);
						open_module = open_module === module ? null : module;
						open_state(wrapper);
					};
					const pick = (event) => {
						mine(event);
						const heading = event.target.closest(".ha-rail-heading");
						if (heading) {
							const group = heading.parentElement;
							const key = module + "|" + list[Number(group.getAttribute("data-group"))].heading;
							const shown = !group.classList.contains("ha-shown");
							group.classList.toggle("ha-shown", shown);
							heading.setAttribute("aria-expanded", shown ? "true" : "false");
							if (shown) shown_groups.add(key);
							else shown_groups.delete(key);
							return;
						}
						const link = event.target.closest(".ha-rail-link");
						const row = link && list[Number(link.getAttribute("data-index"))];
						try {
							if (row) follow(row.path, module, row.outside);
						} catch (error) {
							console.error(error);
						}
					};
					const keyed = (act) => (event) => {
						if (event.key === "Enter" || event.key === " ") act(event);
					};
					const toggle = tile.querySelector(".ha-rail-toggle");
					const menu = tile.querySelector(".ha-rail-menu");
					toggle.addEventListener("click", flip);
					toggle.addEventListener("keydown", keyed(flip));
					menu.addEventListener("click", pick);
					menu.addEventListener("keydown", keyed(pick));
				});
			open_state(wrapper);
		} catch (error) {
			console.error(error);
		}
	}

	// A module's menu: its first entries as they are, and each heading with the entries under it, which the
	// heading opens and shuts. A heading stays as it was left while the desk is drawn again.
	function menu_html(list, module) {
		let html = "";
		let in_group = false;
		list.forEach((row, index) => {
			if (row.heading) {
				if (in_group) html += "</span></span>";
				const shown = shown_groups.has(module + "|" + row.heading);
				html +=
					`<span class="ha-rail-group${shown ? " ha-shown" : ""}" data-group="${index}">` +
					`<span class="ha-rail-heading" role="button" tabindex="0" aria-expanded="${shown ? "true" : "false"}">` +
					`<span>${esc(__(row.heading))}</span>${icon("chevron")}</span><span class="ha-rail-items">`;
				in_group = true;
			} else {
				html +=
					`<span class="ha-rail-link" role="link" tabindex="0" data-index="${index}">` + `${esc(__(row.label))}</span>`;
			}
		});
		return html + (in_group ? "</span></span>" : "");
	}

	// the desk as Frappe drew it: nothing of the home's left on it
	function unmount(wrapper) {
		wrapper.querySelectorAll(".ha-home, .ha-rail-toggle, .ha-rail-menu").forEach((node) => node.remove());
		wrapper.querySelectorAll(".ha-has-menu").forEach((tile) => tile.classList.remove("ha-has-menu", "ha-open"));
		wrapper.classList.remove("ha-has-home");
		MEASURED.forEach((name) => wrapper.style.removeProperty(name));
	}

	function skeleton() {
		const line = (width) => `<div class="ha-home-bone" style="width:${width}"></div>`;
		return (
			`<section class="ha-home-hero"><div class="ha-home-hero-text">${line("260px")}${line("180px")}</div></section>` +
			`<div class="ha-home-cards">${[1, 2, 3, 4]
				.map(() => `<div class="ha-home-card">${line("90px")}${line("60px")}${line("120px")}</div>`)
				.join("")}</div>`
		);
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

	// a list of rows, each opening what it names; what and section say which list a click is on
	function rows(list, empty, what = "row", section = "", part = "rows") {
		if (!list.length) return `<div class="ha-home-empty">${esc(empty)}</div>`;
		return list
			.map((row, index) => {
				// a row that opens nothing (a holiday) has no arrow
				const arrow = what !== "item" || row.doctype ? icon("chevron") : "";
				return (
					`<button type="button" class="ha-home-row" data-ha-home="${what}" data-section="${esc(section)}" ` +
					`data-part="${esc(part)}" data-index="${index}">` +
					`<span class="ha-home-dot ha-band-${esc(row.band || "none")}"></span>` +
					`<span class="ha-home-row-text"><span class="ha-home-row-title">${esc(row.title)}</span>` +
					`<span class="ha-home-row-meta">${[
						row.doctype ? __(row.doctype) : row.date ? day_words(row.date) : "",
						row.docname,
						row.when ? __(row.when) : "",
					]
						.filter(Boolean)
						.map(esc)
						.join(" · ")}</span></span>${arrow}</button>`
				);
			})
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
			`<section class="ha-home-panel ha-home-waiting"><header><span class="ha-home-panel-icon">${icon("waiting")}</span>` +
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

	function panel(name, title, body, note) {
		return (
			`<section class="ha-home-panel"><header><span class="ha-home-panel-icon">${icon(name)}</span>` +
			`<h3>${title}</h3>${note || ""}</header><div class="ha-home-list">${body}</div></section>`
		);
	}

	// bars, each as wide as its share of the whole: where people are today, the departments, or a part of one of
	// the panels under them (panel and part say which, for a click)
	function bars(list, what, whole, panel, part) {
		const most = whole || Math.max(1, ...list.map((row) => Number(row.value) || 0));
		const of_panel = panel ? ` data-panel="${esc(panel)}" data-part="${esc(part)}"` : "";
		return (
			`<div class="ha-home-bars">` +
			list
				.map((row, index) => {
					const width = most ? Math.round((100 * (Number(row.value) || 0)) / most) : 0;
					return (
						`<button type="button" class="ha-home-bar" data-ha-home="${what}"${of_panel} data-index="${index}">` +
						`<span class="ha-home-bar-label">${esc(__(row.label))}</span>` +
						`<span class="ha-home-bar-track"><i class="ha-band-${esc(row.band || "navy")}" style="width:${width}%"></i></span>` +
						`<b>${count(row.value)}</b></button>`
					);
				})
				.join("") +
			`</div>`
		);
	}

	// What this user's desk has under what waits for them: HR the company's people, a manager their team,
	// everybody their own requests and holidays. Only what the server sent is drawn.
	function sections(data) {
		const parts = data.sections || {};
		const blocks = [];
		// a panel that takes the place of one of these: Plants at a Glance stands where Today stood on HR's desk
		(data.panels || [])
			.filter((item) => item.place === "sections")
			.forEach((item) => {
				const drawn = more_one(item, false);
				if (drawn) blocks.push(drawn);
			});
		if (parts.today && parts.today.rows) {
			blocks.push(panel("on_site", __("Today"), bars(parts.today.rows, "board", Number(parts.today.total) || 0),
				`<span class="ha-home-panel-note">${count(parts.today.total)} ${__("employees")}</span>`));
		}
		if (parts.departments && parts.departments.length) {
			blocks.push(panel("employees", __("Departments"), bars(parts.departments, "department")));
		}
		if (parts.coming) {
			blocks.push(panel("calendar", __("Coming Up"), rows(parts.coming, __("Nothing in the next two weeks."), "item", "coming")));
		}
		if (parts.team) {
			blocks.push(panel("employees", __("My Team Today"), rows(parts.team, __("Nobody reports to you."), "item", "team")));
		}
		if (parts.requests) {
			blocks.push(panel("contracts", __("My Requests"), rows(parts.requests, __("No requests yet."), "item", "requests")));
		}
		if (parts.holidays) {
			blocks.push(panel("calendar", __("Holidays"), rows(parts.holidays, __("No holidays ahead on your list."), "item", "holidays")));
		}
		if (!blocks.length) return "";
		return `<div class="ha-home-panels ha-home-more ha-home-${blocks.length > 2 ? "three" : blocks.length > 1 ? "two" : "one"}">${blocks.join("")}</div>`;
	}

	// ── The panels: the overview's under what waits, and a module tab's (dashboards.py) ──
	// The home's own answer names the tabs the user has, and the overview's panels with where each goes
	// ({key, title, place}); their figures come in a call of their own for each part, as its tab is opened, so
	// the greeting and what waits are never held up by them. A panel is drawn as a frame while its figures are
	// on their way, and not at all where they could not be read.

	// how a step of Payroll Readiness is coloured: done, under way, late, not started
	const STATES = { done: "good", open: "today", late: "overdue", todo: "none" };

	function tab_of(key) {
		return ((answer && answer.tabs) || []).find((one) => one.key === key) || null;
	}

	// a panel of the tab open now, as the server read it
	function panel_of(key) {
		const read = parts[current];
		return ((read && read.panels) || []).find((one) => one.key === key) || null;
	}

	function more_one(item, wide) {
		if (!parts[current]) return more_frame(item, wide);
		const one = panel_of(item.key);
		return one ? more_panel(one, wide) : "";
	}

	// a panel still on its way: its frame
	function more_frame(item, wide) {
		const line = (width) => `<div class="ha-home-bone" style="width:${width}"></div>`;
		return (
			`<section class="ha-home-panel${wide ? " ha-home-wide" : ""}"><header>` +
			`<span class="ha-home-panel-icon">${icon(item.icon || item.key)}</span><h3>${esc(__(item.title))}</h3></header>` +
			`<div class="ha-home-list ha-home-pad">${line("72%")}${line("88%")}${line("54%")}</div></section>`
		);
	}

	// a panel drawn by its kind; wide is across the page
	function more_panel(one, wide) {
		const body = KINDS[one.kind];
		if (!body) return "";
		return (
			`<section class="ha-home-panel ha-home-${esc(one.key)}${wide ? " ha-home-wide" : ""}"><header>` +
			`<span class="ha-home-panel-icon">${icon(one.icon || one.key)}</span><h3>${esc(__(one.title))}</h3>` +
			(one.note ? `<span class="ha-home-panel-note">${esc(__(one.note))}</span>` : "") +
			`</header><div class="ha-home-list">${body(one)}</div>${see_all(one)}</section>`
		);
	}

	// the way to the whole list, where a panel shows only some of it
	function see_all(one) {
		const listed = (one.rows || []).length;
		if (!one.route || !one.total || one.total <= listed) return "";
		return (
			`<div class="ha-home-seeall"><button type="button" class="ha-home-all" data-ha-home="all" data-panel="${esc(one.key)}">` +
			`<span>${esc(__("See all {0}", [count(one.total)]))}</span>${icon("chevron")}</button></div>`
		);
	}

	function more_top(data) {
		return (data.panels || [])
			.filter((item) => item.place === "top")
			.map((item) => more_one(item, true))
			.join("");
	}

	function more_rows(data) {
		const blocks = (data.panels || [])
			.filter((item) => item.place === "row")
			.map((item) => more_one(item, false))
			.filter(Boolean);
		if (!blocks.length) return "";
		const across = blocks.length > 2 ? "three" : blocks.length > 1 ? "two" : "one";
		return `<div class="ha-home-panels ha-home-extra ha-home-${across}">${blocks.join("")}</div>`;
	}

	function nothing(words) {
		return `<div class="ha-home-empty">${esc(words)}</div>`;
	}

	// a figure against the period before: which way it moved, and how far
	function moved(change) {
		if (!change || change.percent == null || change.direction === "same") return "";
		const way = change.direction === "up" ? "up" : "down";
		return `<span class="ha-home-delta">${icon(way)}${esc(Math.abs(Number(change.percent) || 0) + "%")}</span>`;
	}

	// Payroll Readiness: the period's steps, each with where it stands
	function steps_body(one) {
		const all = one.steps || [];
		if (!all.length) return nothing(__("Nothing to check yet."));
		const done = all.filter((step) => step.state === "done").length;
		return (
			`<div class="ha-home-progress"><i style="width:${Math.round((100 * done) / all.length)}%"></i></div>` +
			`<div class="ha-home-steps">` +
			all
				.map((step, index) => {
					// a step that opens nothing has no arrow
					const arrow = step.route || step.doctype ? icon("chevron") : "";
					return (
						`<button type="button" class="ha-home-step ha-band-${STATES[step.state] || "none"}" data-ha-home="more" ` +
						`data-panel="${esc(one.key)}" data-part="steps" data-index="${index}">` +
						`<span class="ha-home-step-mark">${icon(STATES[step.state] ? step.state : "todo")}</span>` +
						`<span class="ha-home-row-text"><span class="ha-home-row-title">${esc(__(step.label))}</span>` +
						`<span class="ha-home-row-meta">${esc(__(step.note || ""))}</span></span>${arrow}</button>`
					);
				})
				.join("") +
			`</div>`
		);
	}

	// Plants at a Glance: who is in at each plant, of its people, and the rest of its day
	function plants_body(one) {
		const all = one.rows || [];
		if (!all.length) return nothing(__("No plants to show."));
		return all
			.map((plant, index) => {
				// today is not said to somebody who may read neither the clock nor the attendance
				const known = plant.in != null;
				const staff = Number(plant.staff) || 0;
				const share = known && staff ? Math.round((100 * (Number(plant.in) || 0)) / staff) : 0;
				const meta = (known
					? [
							`${count(plant.late)} ${__("late")}`,
							`${count(plant.absent)} ${__("absent")}`,
							`${count(plant.on_leave)} ${__("on leave")}`,
					  ]
					: []
				)
					.concat([`${hours(plant.overtime)} ${__("overtime")}`])
					.join(" · ");
				const figure = known
					? `${count(plant.in)}<small> / ${count(plant.staff)}</small>`
					: `${count(plant.staff)}<small> ${esc(__("staff"))}</small>`;
				return (
					`<button type="button" class="ha-home-plant" data-ha-home="more" data-panel="${esc(one.key)}" ` +
					`data-part="rows" data-index="${index}">` +
					`<span class="ha-home-plant-top"><span class="ha-home-bar-label">${esc(plant.plant)}</span>` +
					`<span class="ha-home-bar-track"><i class="ha-band-${esc(plant.band || "good")}" style="width:${share}%"></i></span>` +
					`<b>${figure}</b></span>` +
					`<span class="ha-home-row-meta">${esc(meta)}</span>` +
					(plant.silent ? `<span class="ha-home-flag">${esc(__("No punches from its clock today"))}</span>` : "") +
					`</button>`
				);
			})
			.join("");
	}

	// Output and Labour Cost: each plant's work, its pay and its overtime, against the same days of the last
	// period. The server says which figures a plant has, and sends money only to those who may see it.
	function output_body(one) {
		const all = one.rows || [];
		if (!all.length) return nothing(__("No output recorded this period."));
		const written = (figure) =>
			figure.kind === "money"
				? money(figure.value, one.currency || "")
				: figure.kind === "hours"
				? hours(figure.value)
				: count(Math.round(Number(figure.value) || 0));
		return all
			.map((plant, index) => {
				const parts = (plant.figures || [])
					.map(
						(figure) =>
							`<span class="ha-home-figure"><small>${esc(__(figure.label))}</small>` +
							`<b>${esc(written(figure))}</b>${moved(figure)}</span>`
					)
					.join("");
				return (
					`<button type="button" class="ha-home-output-plant" data-ha-home="more" data-panel="${esc(one.key)}" ` +
					`data-part="rows" data-index="${index}"><span class="ha-home-bar-label">${esc(plant.plant)}</span>` +
					`<span class="ha-home-figures">${parts}</span></button>`
				);
			})
			.join("");
	}

	// Workforce Movement: joiners and leavers by month, the turnover, and the headcount by status
	function movement_body(one) {
		const months = one.months || [];
		const most = Math.max(1, ...months.map((month) => Math.max(Number(month.joined) || 0, Number(month.left) || 0)));
		const tall = (value) => Math.round((100 * (Number(value) || 0)) / most);
		const chart =
			`<div class="ha-home-columns">` +
			months
				.map(
					(month) =>
						`<span class="ha-home-column" title="${esc(__(month.label))}: ${count(month.joined)} ${esc(__("joined"))}, ` +
						`${count(month.left)} ${esc(__("left"))}"><span class="ha-home-column-bars">` +
						`<i class="ha-band-good" style="height:${tall(month.joined)}%"></i>` +
						`<i class="ha-band-overdue" style="height:${tall(month.left)}%"></i></span>` +
						`<span class="ha-home-column-label">${esc(__(month.label))}</span>` +
						`<span class="ha-home-column-figures">${count(month.joined)} · ${count(month.left)}</span></span>`
				)
				.join("") +
			`</div>`;
		const turnover = one.turnover
			? `<span class="ha-home-legend-figure">${esc(__("Turnover"))} <b>${esc(String(one.turnover.rate) + "%")}</b> ` +
			  `${esc(__("in 12 months"))}</span>`
			: "";
		const legend =
			`<div class="ha-home-legend"><span><i class="ha-band-good"></i>${esc(__("Joined"))}</span>` +
			`<span><i class="ha-band-overdue"></i>${esc(__("Left"))}</span>${turnover}</div>`;
		const statuses = (one.statuses || []).length
			? `<div class="ha-home-sub">${esc(__("Headcount by status"))}</div>` + bars(one.statuses, "more", 0, one.key, "statuses")
			: "";
		return (months.length ? chart + legend : "") + statuses;
	}

	// Deadlines, and a module's lists: what comes due, the nearest first, or what has waited longest
	function list_body(one) {
		return rows(one.rows || [], __(one.empty || "Nothing coming due."), "more", one.key);
	}

	// Recruitment Pipeline: each stage's figure, a few figures about it, and this week's interviews
	function pipeline_body(one) {
		const figures = (one.figures || [])
			.map(
				(figure) =>
					`<span class="ha-home-figure"><small>${esc(__(figure.label))}</small>` +
					`<b>${esc(figure.text != null ? __(figure.text) : count(figure.value))}</b></span>`
			)
			.join("");
		const interviews = (one.rows || []).length
			? `<div class="ha-home-sub">${esc(__("Interviews this week"))}</div>` + rows(one.rows, "", "more", one.key)
			: "";
		const longest = (one.longest || []).length
			? `<div class="ha-home-sub">${esc(__("Open longest"))}</div>` + rows(one.longest, "", "more", one.key, "longest")
			: "";
		return (
			bars(one.stages || [], "more", 0, one.key, "stages") +
			(figures ? `<div class="ha-home-figures ha-home-pad">${figures}</div>` : "") +
			interviews +
			longest
		);
	}

	// Data Health: what is missing, and from how many records, each opening those records
	function health_body(one) {
		const all = one.rows || [];
		if (!all.length) return nothing(__("Every record has what payroll and the clock need."));
		return all
			.map(
				(row, index) =>
					`<button type="button" class="ha-home-row" data-ha-home="more" data-panel="${esc(one.key)}" ` +
					`data-part="rows" data-index="${index}"><span class="ha-home-dot ha-band-${esc(row.band || "today")}"></span>` +
					`<span class="ha-home-row-text"><span class="ha-home-row-title">${esc(__(row.label))}</span>` +
					`<span class="ha-home-row-meta">${esc(__(row.note || ""))}</span></span>` +
					`<b class="ha-home-count">${count(row.value)}</b>${icon("chevron")}</button>`
			)
			.join("");
	}

	// Needs Attention: what waits for a decision or is late, the most pressing first, each opening its list; on
	// the overview each says which module it is in
	function attention_body(one) {
		const all = one.rows || [];
		if (!all.length) return nothing(__("Nothing is waiting or late. All clear."));
		return all
			.map(
				(check, index) =>
					`<button type="button" class="ha-home-row ha-home-check" data-ha-home="more" data-panel="${esc(one.key)}" ` +
					`data-part="rows" data-index="${index}"><b class="ha-home-check-count ha-band-${esc(check.band || "none")}">` +
					`${count(check.value)}</b><span class="ha-home-row-text"><span class="ha-home-row-title">${esc(__(check.label))}</span>` +
					(check.module ? `<span class="ha-home-row-meta">${esc(__(check.module))}</span>` : "") +
					`</span>${icon("chevron")}</button>`
			)
			.join("");
	}

	// a figure of a panel as its kind writes it: money in the company's currency, hours, a percent, or a count
	function written_by(one) {
		return (value) =>
			one.money
				? money(value, one.currency || "")
				: one.hours
				? hours(value)
				: one.percent
				? percent(value)
				: count(Math.round(Number(value) || 0));
	}

	// a percent, to a tenth where it is not whole
	function percent(value) {
		return count(Math.round((Number(value) || 0) * 10) / 10) + "%";
	}

	// Six months of something: a column for each series in each month, a month opening what it is made of.
	// Nothing is drawn for a month with none.
	function columns_body(one) {
		const months = one.months || [];
		const series = one.series || [];
		if (!months.length || !series.length) return nothing(__(one.empty || "Nothing to show yet."));
		const written = written_by(one);
		const most = Math.max(1, ...months.map((month) => Math.max(0, ...(month.values || []).map((v) => Number(v) || 0))));
		const tall = (value) => Math.round((100 * Math.max(0, Number(value) || 0)) / most);
		const chart =
			`<div class="ha-home-columns">` +
			months
				.map((month, index) => {
					const values = month.values || [];
					const says = series.map((s, at) => __(s.label) + " " + written(values[at])).join(", ");
					return (
						`<button type="button" class="ha-home-column" data-ha-home="month" data-panel="${esc(one.key)}" ` +
						`data-index="${index}" title="${esc(__(month.label) + ": " + says)}"><span class="ha-home-column-bars">` +
						series
							.map((s, at) =>
								tall(values[at]) > 0
									? `<i class="ha-band-${esc(s.band || "soon")}" style="height:${tall(values[at])}%"></i>`
									: ""
							)
							.join("") +
						`</span><span class="ha-home-column-label">${esc(__(month.label))}</span>` +
						`<span class="ha-home-column-figures">${esc(written(values[0]))}</span></button>`
					);
				})
				.join("") +
			`</div>`;
		const latest = months[months.length - 1].values || [];
		const legend =
			`<div class="ha-home-legend">` +
			series
				.map(
					(s, at) =>
						`<span><i class="ha-band-${esc(s.band || "soon")}"></i>${esc(__(s.label))} <b>${esc(written(latest[at]))}</b></span>`
				)
				.join("") +
			`<span class="ha-home-legend-figure">${esc(__("This month so far"))}</span></div>`;
		return chart + legend;
	}

	// A breakdown as bars, each as long as its share of the largest, opening what it is made of
	function bars_body(one) {
		const all = one.rows || [];
		if (!all.length) return nothing(__(one.empty || "Nothing to show yet."));
		const written = written_by(one);
		const most = Math.max(1, ...all.map((part) => Math.abs(Number(part.value) || 0)));
		return (
			`<div class="ha-home-bars">` +
			all
				.map((part, index) => {
					const width = Math.round((100 * Math.abs(Number(part.value) || 0)) / most);
					return (
						`<button type="button" class="ha-home-bar" data-ha-home="more" data-panel="${esc(one.key)}" data-part="rows" ` +
						`data-index="${index}"><span class="ha-home-bar-label">${esc(__(part.label))}</span>` +
						`<span class="ha-home-bar-track">` +
						(width > 0 ? `<i class="ha-band-${esc(part.band || "navy")}" style="width:${width}%"></i>` : "") +
						`</span><b>${esc(written(part.value))}</b></button>`
					);
				})
				.join("") +
			`</div>`
		);
	}

	// A ring of a whole's parts in the theme's colours, each listed with its share and opening what it is made
	// of; the rest, put together, in the quiet gray
	function donut_body(one) {
		const all = one.rows || [];
		const whole = all.reduce((sum, part) => sum + Math.max(0, Number(part.value) || 0), 0);
		if (!all.length || !whole) return nothing(__(one.empty || "Nothing to show yet."));
		const written = written_by(one);
		const shade = (part, index) => (part.rest ? "var(--ha-slice-rest)" : `var(--ha-slice-${index % SLICES})`);
		let at = 0;
		const stops = all
			.map((part, index) => {
				const from = at;
				at += (100 * Math.max(0, Number(part.value) || 0)) / whole;
				return `${shade(part, index)} ${from.toFixed(2)}% ${at.toFixed(2)}%`;
			})
			.join(", ");
		const ring =
			`<div class="ha-home-donut"><span class="ha-home-donut-ring" role="img" ` +
			`aria-label="${esc(all.map((part) => `${__(part.label)}: ${written(part.value)}`).join(", "))}" ` +
			`style="background: conic-gradient(${stops})"></span>` +
			`<span class="ha-home-donut-middle"><b>${esc(written(whole))}</b><small>${esc(__("in all"))}</small></span></div>`;
		const legend = all
			.map(
				(part, index) =>
					`<button type="button" class="ha-home-slice" data-ha-home="more" data-panel="${esc(one.key)}" data-part="rows" ` +
					`data-index="${index}"><i style="background:${shade(part, index)}"></i>` +
					`<span class="ha-home-bar-label">${esc(__(part.label))}</span><b>${esc(written(part.value))}</b>` +
					`<small>${Math.round((100 * Math.max(0, Number(part.value) || 0)) / whole)}%</small></button>`
			)
			.join("");
		return `<div class="ha-home-donut-row">${ring}<div class="ha-home-slices">${legend}</div></div>`;
	}

	const KINDS = {
		steps: steps_body,
		plants: plants_body,
		output: output_body,
		movement: movement_body,
		list: list_body,
		pipeline: pipeline_body,
		health: health_body,
		attention: attention_body,
		columns: columns_body,
		bars: bars_body,
		donut: donut_body,
	};

	// ── The tabs ──────────────────────────────────────────────────────────

	// The tab a module page's Dashboard button asks for. It comes as a route option, which Frappe's router may
	// also carry in the address, JSON-encoded (router.js set_route), and it is taken off both once read: the tab
	// the viewer moves to is not undone when the desk is drawn again, and the next list opened does not take it
	// for a filter. Only while the desk is on the screen: Frappe keeps the pages it has shown, hidden, and
	// another page's options are its own.
	function take_request() {
		const wrapper = desk();
		if (!wrapper || wrapper.offsetParent === null) return;
		try {
			let named = null;
			const options = frappe.route_options;
			if (options && options.dashboard != null) {
				named = options.dashboard;
				delete options.dashboard;
				if (!Object.keys(options).length) frappe.route_options = null;
			}
			const address = new URL(window.location.href);
			if (address.searchParams.has("dashboard")) {
				named = named || address.searchParams.get("dashboard");
				address.searchParams.delete("dashboard");
				window.history.replaceState(window.history.state, "", address.pathname + address.search + address.hash);
			}
			if (typeof named === "string" && named.startsWith('"')) named = JSON.parse(named);
			if (named) requested = String(named);
		} catch (error) {
			console.error(error);
		}
	}

	// The tab to open first: the one asked for, else the one the viewer last opened, else the overview; only one
	// the user has
	function first_tab(data) {
		const have = (key) => (data.tabs || []).some((one) => one.key === key);
		take_request();
		const named = requested;
		requested = null;
		if (named && have(named)) return named;
		let kept = null;
		try {
			kept = window.localStorage.getItem(TAB_KEY);
		} catch (error) {
			kept = null;
		}
		return kept && have(kept) ? kept : OVERVIEW;
	}

	function keep_tab() {
		try {
			window.localStorage.setItem(TAB_KEY, current);
		} catch (error) {
			// the tab still opens; it is only not remembered
		}
	}

	// A tab asked for once the home is here opens over the one open; until then, the home's answer opens it
	function follow_request() {
		take_request();
		if (!requested || !answer) return;
		const named = requested;
		requested = null;
		if (!tab_of(named) || named === current) return;
		current = named;
		keep_tab();
		redraw();
		load_parts(false);
	}

	// how much needs attention on a tab, as the overview read it
	function badge_of(key) {
		const badges = (parts[OVERVIEW] && parts[OVERVIEW].badges) || {};
		return badges[key] || null;
	}

	// a tab for each module the user's work is about, the overview first: each says how much needs attention in it
	function tab_bar(data) {
		const all = data.tabs || [];
		if (all.length < 2) return "";
		return (
			`<nav class="ha-home-tabbar" role="tablist" aria-label="${esc(__("Dashboards"))}">` +
			all
				.map((one) => {
					const on = one.key === current;
					const badge = badge_of(one.key);
					const says = badge && badge.value ? __("{0} need attention", [count(badge.value)]) : "";
					return (
						`<button type="button" role="tab" id="ha-home-tab-${esc(one.key)}" class="ha-home-tabbtn${on ? " ha-on" : ""}" ` +
						`data-ha-home="open" data-tab="${esc(one.key)}" aria-selected="${on ? "true" : "false"}" ` +
						`aria-controls="ha-home-tabpanel" tabindex="${on ? "0" : "-1"}"${says ? ` title="${esc(says)}"` : ""}>` +
						`${icon(one.icon)}<span>${esc(__(one.title))}</span>` +
						(badge && badge.value ? `<i class="ha-home-badge ha-band-${esc(badge.band || "none")}">${count(badge.value)}</i>` : "") +
						`</button>`
					);
				})
				.join("") +
			`</nav>`
		);
	}

	// a time the server stamped ("2026-10-27 14:05:09") as the viewer's clock writes it
	function time_words(stamp) {
		try {
			const [day, time] = String(stamp).split(" ");
			const date = day.split("-").map(Number);
			const clock = (time || "00:00").split(":").map(Number);
			return new Date(date[0], date[1] - 1, date[2], clock[0], clock[1]).toLocaleTimeString(undefined, {
				hour: "numeric",
				minute: "2-digit",
			});
		} catch (e) {
			return stamp || "";
		}
	}

	// when the figures of a tab were read, and a way to read them again
	function stamp(key) {
		const read = parts[key];
		if (!read || !read.at) return "";
		return (
			`<span class="ha-home-stamp"><span>${esc(__("As of {0}", [time_words(read.at)]))}</span>` +
			`<button type="button" class="ha-home-refresh${parts_asking[key] ? " ha-busy" : ""}" data-ha-home="refresh">` +
			`${icon("refresh")}<span>${esc(__("Refresh"))}</span></button></span>`
		);
	}

	// A module's workspace, opened as its tile opens it, with its own menu down the left; only one the user may
	// open, which is one whose menu the boot carries
	function open_workspace(name) {
		if (!name || !entries(name).length) return;
		frappe.route_options = { sidebar: name };
		frappe.set_route(frappe.router.slug(name));
	}

	// the heading of a module's tab: what it is, when its figures were read with a way to read them again, and the
	// way into the module itself
	function tab_head(data, open) {
		const workspace = (open.workspaces || []).find((name) => entries(name).length);
		const into = workspace
			? `<button type="button" class="ha-home-into" data-ha-home="module" data-workspace="${esc(workspace)}">` +
			  `<span>${esc(__("Open {0}", [__(workspace)]))}</span>${icon("arrow")}</button>`
			: "";
		const company = data.company ? `<p>${esc(data.company)}</p>` : "";
		return (
			`<div class="ha-home-tabhead"><div class="ha-home-tabhead-text">` +
			`<h3>${esc(__("{0} Dashboard", [__(open.title)]))}</h3>${company}</div>` +
			`<div class="ha-home-tabhead-side">${stamp(open.key)}${into}</div></div>`
		);
	}

	// the figures across the top of a module's tab: frames until they are read, then those that could be
	function tab_cards(open) {
		const read = parts[open.key];
		const found = (key) => ((read && read.cards) || []).find((one) => one.key === key) || null;
		return (open.cards || []).map((frame) => (read ? found(frame.key) : frame)).filter(Boolean);
	}

	function module_cards(open) {
		const all = tab_cards(open);
		if (!all.length) return "";
		const line = (width) => `<div class="ha-home-bone" style="width:${width}"></div>`;
		return (
			`<div class="ha-home-cards">` +
			all
				.map((figure) => {
					const top =
						`<span class="ha-home-card-top"><span class="ha-home-card-label">${esc(__(figure.label))}</span>` +
						`<span class="ha-home-card-icon">${icon(figure.icon || figure.key)}</span></span>`;
					if (figure.frame) return `<div class="ha-home-card ha-home-frame">${top}${line("70%")}${line("50%")}</div>`;
					const value =
						figure.kind === "money"
							? money(figure.value, figure.currency || "")
							: figure.kind === "hours"
							? hours(figure.value)
							: figure.kind === "percent"
							? percent(figure.value)
							: count(figure.value);
					const delta = moved(figure.change);
					return (
						`<button type="button" class="ha-home-card ha-tone-${esc(figure.tone || "navy")}" data-ha-home="figure" ` +
						`data-key="${esc(figure.key)}">${top}<span class="ha-home-card-value">${esc(value)}</span>` +
						`<span class="ha-home-card-note">${delta}${esc(__(figure.note || ""))}</span></button>`
					);
				})
				.join("") +
			`</div>`
		);
	}

	// the reports a closer look is taken in, each opening for the user's company; across the page, or beside the
	// last panel where that one would be alone on its row
	function reports_panel(open, wide) {
		const all = open.reports || [];
		if (!all.length) return "";
		return (
			`<section class="ha-home-panel${wide ? " ha-home-wide" : ""} ha-home-reports"><header>` +
			`<span class="ha-home-panel-icon">${icon("reports")}</span><h3>${esc(__("Reports"))}</h3>` +
			`<span class="ha-home-panel-note">${esc(__("For a closer look"))}</span></header><div class="ha-home-list">` +
			all
				.map(
					(report, index) =>
						`<button type="button" class="ha-home-row" data-ha-home="report" data-index="${index}">` +
						`<span class="ha-home-row-text"><span class="ha-home-row-title">${esc(__(report.label))}</span></span>` +
						`${icon("chevron")}</button>`
				)
				.join("") +
			`</div></section>`
		);
	}

	// whether a panel of the tab open now is drawn: its frame until the tab is read, then only one the server read
	// in a kind this page draws
	function drawn(item) {
		if (!parts[current]) return true;
		const one = panel_of(item.key);
		return Boolean(one && KINDS[one.kind]);
	}

	// Two across, a wide one across both, and no row with a hole in it: a panel that would be alone on its row is
	// widened across it, the last one taking the reports beside it instead where there are reports.
	function packed(items, reports) {
		const out = items.map((item) => ({ item, wide: item.size === "wide" }));
		let alone = null;
		out.forEach((one, index) => {
			if (one.wide) {
				if (alone !== null) out[alone].wide = true;
				alone = null;
			} else alone = alone === null ? index : null;
		});
		if (alone !== null && !reports) out[alone].wide = true;
		return { panels: out, reports_wide: alone === null };
	}

	// a module's tab: its heading, its figures, what needs attention and its dashboards, and its reports
	function tab_panel(data, open) {
		const rows = packed((open.panels || []).filter(drawn), (open.reports || []).length > 0);
		const blocks = rows.panels
			.map((one) => more_one(one.item, one.wide))
			.concat([reports_panel(open, rows.reports_wide)])
			.filter(Boolean);
		return tab_head(data, open) + module_cards(open) + (blocks.length ? `<div class="ha-home-grid">${blocks.join("")}</div>` : "");
	}

	// the overview: the home as it was
	function overview(data) {
		return cards(data) + more_top(data) + panels(data) + sections(data) + more_rows(data);
	}

	// A tab bar wider than the screen scrolls sideways. It stays where the viewer left it, unless the open tab is
	// out of sight there: then it moves just far enough to show it.
	function reveal(bar, scrolled) {
		bar.scrollLeft = scrolled;
		const on = bar.querySelector(".ha-home-tabbtn.ha-on");
		if (!on || bar.scrollWidth <= bar.clientWidth) return;
		const edge = parseFloat(getComputedStyle(bar).paddingLeft) || 0;
		const start = on.offsetLeft - edge;
		const end = on.offsetLeft + on.offsetWidth + edge;
		if (start < bar.scrollLeft) bar.scrollLeft = start;
		else if (end > bar.scrollLeft + bar.clientWidth) bar.scrollLeft = end - bar.clientWidth;
	}

	// The tab bar is worked by the keyboard as a row of tabs (the WAI-ARIA tabs pattern): the arrows move to the
	// next tab and open it, Home and End to the first and the last.
	function keyed(event) {
		const button = event.target.closest(".ha-home-tabbtn");
		if (!button || !answer) return;
		const all = (answer.tabs || []).map((one) => one.key);
		const at = all.indexOf(button.getAttribute("data-tab"));
		const to = { ArrowRight: at + 1, ArrowLeft: at - 1, Home: 0, End: all.length - 1 }[event.key];
		if (to == null || at < 0) return;
		event.preventDefault();
		open_tab(all[(to + all.length) % all.length], true);
	}

	// another tab opened: drawn at once, its figures asked for if they are not here yet
	function open_tab(key, focus) {
		if (!tab_of(key)) return;
		current = key;
		keep_tab();
		redraw();
		load_parts(false);
		if (focus) {
			const button = document.getElementById("ha-home-tab-" + key);
			if (button) button.focus();
		}
	}

	// a route the server names, opened as Frappe opens it: a list on its filters, a page on its options
	function go(target) {
		if (!target || !target.route) return;
		const route = target.route.slice();
		const filters = Object.assign({}, target.filters || {});
		if (target.mine && route[1] === "ToDo") Object.assign(filters, { allocated_to: frappe.session.user, status: "Open" });
		if (target.mine && route[1] === "Notification Log") Object.assign(filters, { for_user: frappe.session.user, read: 0 });
		if (route[0] === "List" && Object.keys(filters).length) frappe.route_options = filters;
		else if (target.options) frappe.route_options = Object.assign({}, target.options);
		frappe.set_route(route);
	}

	// scrolled: how far along the tab bar was scrolled before it was drawn again
	function draw(home, scrolled) {
		const data = answer;
		if (!data) {
			home.innerHTML = skeleton();
			return;
		}
		const open = current !== OVERVIEW ? tab_of(current) : null;
		const body = open ? tab_panel(data, open) : overview(data);
		const bar = tab_bar(data);
		const shown = open ? open.key : OVERVIEW;
		home.innerHTML =
			hero(data) +
			(bar
				? bar +
				  `<div class="ha-home-tabpanel" id="ha-home-tabpanel" role="tabpanel" aria-labelledby="ha-home-tab-${esc(shown)}">` +
				  `${body}</div>`
				: body);
		const tabs = home.querySelector(".ha-home-tabbar");
		if (tabs) {
			reveal(tabs, scrolled || 0);
			tabs.addEventListener("keydown", keyed);
		}
		home.querySelectorAll("[data-ha-home]").forEach((element) => {
			element.addEventListener("click", () => {
				try {
					act(element);
				} catch (error) {
					console.error(error);
				}
			});
		});
	}

	// what a click on the home does: data-ha-home says what was clicked, data-index which of its kind
	function act(element) {
		const data = answer;
		const what = element.getAttribute("data-ha-home");
		const index = Number(element.getAttribute("data-index"));
		if (what === "tab") {
			tab = element.getAttribute("data-tab");
			redraw();
		} else if (what === "open") open_tab(element.getAttribute("data-tab"), false);
		else if (what === "todo") go({ route: ["List", "ToDo"], mine: 1 });
		else if (what === "action") go(data.action);
		else if (what === "card") go((data.cards || [])[index]);
		else if (what === "figure") {
			// a figure across the top of a module's tab
			const open = tab_of(current);
			const key = element.getAttribute("data-key");
			go(open && tab_cards(open).find((one) => one.key === key && !one.frame));
		} else if (what === "link") go((data.shortcuts || [])[index]);
		else if (what === "row") {
			const row = ((tab === "notes" ? data.waiting.notes : data.waiting.items) || [])[index];
			if (row && row.doctype && row.docname) frappe.set_route("Form", row.doctype, row.docname);
			else go({ route: ["List", "ToDo"], mine: 1 });
		} else if (what === "item") {
			const row = ((data.sections || {})[element.getAttribute("data-section")] || [])[index];
			if (row && row.doctype && row.docname) frappe.set_route("Form", row.doctype, row.docname);
		} else if (what === "department") {
			const row = ((data.sections || {}).departments || [])[index];
			if (row) go({ route: ["List", "Employee"], filters: row.filters });
		} else if (what === "board") go({ route: ["attendance-board"] });
		else if (what === "more") {
			// a row of one of the panels: the record it names, else the list or page it opens on, else the panel's
			// own list narrowed to it
			const one = panel_of(element.getAttribute("data-panel") || element.getAttribute("data-section"));
			const row = one && (one[element.getAttribute("data-part") || "rows"] || [])[index];
			if (!row) return;
			if (row.doctype && row.docname) frappe.set_route("Form", row.doctype, row.docname);
			else if (row.route) go(row);
			else if (row.filters && one.route) go({ route: one.route, filters: Object.assign({}, one.filters, row.filters) });
		} else if (what === "month") {
			// a month of a chart: its documents, by the date the chart counts them on
			const one = panel_of(element.getAttribute("data-panel"));
			const month = one && (one.months || [])[index];
			if (month && one.route && one.day) {
				go({ route: one.route, filters: Object.assign({}, one.filters, { [one.day]: ["between", [month.from, month.to]] }) });
			}
		} else if (what === "all") {
			const one = panel_of(element.getAttribute("data-panel"));
			if (one) go(one);
		} else if (what === "report") {
			const open = tab_of(current);
			const report = open && (open.reports || [])[index];
			if (report) go({ route: report.route, options: report.options });
		} else if (what === "module") open_workspace(element.getAttribute("data-workspace"));
		else if (what === "refresh") load_parts(true);
	}

	// the home drawn again where it is, the tab bar scrolled to where the viewer left it, not back to its start
	function redraw() {
		try {
			const wrapper = desk();
			const home = present() ? wrapper.querySelector(".ha-home") : null;
			if (home && answer) {
				const bar = home.querySelector(".ha-home-tabbar");
				draw(home, bar ? bar.scrollLeft : 0);
			}
		} catch (error) {
			console.error(error);
		}
	}

	function load(home) {
		if (asking || Date.now() - asked_at < FRESH_MS) return;
		asking = true;
		// fetch, not frappe.call: a call that fails must leave the desk alone, and frappe.call would open
		// Frappe's Server Error dialog on the page everybody lands on
		fetch("/api/method/" + METHOD, { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } })
			.then((response) => (response.ok ? response.json() : null))
			.then((r) => {
				const first = !answer;
				answer = (r && r.message) || answer;
				// the desk opens on the tab asked for, else the one last opened, once the tabs are known
				if (answer && first) {
					current = first_tab(answer);
					keep_tab();
				}
			})
			.catch(() => {})
			.then(() => {
				asked_at = Date.now(); // the tiles are still there; a call that failed is tried again later, not at once
				asking = false;
				const there = mount();
				if (there && answer) draw(there);
				else if (there && !answer) unmount(desk()); // nothing to show: the desk as Frappe drew it
				load_parts(false);
			});
	}

	// What the tab open now needs, and the overview's figures, which say how much needs attention on each tab:
	// the overview's part only where it has panels or there are tabs to count for. Refresh asks the server to
	// read again each part already read.
	function load_parts(fresh) {
		if (!answer) return;
		const wanted = [];
		if ((answer.panels || []).length || (answer.tabs || []).length > 1) wanted.push(OVERVIEW);
		if (current !== OVERVIEW && tab_of(current)) wanted.push(current);
		const again = fresh ? Object.keys(parts) : [];
		Array.from(new Set(wanted.concat(again))).forEach((part) => load_part(part, fresh));
	}

	// One part's figures, by fetch for the same reason as the home's own. A call that fails leaves no panel where
	// its frames were, and is tried again later.
	function load_part(part, fresh) {
		if (!answer || parts_asking[part]) return;
		const had = parts[part];
		if (!fresh && had && Date.now() - had.time < FRESH_MS) return;
		if (part !== OVERVIEW && !tab_of(part)) return;
		parts_asking[part] = true;
		if (fresh) redraw(); // the refresh turns while it reads
		const query = "?part=" + encodeURIComponent(part) + (fresh ? "&fresh=1" : "");
		fetch("/api/method/" + FIGURES_METHOD + query, {
			credentials: "same-origin",
			cache: "no-store",
			headers: { Accept: "application/json" },
		})
			.then((response) => (response.ok ? response.json() : null))
			.then((r) => (r && r.message) || null)
			.catch(() => null)
			.then((read) => {
				parts[part] = Object.assign({ cards: [], panels: [] }, read || had || {}, { time: Date.now() });
				parts_asking[part] = false;
				redraw();
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
			load_parts(false);
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
	// there yet when the page changes: look a few times, then leave it. And it
	// draws the desk afresh after "page-change" each time the page is come back
	// to, which takes the home off again: so it looks a few times more than it
	// takes to find the desk, and puts the home back where it is missing.
	function arrive() {
		if (!on_desk()) return;
		let tries = 0;
		const look = () => {
			tries += 1;
			const there = present() || show();
			// measured again each time: the page may not have been laid out yet when the home went on
			if (there) measure();
			// a module page's Dashboard button may have asked for a tab
			if (there) follow_request();
			if (tries < 12 && (!there || tries < 5)) setTimeout(look, 150 * tries);
		};
		look();
	}

	// Frappe says when it has drawn the desk (desktop.js setup: "desktop_screen"): the home goes on at once,
	// and is measured again once Frappe has done what it does after (it hides its own navbar). Frappe means a
	// page it shows to open at its top (container.js, scroll_to), but scrolls the window, and the desk scrolls
	// in a pane of its own: come back to, it was shown as far down as the module left it.
	function drawn_again() {
		try {
			if (!on_desk()) return;
			if (!present()) show();
			follow_request();
			const wrapper = desk();
			const pane = wrapper && wrapper.closest(".main-section");
			if (pane) pane.scrollTop = 0;
			setTimeout(measure, 0);
		} catch (error) {
			console.error(error);
		}
	}

	// how far in the desk sits, wherever the home is on it
	function measure() {
		const wrapper = desk();
		if (wrapper && wrapper.classList.contains("ha-has-home")) bleed(wrapper);
	}

	let measuring = null;
	function resized() {
		clearTimeout(measuring);
		measuring = setTimeout(measure, 150);
	}

	const CSS = `
.ha-home {
	--ha-h-navy: var(--hra-primary, #14395E);
	--ha-h-deep: var(--hra-primary-dark, #0A2540);
	--ha-h-mid: var(--hra-primary-mid, #2A5A8C);
	--ha-h-gold: var(--hra-shell-marker, #F0AB00);
	--ha-h-on-gold: var(--hra-primary-dark, #0A2540);
	--ha-h-line: var(--hra-border, #C3D0E0);
	--ha-h-ink: var(--text-color, #1A2733);
	--ha-h-muted: var(--text-muted, #546678);
	--ha-h-card: var(--card-bg, #fff);
	--ha-h-shade: color-mix(in srgb, var(--ha-h-deep) 20%, transparent);
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
		radial-gradient(520px 220px at 88% -30%, color-mix(in srgb, var(--ha-h-gold) 26%, transparent), transparent 62%),
		radial-gradient(420px 260px at 8% 130%, rgba(255,255,255,.10), transparent 60%),
		linear-gradient(118deg, var(--ha-h-deep) 0%, var(--ha-h-navy) 52%, var(--ha-h-mid) 100%);
	box-shadow: 0 10px 28px var(--ha-h-shade);
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
	background: var(--ha-h-gold); color: var(--ha-h-on-gold); font-weight: 700; font-size: 13.5px;
	box-shadow: 0 6px 16px color-mix(in srgb, var(--ha-h-gold) 32%, transparent);
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
.ha-home .ha-home-card:hover { transform: translateY(-2px); box-shadow: 0 10px 22px color-mix(in srgb, var(--ha-h-navy) 12%, transparent); }
/* the figures' tones are the theme's status colours and its Accent (HRMS Addon Theme Settings) */
.ha-home .ha-tone-green { --ha-tone: var(--hra-success, #256F3A); }
.ha-home .ha-tone-amber { --ha-tone: var(--hra-amber-text, #B45309); }
.ha-home .ha-tone-rose { --ha-tone: var(--hra-danger, #A62B25); }
.ha-home .ha-tone-blue { --ha-tone: var(--hra-accent, #0A6ED1); }
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
.ha-home .ha-home-tab.ha-on { background: var(--ha-h-card); color: var(--ha-h-ink); box-shadow: 0 1px 3px color-mix(in srgb, var(--ha-h-navy) 16%, transparent); }
.ha-home-list { padding: 4px 6px 6px; }
.ha-home .ha-home-row { display: flex; align-items: center; gap: 11px; width: 100%; padding: 10px; border-radius: 10px; color: var(--ha-h-muted); }
.ha-home .ha-home-row:hover { background: color-mix(in srgb, var(--ha-h-navy) 6%, transparent); }
.ha-home-row-text { display: flex; flex-direction: column; gap: 1px; flex: 1 1 auto; min-width: 0; }
.ha-home-row-title { font-size: 13.5px; font-weight: 600; color: var(--ha-h-ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ha-home-row-meta { font-size: 12px; color: var(--ha-h-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* each row's and bar's band in the status colours My Alerts gives it (hrms_addon.bundle.css, the bands), and
   good in green */
.ha-home .ha-band-overdue { --ha-band: var(--hra-danger, #A62B25); }
.ha-home .ha-band-today { --ha-band: var(--hra-amber-text, #B45309); }
.ha-home .ha-band-soon { --ha-band: var(--hra-accent, #0A6ED1); }
.ha-home .ha-band-later { --ha-band: var(--hra-primary-soft, #5B8FC7); }
.ha-home .ha-band-good { --ha-band: var(--hra-success, #256F3A); }
.ha-home .ha-band-none { --ha-band: var(--hra-ink-muted, #546678); }
.ha-home-dot { width: 9px; height: 9px; border-radius: 50%; flex: none; background: var(--ha-band, var(--hra-ink-muted, #546678)); }
.ha-home-dot.ha-band-overdue, .ha-home-dot.ha-band-today { box-shadow: 0 0 0 3px color-mix(in srgb, var(--ha-band) 16%, transparent); }

/* the second row: the desk of HR, of a manager or of an employee */
.ha-home-panels.ha-home-two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.ha-home-panels.ha-home-three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.ha-home-panel-note { font-size: 12px; color: var(--ha-h-muted); }
.ha-home-bars { display: grid; gap: 2px; }
.ha-home .ha-home-bar {
	display: grid; grid-template-columns: minmax(0, 118px) minmax(0, 1fr) auto; align-items: center; gap: 10px;
	width: 100%; padding: 8px 10px; border-radius: 10px;
}
.ha-home .ha-home-bar:hover { background: color-mix(in srgb, var(--ha-h-navy) 6%, transparent); }
.ha-home-bar-label { font-size: 13px; font-weight: 600; color: var(--ha-h-ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ha-home-bar-track { height: 8px; border-radius: 99px; overflow: hidden; background: color-mix(in srgb, var(--ha-h-navy) 8%, transparent); }
.ha-home-bar-track > i { display: block; height: 100%; min-width: 2px; border-radius: 99px; background: var(--ha-band, var(--ha-h-navy)); }
.ha-home-bar b { min-width: 28px; text-align: right; font-size: 13.5px; color: var(--ha-h-ink); }
.ha-home-empty { padding: 26px 12px; text-align: center; font-size: 13px; color: var(--ha-h-muted); }

/* the panels under what waits (home_panels.py): Payroll Readiness across the page on top in its week, the rest
   in the rows, every colour the theme's */
.ha-home-panel.ha-home-wide { margin-top: 14px; }
.ha-home-pad { padding: 10px 16px 14px; }
.ha-home-sub { padding: 12px 10px 4px; font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--ha-h-muted); }
.ha-home-progress { height: 6px; margin: 8px 10px 6px; border-radius: 99px; overflow: hidden; background: color-mix(in srgb, var(--ha-h-navy) 8%, transparent); }
.ha-home-progress > i { display: block; height: 100%; min-width: 2px; border-radius: 99px; background: var(--hra-success, #256F3A); }
.ha-home-steps { display: grid; gap: 2px; }
.ha-home-wide .ha-home-steps { grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 4px; }
/* a step says all it has to say: its name and what stands in its way wrap rather than stop short */
.ha-home-step .ha-home-row-title, .ha-home-step .ha-home-row-meta,
.ha-home-data_health .ha-home-row-meta { white-space: normal; overflow: visible; }
.ha-home .ha-home-step { display: flex; align-items: center; gap: 11px; width: 100%; padding: 9px 10px; border-radius: 10px; color: var(--ha-h-muted); }
.ha-home .ha-home-step:hover { background: color-mix(in srgb, var(--ha-h-navy) 6%, transparent); }
.ha-home-step-mark {
	width: 26px; height: 26px; flex: none; border-radius: 50%; display: grid; place-items: center;
	color: var(--ha-band, var(--hra-ink-muted, #546678)); background: color-mix(in srgb, var(--ha-band, var(--hra-ink-muted, #546678)) 13%, transparent);
}
.ha-home-step-mark .ha-home-icon { width: 16px; height: 16px; }
.ha-home .ha-home-step.ha-band-good .ha-home-step-mark { color: #fff; background: var(--ha-band); }
.ha-home .ha-home-plant, .ha-home .ha-home-output-plant { display: flex; flex-direction: column; gap: 4px; width: 100%; padding: 9px 10px; border-radius: 10px; }
.ha-home .ha-home-plant:hover, .ha-home .ha-home-output-plant:hover { background: color-mix(in srgb, var(--ha-h-navy) 6%, transparent); }
.ha-home-plant-top { display: grid; grid-template-columns: minmax(0, 104px) minmax(0, 1fr) auto; align-items: center; gap: 10px; }
.ha-home-plant-top b { font-size: 13.5px; color: var(--ha-h-ink); white-space: nowrap; }
.ha-home-plant-top small { font-size: 11.5px; font-weight: 600; color: var(--ha-h-muted); }
.ha-home-flag {
	align-self: flex-start; font-size: 11.5px; font-weight: 600; padding: 2px 8px; border-radius: 99px;
	color: var(--hra-danger, #A62B25); background: color-mix(in srgb, var(--hra-danger, #A62B25) 10%, transparent);
}
.ha-home-figures { display: grid; grid-template-columns: repeat(auto-fit, minmax(96px, 1fr)); gap: 8px 12px; }
.ha-home-output-plant .ha-home-figures { grid-template-columns: repeat(2, minmax(0, 1fr)); }
/* Output and Labour Cost across the page: the plants side by side */
.ha-home-output.ha-home-wide .ha-home-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr)); gap: 0 8px; }
/* the pipeline's stages are named in full */
.ha-home-recruitment .ha-home-bar { grid-template-columns: minmax(0, 168px) minmax(0, 1fr) auto; }
.ha-home-figure { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.ha-home-figure small { font-size: 11px; color: var(--ha-h-muted); }
.ha-home-figure b { font-size: 14px; color: var(--ha-h-ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ha-home-delta { display: inline-flex; align-items: center; gap: 1px; font-size: 11px; font-weight: 600; color: var(--ha-h-muted); }
.ha-home-delta .ha-home-icon { width: 13px; height: 13px; }
.ha-home-card-note .ha-home-delta { margin-right: 6px; }
.ha-home-columns { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); gap: 8px; height: 150px; padding: 12px 12px 0; }
.ha-home-column { display: flex; flex-direction: column; align-items: center; gap: 3px; min-width: 0; height: 100%; }
.ha-home-column-bars { flex: 1 1 auto; width: 100%; display: flex; align-items: flex-end; justify-content: center; gap: 3px; }
.ha-home-column-bars > i { display: block; width: 38%; max-width: 14px; min-height: 2px; border-radius: 4px 4px 0 0; background: var(--ha-band, var(--ha-h-navy)); }
.ha-home-column-label { font-size: 11.5px; font-weight: 600; color: var(--ha-h-ink); }
.ha-home-column-figures { font-size: 11px; color: var(--ha-h-muted); white-space: nowrap; }
.ha-home-legend { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; padding: 10px 12px 4px; font-size: 12px; color: var(--ha-h-muted); }
.ha-home-legend > span { display: inline-flex; align-items: center; gap: 6px; }
.ha-home-legend i { width: 9px; height: 9px; border-radius: 3px; background: var(--ha-band, var(--ha-h-navy)); }
.ha-home-legend .ha-home-legend-figure { margin-left: auto; }
.ha-home-legend-figure b { color: var(--ha-h-ink); }
.ha-home-count { min-width: 28px; text-align: right; font-size: 13.5px; color: var(--ha-h-ink); }

/* the tabs: Overview, then each module's dashboard, kept in sight under the desk's bar as the page scrolls, and
   scrolling sideways where they do not fit */
.ha-home-tabbar {
	display: flex; gap: 4px; margin-top: 14px; padding: 5px; overflow-x: auto; scrollbar-width: thin;
	position: sticky; top: calc(var(--desktop-navbar-height, 52px) + 6px); z-index: 3;
	background: var(--ha-h-card); border: 1px solid var(--ha-h-line); border-radius: 14px;
	box-shadow: 0 6px 18px color-mix(in srgb, var(--ha-h-navy) 8%, transparent);
}
.ha-home .ha-home-tabbtn {
	flex: none; display: inline-flex; align-items: center; gap: 8px; padding: 8px 13px; border-radius: 10px;
	font-size: 13.5px; font-weight: 600; color: var(--ha-h-muted); white-space: nowrap;
}
.ha-home .ha-home-tabbtn:hover { background: color-mix(in srgb, var(--ha-h-navy) 6%, transparent); color: var(--ha-h-ink); }
.ha-home .ha-home-tabbtn:focus-visible { outline: 2px solid var(--ha-h-gold); outline-offset: 1px; }
.ha-home .ha-home-tabbtn.ha-on { background: var(--ha-h-navy); color: #fff; }
.ha-home .ha-home-tabbtn.ha-on .ha-home-icon { color: var(--ha-h-gold); }
.ha-home-tabbtn .ha-home-icon { width: 17px; height: 17px; }
.ha-home-badge {
	font-style: normal; font-size: 11px; font-weight: 700; line-height: 18px; min-width: 20px; padding: 0 6px;
	border-radius: 99px; text-align: center; color: #fff; background: var(--ha-band, var(--ha-h-muted));
}
/* the heading of a module's tab */
.ha-home-tabhead { display: flex; align-items: flex-end; justify-content: space-between; gap: 10px 16px; flex-wrap: wrap; margin: 18px 2px 0; }
.ha-home-tabhead h3 { margin: 0; font-size: 19px; font-weight: 700; color: var(--ha-h-ink); letter-spacing: -.01em; }
.ha-home-tabhead p { margin: 3px 0 0; font-size: 12.5px; color: var(--ha-h-muted); }
.ha-home-tabhead-side { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.ha-home-stamp { display: inline-flex; align-items: center; gap: 10px; font-size: 12.5px; color: var(--ha-h-muted); }
.ha-home .ha-home-refresh { display: inline-flex; align-items: center; gap: 5px; font-weight: 600; color: var(--hra-accent, #0A6ED1); }
.ha-home-refresh .ha-home-icon { width: 15px; height: 15px; }
.ha-home .ha-home-refresh.ha-busy .ha-home-icon { animation: ha-home-turn .9s linear infinite; }
@keyframes ha-home-turn { to { transform: rotate(360deg); } }
.ha-home .ha-home-into {
	display: inline-flex; align-items: center; gap: 8px; padding: 8px 14px; border-radius: 10px; font-size: 13px;
	font-weight: 600; color: var(--ha-h-ink); background: var(--ha-h-card); border: 1px solid var(--ha-h-line);
}
.ha-home .ha-home-into:hover { border-color: var(--ha-h-navy); }
.ha-home-card.ha-home-frame { cursor: default; }
/* a module's dashboards: two across, a wide one across both, the two of a row as tall as each other */
.ha-home-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-top: 14px; }
.ha-home-grid > .ha-home-panel.ha-home-wide { grid-column: 1 / -1; margin-top: 0; }
.ha-home-reports .ha-home-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 2px 8px; }
/* Needs Attention across the page: its checks side by side, as many as fit */
.ha-home-grid > .ha-home-attention.ha-home-wide .ha-home-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(380px, 100%), 1fr)); gap: 0 8px; }
.ha-home-grid .ha-home-list > .ha-home-empty { grid-column: 1 / -1; }
.ha-home-seeall { padding: 0 10px 10px; }
.ha-home .ha-home-all { display: inline-flex; align-items: center; gap: 4px; font-size: 12.5px; font-weight: 600; color: var(--hra-accent, #0A6ED1); }
.ha-home-all .ha-home-icon { width: 15px; height: 15px; }
/* Needs Attention: how many of each, in the band of how pressing it is */
.ha-home-check-count {
	min-width: 30px; height: 26px; padding: 0 8px; border-radius: 99px; flex: none; display: inline-grid; place-items: center;
	font-size: 12.5px; font-weight: 700; color: #fff; background: var(--ha-band, var(--hra-ink-muted, #546678));
}
/* six months of something: each month a column that opens its documents */
.ha-home .ha-home-column { border-radius: 8px; padding: 2px 0; text-align: center; }
.ha-home .ha-home-column:hover { background: color-mix(in srgb, var(--ha-h-navy) 6%, transparent); }
/* a ring of a whole's parts, in the theme's colours, the rest in the quiet gray */
.ha-home-donut-row {
	display: flex; align-items: center; gap: 16px; padding: 10px 10px 6px; flex-wrap: wrap;
	--ha-slice-0: var(--hra-primary, #14395E); --ha-slice-1: var(--hra-shell-marker, #F0AB00);
	--ha-slice-2: var(--hra-accent, #0A6ED1); --ha-slice-3: var(--hra-success, #256F3A);
	--ha-slice-4: var(--hra-amber-text, #B45309); --ha-slice-5: var(--hra-primary-soft, #5B8FC7);
	--ha-slice-6: var(--hra-danger, #A62B25); --ha-slice-rest: var(--hra-ink-muted, #546678);
}
.ha-home-donut { position: relative; width: 132px; height: 132px; flex: none; }
.ha-home-donut-ring { position: absolute; inset: 0; border-radius: 50%; }
.ha-home-donut-middle {
	position: absolute; inset: 21px; border-radius: 50%; background: var(--ha-h-card); display: flex; flex-direction: column;
	align-items: center; justify-content: center; text-align: center;
}
.ha-home-donut-middle b { font-size: 15px; color: var(--ha-h-ink); line-height: 1.15; }
.ha-home-donut-middle small { font-size: 11px; color: var(--ha-h-muted); }
.ha-home-slices { flex: 1 1 180px; min-width: 0; display: grid; gap: 2px; }
.ha-home .ha-home-slice {
	display: grid; grid-template-columns: 10px minmax(0, 1fr) auto auto; align-items: center; gap: 8px;
	width: 100%; padding: 6px 8px; border-radius: 9px;
}
.ha-home .ha-home-slice:hover { background: color-mix(in srgb, var(--ha-h-navy) 6%, transparent); }
.ha-home-slice > i { width: 10px; height: 10px; border-radius: 3px; }
.ha-home-slice b { font-size: 13px; color: var(--ha-h-ink); white-space: nowrap; }
.ha-home-slice small { font-size: 11.5px; color: var(--ha-h-muted); min-width: 32px; text-align: right; }

/* while the figures are on their way */
.ha-home-bone { height: 12px; border-radius: 6px; margin: 6px 0; background: linear-gradient(90deg, color-mix(in srgb, var(--hra-border-strong, #7E93AD) 16%, transparent), color-mix(in srgb, var(--hra-border-strong, #7E93AD) 30%, transparent), color-mix(in srgb, var(--hra-border-strong, #7E93AD) 16%, transparent)); background-size: 200% 100%; animation: ha-home-shine 1.3s linear infinite; }
.ha-home-hero .ha-home-bone { background: linear-gradient(90deg, rgba(255,255,255,.14), rgba(255,255,255,.30), rgba(255,255,255,.14)); background-size: 200% 100%; }
@keyframes ha-home-shine { from { background-position: 200% 0; } to { background-position: -200% 0; } }
@media (prefers-reduced-motion: reduce) { .ha-home-bone, .ha-home .ha-home-refresh.ha-busy .ha-home-icon { animation: none; } .ha-home * { transition: none !important; } }

/* Frappe's own tiles, as a list of modules: down the left of the home on a
   wide screen and under it on a narrow one, in the order of an employee's
   time with the company (order_rules). Only the tiles of the desk itself
   (child selectors all the way): a folder's thumbnails and the folder window
   keep Frappe's layout. Every rule stands aside while the desk is being
   edited, which is then exactly as Frappe draws it. */
${RAIL} {
	display: block; position: relative; box-sizing: border-box; width: auto; margin: 14px 20px 44px; padding: 57px 0 0;
	background: var(--card-bg, #fff); border: 1px solid var(--hra-border, #C3D0E0); border-radius: 14px; overflow: hidden;
}
${RAIL}::before {
	content: ""; position: absolute; left: 16px; top: 13px; width: 30px; height: 30px; border-radius: 9px;
	background: var(--hra-primary, #14395E) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23fff' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='4' y='4' width='6.5' height='6.5' rx='1.6'/%3E%3Crect x='13.5' y='4' width='6.5' height='6.5' rx='1.6'/%3E%3Crect x='4' y='13.5' width='6.5' height='6.5' rx='1.6'/%3E%3Crect x='13.5' y='13.5' width='6.5' height='6.5' rx='1.6'/%3E%3C/svg%3E") center / 18px 18px no-repeat;
}
${RAIL}::after {
	content: var(--ha-rail-title, "Modules"); position: absolute; left: 56px; right: 16px; top: 13px; height: 30px; line-height: 30px;
	font-size: 14.5px; font-weight: 700; color: var(--text-color, #1E2A3A); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
${RAIL} > .icons-container {
	display: block !important; width: 100% !important; max-width: none !important; margin: 0 !important; padding: 6px !important;
	box-sizing: border-box; border-top: 1px solid var(--hra-border, #C3D0E0);
}
${TILES} {
	position: relative; grid-template-columns: minmax(0, 1fr) !important; grid-template-rows: none !important;
	grid-auto-rows: auto !important; gap: 2px !important; justify-content: stretch !important; justify-items: stretch !important;
}
/* one line down the pictures, from the first module to the last */
${TILES}::before {
	content: ""; position: absolute; left: 27px; top: 25px; bottom: 25px; width: 2px; border-radius: 2px;
	background: var(--hra-border, #C3D0E0);
}
${TILES} > .desktop-icon {
	order: 1000; width: auto !important; height: auto !important; box-sizing: border-box; flex-direction: row !important; align-items: center !important;
	gap: 12px !important; padding: 7px 10px !important; border: 0 !important; border-radius: 10px !important; transition: background .12s ease;
}
${TILES} > .desktop-icon:hover { background: color-mix(in srgb, var(--hra-primary, #14395E) 7%, transparent); }
${TILES} > .desktop-icon::after {
	content: ""; flex: none; width: 7px; height: 7px; margin-right: 5px; border-top: 1.6px solid var(--text-muted, #5C6B82);
	border-right: 1.6px solid var(--text-muted, #5C6B82); transform: rotate(45deg); opacity: .6;
}
${TILES} > .desktop-icon > .icon-container {
	flex: none; padding: 0 !important; width: 36px !important; height: 36px !important; position: relative; z-index: 1;
	background: var(--card-bg, #fff);
}
${TILES} > .desktop-icon > .icon-container > img { width: 36px !important; height: 36px !important; }
${TILES} > .desktop-icon > .icon-container:hover { transform: none; }
${TILES} > .desktop-icon > .icon-caption {
	text-align: left !important; height: auto !important; text-wrap: wrap; min-width: 0; flex: 1 1 auto; max-width: none !important;
}
${TILES} > .desktop-icon > .icon-caption .icon-title {
	white-space: normal !important; overflow: visible; font-size: 13.5px; line-height: 1.25; color: var(--text-color, #1E2A3A);
}
.desktop-wrapper.ha-has-home[data-mode="Edit"] .ha-home { display: none; }

/* A module's own menu, opened by its arrow: the entries of its sidebar, one click from the desk. Both are
   hidden wherever their tile is, and shown only in the list: while the desk is edited, or on a tile Frappe
   has moved into a folder's window, nothing of them is seen. */
.ha-rail-toggle, .ha-rail-menu { display: none; }
${TILES} > .desktop-icon.ha-has-menu { flex-wrap: wrap !important; row-gap: 0 !important; }
${TILES} > .desktop-icon.ha-has-menu::after { display: none; }
/* the name takes what the picture and the arrow leave, and never a line of its own: Frappe gives it the full width */
${TILES} > .desktop-icon.ha-has-menu > .icon-caption { flex: 1 1 0; width: auto !important; }
${TILES} > .desktop-icon.ha-open:hover { background: none; }
${TILES} > .desktop-icon > .ha-rail-toggle {
	display: grid; flex: none; width: 26px; height: 26px; border-radius: 8px; place-items: center; cursor: pointer;
	color: var(--text-muted, #5C6B82); transition: transform .12s ease, background .12s ease;
}
${TILES} > .desktop-icon > .ha-rail-toggle:hover, ${TILES} > .desktop-icon > .ha-rail-toggle:focus-visible {
	background: color-mix(in srgb, var(--hra-primary, #14395E) 12%, transparent); outline: none;
}
${TILES} > .desktop-icon > .ha-rail-toggle > svg { width: 16px; height: 16px; }
${TILES} > .desktop-icon.ha-open > .ha-rail-toggle { transform: rotate(90deg); color: var(--hra-primary, #14395E); }
${TILES} > .desktop-icon > .ha-rail-menu { flex: 0 0 100%; box-sizing: border-box; min-width: 0; padding: 2px 0 6px 48px; cursor: default; }
${TILES} > .desktop-icon.ha-open > .ha-rail-menu { display: block; }
/* a heading opens and shuts the entries under it, in the theme's blue so it reads apart from them */
${TILES} > .desktop-icon > .ha-rail-menu .ha-rail-heading {
	display: flex; align-items: center; justify-content: space-between; gap: 6px; margin: 3px 0 1px; padding: 5px 8px;
	border-radius: 7px; font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; line-height: 1.3;
	cursor: pointer; color: var(--hra-primary-mid, #2A5A8C);
}
${TILES} > .desktop-icon > .ha-rail-menu .ha-rail-heading:hover, ${TILES} > .desktop-icon > .ha-rail-menu .ha-rail-heading:focus-visible {
	background: color-mix(in srgb, var(--hra-primary-mid, #2A5A8C) 10%, transparent); outline: none;
}
${TILES} > .desktop-icon > .ha-rail-menu .ha-rail-heading > svg { width: 13px; height: 13px; flex: none; transition: transform .12s ease; }
${TILES} > .desktop-icon > .ha-rail-menu .ha-rail-group.ha-shown > .ha-rail-heading > svg { transform: rotate(90deg); }
${TILES} > .desktop-icon > .ha-rail-menu .ha-rail-items { display: none; padding: 0 0 2px 8px; }
${TILES} > .desktop-icon > .ha-rail-menu .ha-rail-group.ha-shown > .ha-rail-items { display: block; }
${TILES} > .desktop-icon > .ha-rail-menu .ha-rail-link {
	display: block; padding: 5px 8px; border-radius: 7px; font-size: 12.5px; line-height: 1.3; cursor: pointer;
	color: var(--text-color, #1E2A3A);
}
${TILES} > .desktop-icon > .ha-rail-menu .ha-rail-link:hover, ${TILES} > .desktop-icon > .ha-rail-menu .ha-rail-link:focus-visible {
	background: color-mix(in srgb, var(--hra-primary, #14395E) 9%, transparent); color: var(--hra-primary, #14395E); outline: none;
}

/* The desk reaches the window's edges: the page Frappe holds it in is padded, and the navbar stopped short of
   them. bleed() measures how far in it sits. Its colour is the page's own, whatever the theme. It is as tall
   as what is on it: made as tall as the window, it scrolled by whatever Frappe puts under the page. */
.desktop-wrapper.ha-has-home:not([data-mode="Edit"]) {
	width: auto; max-width: none; box-sizing: border-box; background-color: inherit;
	margin: calc(-1 * var(--ha-bleed-t, 0px)) calc(-1 * var(--ha-bleed-r, 0px)) calc(-1 * var(--ha-bleed-b, 0px)) calc(-1 * var(--ha-bleed-l, 0px));
}

/* a wide screen: the modules down the left, the home beside them, from one
   edge of the window to the other. A flex row that wraps, not a grid: a grid
   would hold Frappe's sticky navbar to its own row, and it would scroll away.
   The home starts from nothing and grows to fill the row: a line breaks
   before it shrinks, and a home that started at its full width would drop
   under the list on a screen narrower than both. */
@media (min-width: 901px) {
	.desktop-wrapper.ha-has-home:not([data-mode="Edit"]) { display: flex; flex-wrap: wrap; align-items: flex-start; align-content: flex-start; justify-content: flex-start; column-gap: 16px; }
	.desktop-wrapper.ha-has-home:not([data-mode="Edit"]) > .desktop-navbar { flex: 0 0 100%; order: 0; }
	${RAIL} {
		/* the same 18px above and below: the list is as tall as the window allows, and a deeper margin
		   below would push it up under the navbar at the end of the page */
		order: 1; flex: 0 0 248px; width: 248px; margin: 18px 0 18px 20px; position: sticky;
		top: calc(var(--desktop-navbar-height, 52px) + 18px); max-height: calc(100vh - var(--desktop-navbar-height, 52px) - 36px);
		overflow-y: auto; scrollbar-width: thin;
	}
	.desktop-wrapper.ha-has-home:not([data-mode="Edit"]) > .ha-home { order: 2; flex: 1 1 0; min-width: 0; max-width: none; margin: 18px 20px 44px 0; padding: 0; }
}
@media (max-width: 1100px) {
	.ha-home-panels, .ha-home-panels.ha-home-two, .ha-home-panels.ha-home-three, .ha-home-grid { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 900px) {
	.ha-home-hero { padding: 18px; }
	.ha-home-hero h2 { font-size: 19px; }
}
@media (max-width: 560px) {
	.ha-home { padding: 0 16px; margin-top: 12px; }
	${RAIL} { margin: 12px 16px 32px; }
	.ha-home-hero-side { width: 100%; }
	.ha-home .ha-home-chip, .ha-home .ha-home-action { flex: 1 1 auto; justify-content: center; }
	.ha-home-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
	.ha-home-card-value { font-size: 24px; }
}
`;

	// last, once the styles above exist: the desk may already be on the page
	hrms_addon.home.show = arrive;
	$(document).on("page-change", arrive);
	$(document).on("desktop_screen", drawn_again);
	$(window).on("resize", resized);
	$(arrive);
})();
