// Copyright (c) 2026, CyveTech and contributors
// For license information, please see license.txt

// Attendance Deletion: choose the dates and people, see the count, type it to
// delete. One job does it in the background and this page follows it
// (attendance_deletions.py). fetch, not frappe.call, for following it: a
// moment's trouble reaching the server should not raise a dialog every few seconds.
const HA_ATTENDANCE_DELETION = "hrms_addon.hrms_addon.attendance_deletions.";
const HA_ATTENDANCE_DELETION_RUNNING = ["Queued", "Deleting"];
const HA_ATTENDANCE_DELETION_ON_HOLD = ["Stopped", "Failed"];
const HA_ATTENDANCE_DELETION_EVERY = 5000;
let ha_attendance_deletion_timer = null;

frappe.ui.form.on("Attendance Deletion", {
	setup(frm) {
		frm.set_query("department", () => ({ filters: { company: frm.doc.company } }));
		frm.set_query("employee", () => ({ filters: { company: frm.doc.company } }));
	},

	refresh(frm) {
		ha_attendance_deletion_form(frm);
	},
});

function ha_attendance_deletion_form(frm) {
	clearTimeout(ha_attendance_deletion_timer);
	ha_attendance_deletion_timer = null;
	frm.clear_custom_buttons();
	frm.layout.message.find(".ha-deletion-hint").remove();
	const doc = frm.doc;
	const stopped = (doc.__onload || {}).stopped;
	const running = HA_ATTENDANCE_DELETION_RUNNING.includes(doc.status) && !stopped;

	if (frm.is_new()) {
		ha_attendance_deletion_hint(frm, __("Choose the dates and save to see how many records this would delete."));
	} else if (running) {
		ha_attendance_deletion_hint(frm, __("Deleting in the background. You can close this page."), "blue");
		frm.add_custom_button(__("Stop"), () => ha_attendance_deletion_call(frm, "stop"));
		ha_attendance_deletion_follow(frm);
	} else if (stopped || HA_ATTENDANCE_DELETION_ON_HOLD.includes(doc.status)) {
		ha_attendance_deletion_hint(
			frm,
			doc.message || __("{0} deleted so far. Press Resume to go on from where it stopped.", [ha_attendance_number(doc.deleted)]),
			"orange"
		);
		frm.add_custom_button(__("Resume"), () => ha_attendance_deletion_call(frm, "start")).addClass("btn-primary");
	} else if (doc.status === "Finished") {
		let result = __("{0} deleted, {1} kept.", [ha_attendance_number(doc.deleted), ha_attendance_number(doc.kept)]);
		if (cint(doc.draft_slips)) result += " " + __("Use Recreate Salary Slips on any draft payroll for these dates.");
		ha_attendance_deletion_hint(frm, result, "green");
	} else if (cint(doc.to_delete)) {
		ha_attendance_deletion_hint(frm, ha_attendance_deletion_count(doc));
		frm.add_custom_button(__("Delete {0} Records", [ha_attendance_number(doc.to_delete)]), () =>
			ha_attendance_deletion_confirm(frm)
		).addClass("btn-primary");
	} else {
		ha_attendance_deletion_hint(frm, __("No records to delete."));
	}

	if (!frm.is_new() && doc.status !== "Draft" && cint(doc.keep_deleted)) {
		frm.add_custom_button(__("Let Auto Attendance Fill These Days"), () => {
			frappe.confirm(__("Auto attendance may mark these days again from its next run. Go on?"), () =>
				ha_attendance_deletion_call(frm, "release")
			);
		});
	}
}

function ha_attendance_number(value) {
	return format_number(cint(value), null, 0);
}

function ha_attendance_deletion_kept(doc) {
	return cint(doc.kept_on_slips) + cint(doc.kept_from_requests) + cint(doc.kept_in_use);
}

function ha_attendance_deletion_count(doc) {
	return __("{0} records will be deleted and {1} kept.", [
		ha_attendance_number(doc.to_delete),
		ha_attendance_number(ha_attendance_deletion_kept(doc)),
	]);
}

function ha_attendance_deletion_hint(frm, text, colour) {
	frm.set_intro(text, colour);
	if (frm.$intro_message) frm.$intro_message.addClass("ha-deletion-hint");
}

function ha_attendance_deletion_call(frm, method) {
	return frappe
		.call({ method: HA_ATTENDANCE_DELETION + method, args: { deletion: frm.doc.name }, freeze: true })
		.then(() => frm.reload_doc());
}

// the count asked for again first: it is the count as it now stands that goes, and that is typed
function ha_attendance_deletion_confirm(frm) {
	const saved = frm.is_dirty() ? frm.save() : Promise.resolve();
	saved
		.then(() =>
			frappe.call({
				method: HA_ATTENDANCE_DELETION + "check",
				args: { deletion: frm.doc.name },
				freeze: true,
				freeze_message: __("Counting"),
			})
		)
		.then((answer) => {
			const counted = cint((answer.message || {}).to_delete);
			if (!counted) {
				frm.reload_doc();
				return;
			}
			frappe.prompt(
				{ fieldname: "confirmed", fieldtype: "Int", reqd: 1, label: __("Type {0} to delete them", [counted]) },
				(values) => {
					frappe
						.call({
							method: HA_ATTENDANCE_DELETION + "start",
							args: { deletion: frm.doc.name, confirmed: values.confirmed },
							freeze: true,
							freeze_message: __("Counting"),
						})
						.then(() => frm.reload_doc());
				},
				__("Delete {0} Attendance Records", [ha_attendance_number(counted)]),
				__("Delete")
			);
		});
}

function ha_attendance_deletion_follow(frm) {
	const name = frm.doc.name;
	const total = cint(frm.doc.to_delete) + ha_attendance_deletion_kept(frm.doc);
	const show = (deleted, kept) => {
		const done = cint(deleted) + cint(kept);
		const percent = total ? Math.min(100, (done * 100) / total) : 0;
		frm.dashboard.show_progress(__("Deleting"), percent, __("{0} of {1}", [ha_attendance_number(done), ha_attendance_number(total)]));
	};
	const again = () => {
		ha_attendance_deletion_timer = setTimeout(ask, HA_ATTENDANCE_DELETION_EVERY);
	};
	const ask = () => {
		// the person has moved to another deletion or another page: leave them be
		if (cur_frm !== frm || frm.doc.name !== name) return;
		fetch("/api/method/" + HA_ATTENDANCE_DELETION + "progress?deletion=" + encodeURIComponent(name), {
			credentials: "same-origin",
			cache: "no-store",
			headers: { Accept: "application/json" },
		})
			.then((response) => (response.ok ? response.json() : null))
			.catch(() => null)
			.then((body) => {
				if (cur_frm !== frm || frm.doc.name !== name) return;
				const state = body && body.message;
				if (!state) return again();
				if (!HA_ATTENDANCE_DELETION_RUNNING.includes(state.status)) return frm.reload_doc();
				show(state.deleted, state.kept);
				again();
			});
	};
	show(frm.doc.deleted, frm.doc.kept);
	again();
}
