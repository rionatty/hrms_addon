// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("BioTime Server", {
	refresh(frm) {
		frm.trigger("say_where_it_got_to");
		if (frm.is_new() || !frm.doc.enabled) return;
		frm.add_custom_button(__("Test the Connection"), () =>
			frappe
				.xcall("hrms_addon.hrms_addon.biotime.test_connection")
				.then((found) => {
					const terminals = Object.entries(found.terminals || {});
					frappe.msgprint({
						title: __("BioTime answered"),
						indicator: "green",
						message: [
							__("{0} punch(es) in the last day, {1} usable.", [
								found.punches,
								found.usable,
							]),
							terminals.length
								? __("Terminals seen:") +
								  "<ul>" +
								  terminals
										.map(
											([serial, name]) =>
												`<li>${frappe.utils.escape_html(name || __("unnamed"))} <span class="text-muted">${frappe.utils.escape_html(serial)}</span></li>`
										)
										.join("") +
								  "</ul>"
								: __("No terminal was named on those punches."),
						].join("<br>"),
					});
					frm.reload_doc();
				})
		);
		frm.add_custom_button(__("Pull Now"), () =>
			frappe.xcall("hrms_addon.hrms_addon.biotime.pull").then((found) => {
				frappe.msgprint({
					title: __("Pulled from BioTime"),
					indicator: found.failed ? "orange" : "green",
					message: __(
						"Read {0}, pushed {1}. {2} unknown badge(s), {3} already there, {4} failed, {5} with no terminal named.",
						[
							found.read,
							found.pushed,
							found.unknown,
							found.duplicate,
							found.failed,
							found.no_terminal,
						]
					),
				});
				frm.reload_doc();
			})
		);
		frm.add_custom_button(__("Punches"), () => frappe.set_route("List", "Attendance Device Log"));
	},
	say_where_it_got_to(frm) {
		frm.dashboard.clear_headline();
		if (frm.is_new()) return;
		if (!frm.doc.enabled) {
			frm.dashboard.set_headline(
				`<span class="indicator-pill gray">${__(
					"Off — each machine is dialled directly, as before"
				)}</span>`
			);
			return;
		}
		if (!frm.doc.last_sync) {
			frm.dashboard.set_headline(
				`<span class="indicator-pill orange">${__("Never read")}</span>` +
					` <span>${__("The first pull reaches back {0} day(s).", [
						frm.doc.first_pull_days || 7,
					])}</span>`
			);
			return;
		}
		frm.dashboard.set_headline(
			`<span>${__("Read up to")} <b>${frappe.datetime.str_to_user(frm.doc.last_sync)}</b></span>` +
				` <span class="indicator-pill ${frm.doc.last_error ? "red" : "green"}">${frappe.utils.escape_html(
					frm.doc.last_status || __("Ready")
				)}</span>`
		);
	},
	base_url(frm) {
		const url = (frm.doc.base_url || "").trim();
		if (url && !url.startsWith("http://") && !url.startsWith("https://")) {
			frappe.show_alert({
				message: __("The address starts http:// or https://."),
				indicator: "red",
			});
		}
		if (url.startsWith("http://") && frm.doc.verify_tls) {
			frm.set_value("verify_tls", 0);
		}
	},
});
