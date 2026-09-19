// Job Application Form (/apply): the careers portal's application, with the
// Pre-Interview Bio-Data Form (LPL/HR/19) as optional steps 2 to 4.
//
// Frappe renders this file through Jinja before sending it
// (frappe/website/doctype/web_form/web_form.py add_custom_context_and_script),
// so it must not contain Jinja delimiters. The web form's client_script
// calls hrms_addon_apply.init() once the form has loaded.
//
// A CV is personal data: the server stores every upload from the website
// private (hrms_addon/hrms_addon/uploads.py), so the upload dialog starts
// private and offers no public / private choice (the .css hides the box).

window.hrms_addon_apply = {
	init() {
		this.private_uploads();
		const job_opening = frappe.utils.get_query_params().job_title;
		if (!job_opening) {
			return;
		}
		// Most candidates are not logged in, and a guest may not read Job
		// Opening, so the title comes from a guest-safe method that only
		// describes published openings.
		frappe.call({
			method: "hrms_addon.hrms_addon.careers.get_opening_summary",
			args: { job_opening: job_opening },
			callback: (r) => this.show_opening(r.message),
		});
	},

	private_uploads() {
		Object.values(frappe.web_form.fields_dict || []).forEach((field) => {
			if (["Attach", "Attach Image"].includes(field.df.fieldtype)) {
				field.df.options = Object.assign({}, field.df.options, {
					make_attachments_public: 0,
					allow_toggle_private: false,
				});
			}
		});
	},

	show_opening(opening) {
		if (!opening) {
			return;
		}
		$(".web-form-title h1").text(__("Apply for {0}", [opening.job_title]));

		const field = frappe.web_form.fields_dict.job_title;
		if (field) {
			$(field.wrapper).find(".control-value, .like-disabled-input").text(opening.job_title);
		}

		const facts = [
			opening.company,
			opening.location,
			opening.employment_type,
			opening.closes_on ? __("Closes {0}", [opening.closes_on]) : null,
		].filter(Boolean);
		if (facts.length && !$(".lpl-apply-summary").length) {
			const summary = $('<div class="lpl-apply-summary"></div>');
			facts.forEach((fact) => $("<span></span>").text(fact).appendTo(summary));
			summary.insertAfter(".web-form-head .title");
		}
	},
};
