// The months of a payroll year are made from its dates when it is saved
// (payroll_months.py): a month's Status is all there is to change here.
frappe.ui.form.on("Payroll Period", {
	refresh(frm) {
		if (!frm.get_field("custom_months")) return;
		frm.set_df_property("custom_months", "cannot_add_rows", 1);
		frm.set_df_property("custom_months", "cannot_delete_rows", 1);
	},
});
