// HRMS Addon — the Training Evaluation Form (LPL/TRG/FRM05) on Frappe HR's
// Training Feedback: a new one lists the form's items to rate, and the score
// shows as the ratings are ticked. See hrms_addon/hrms_addon/training.py.

const HA_RATING_VALUES = { Excellent: 5, "Very Good": 4, Good: 3, Average: 2, "Below Average": 1 };

function ha_score(frm) {
	const values = (frm.doc.custom_ratings || [])
		.map((row) => HA_RATING_VALUES[row.rating])
		.filter((v) => v);
	if (!values.length) {
		frm.set_value("custom_score", null);
		frm.set_value("custom_band", null);
		return;
	}
	const percent = Math.round((1000 * values.reduce((a, b) => a + b, 0)) / (5 * values.length)) / 10;
	const band = percent >= 90 ? "Excellent" : percent >= 75 ? "Very Good" : percent >= 60 ? "Good" : percent >= 50 ? "Average" : "Below Average";
	frm.set_value("custom_score", percent);
	frm.set_value("custom_band", band);
}

frappe.ui.form.on("Training Feedback", {
	onload(frm) {
		if (frm.is_new() && !(frm.doc.custom_ratings || []).length) {
			frappe.db
				.get_list("Training Evaluation Item", { fields: ["name"], order_by: "creation asc", limit: 50 })
				.then((items) => {
					for (const item of items) frm.add_child("custom_ratings", { item: item.name });
					frm.refresh_field("custom_ratings");
				});
		}
	},
});

frappe.ui.form.on("Training Evaluation Rating", {
	rating(frm) {
		ha_score(frm);
	},
	custom_ratings_remove(frm) {
		ha_score(frm);
	},
});
