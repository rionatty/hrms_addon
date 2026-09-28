// HRMS Addon — the result of a training (Frappe HR's Training Result): only
// the participants marked Present can be given one, each once; the marks
// say whether the training was effective. See hrms_addon/hrms_addon/training.py.

frappe.ui.form.on("Training Result", {
	setup(frm) {
		frm.set_query("employee", "employees", () => {
			const listed = (frm.doc.employees || []).map((row) => row.employee).filter(Boolean);
			const present = (frm.__present || []).filter((employee) => !listed.includes(employee));
			return { filters: { name: ["in", present.length ? present : [""]] } };
		});
	},
	refresh(frm) {
		load_present(frm);
	},
	training_event(frm) {
		load_present(frm);
	},
});

function load_present(frm) {
	frm.__present = [];
	if (!frm.doc.training_event) return;
	frappe
		.xcall("hrms_addon.hrms_addon.training.result_employees", { training_event: frm.doc.training_event })
		.then((rows) => (frm.__present = (rows || []).map((row) => row.employee)));
}
