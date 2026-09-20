// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Attendance Device", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Test Connection"), () =>
			frappe
				.xcall("hrms_addon.hrms_addon.devices.test_connection", { device: frm.doc.name })
				.then((found) => {
					frappe.msgprint({
						title: __("{0} answered", [frm.doc.name]),
						indicator: "green",
						message: [
							__("Serial number: {0}", [found.serial_number || "-"]),
							__("Firmware: {0}", [found.firmware || "-"]),
							__("Device time: {0}", [found.device_time || "-"]),
							__("Users enrolled: {0}", [found.users]),
						].join("<br>"),
					});
					frm.reload_doc();
				})
		);
		frm.add_custom_button(__("Pull Now"), () =>
			frappe
				.xcall("hrms_addon.hrms_addon.devices.pull", { device: frm.doc.name })
				.then((found) => {
					frappe.msgprint({
						title: __("Read {0}", [frm.doc.name]),
						indicator: found.failed ? "orange" : "green",
						message: [
							__("{0} punches read, {1} new.", [found.read, found.new]),
							__("{0} repeat readings collapsed.", [found.collapsed]),
							__("{0} pushed, {1} already there.", [found.pushed, found.duplicate]),
							found.unknown ? __("{0} belong to no employee.", [found.unknown]) : "",
							found.failed ? __("{0} could not be pushed — see the device logs.", [found.failed]) : "",
						]
							.filter(Boolean)
							.join("<br>"),
					});
					frm.reload_doc();
				})
		);
		frm.add_custom_button(
			__("Push What Never Landed"),
			() =>
				frappe
					.xcall("hrms_addon.hrms_addon.devices.retry_failed", { device: frm.doc.name })
					.then((found) =>
						frappe.show_alert({
							message: __("{0} pushed, {1} still unknown, {2} failed.", [
								found.pushed,
								found.unknown,
								found.failed,
							]),
							indicator: found.failed ? "orange" : "green",
						})
					),
			__("Logs")
		);
		frm.add_custom_button(
			__("Device Logs"),
			() => frappe.set_route("List", "Attendance Device Log", { device: frm.doc.name }),
			__("Logs")
		);
		if (frm.doc.last_error) {
			frm.dashboard.set_headline(
				`<span class="indicator-pill red">${frappe.utils.escape_html(__("Last error"))}</span> ` +
					frappe.utils.escape_html(frm.doc.last_error)
			);
		} else if (frm.doc.last_sync) {
			frm.dashboard.set_headline(
				frappe.utils.escape_html(
					__("Last synced {0} — {1}", [
						frappe.datetime.str_to_user(frm.doc.last_sync),
						frm.doc.last_status || "",
					])
				)
			);
		}
	},
});
