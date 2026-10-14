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

(function () {
	if (typeof frappe === "undefined" || !frappe.boot) return;
	if (!frappe.boot.hrms_addon_home) return;
	if (frappe.session && frappe.session.user === "Guest") return;
	frappe.provide("hrms_addon.home");

	const METHOD = "hrms_addon.hrms_addon.home.summary";
	const FRESH_MS = 60 * 1000; // how long an answer is shown before it is asked for again
	const STYLE_ID = "ha-home-style";
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
	let tab = "items";
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
		home.innerHTML = hero(data) + cards(data) + panels(data);
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
				else if (there && !answer) unmount(desk()); // nothing to show: the desk as Frappe drew it
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

/* while the figures are on their way */
.ha-home-bone { height: 12px; border-radius: 6px; margin: 6px 0; background: linear-gradient(90deg, rgba(127,147,173,.16), rgba(127,147,173,.30), rgba(127,147,173,.16)); background-size: 200% 100%; animation: ha-home-shine 1.3s linear infinite; }
.ha-home-hero .ha-home-bone { background: linear-gradient(90deg, rgba(255,255,255,.14), rgba(255,255,255,.30), rgba(255,255,255,.14)); background-size: 200% 100%; }
@keyframes ha-home-shine { from { background-position: 200% 0; } to { background-position: -200% 0; } }
@media (prefers-reduced-motion: reduce) { .ha-home-bone { animation: none; } .ha-home * { transition: none !important; } }

/* Frappe's own tiles, as a list of modules: down the left of the home on a
   wide screen and under it on a narrow one, in the order of an employee's
   time with the company (order_rules). Only the tiles of the desk itself
   (child selectors all the way): a folder's thumbnails and the folder window
   keep Frappe's layout. Every rule stands aside while the desk is being
   edited, which is then exactly as Frappe draws it. */
${RAIL} {
	display: block; position: relative; box-sizing: border-box; width: auto; margin: 14px 20px 44px; padding: 57px 0 0;
	background: var(--card-bg, #fff); border: 1px solid var(--hra-border, #D7DEEA); border-radius: 14px; overflow: hidden;
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
	box-sizing: border-box; border-top: 1px solid var(--hra-border, #D7DEEA);
}
${TILES} {
	position: relative; grid-template-columns: minmax(0, 1fr) !important; grid-template-rows: none !important;
	grid-auto-rows: auto !important; gap: 2px !important; justify-content: stretch !important; justify-items: stretch !important;
}
/* one line down the pictures, from the first module to the last */
${TILES}::before {
	content: ""; position: absolute; left: 27px; top: 25px; bottom: 25px; width: 2px; border-radius: 2px;
	background: var(--hra-border, #D7DEEA);
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
	.ha-home-panels { grid-template-columns: minmax(0, 1fr); }
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
