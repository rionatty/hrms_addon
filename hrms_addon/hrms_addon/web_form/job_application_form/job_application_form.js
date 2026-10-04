// Job Application Form (/apply): the careers portal's application (phone,
// CV and cover letter required), with education, experience, skills and
// salary as optional steps 2 and 3. The personal details of the Bio-Data
// Form (LPL/HR/19) are not asked here: they are taken at onboarding.
//
// Frappe renders this file through Jinja before sending it
// (frappe/website/doctype/web_form/web_form.py add_custom_context_and_script),
// so it must not contain Jinja delimiters. The web form's client_script
// calls hrms_addon_apply.init() once the form has loaded.
//
// A CV is personal data: the server stores every upload from the website
// private (hrms_addon/hrms_addon/uploads.py), so the upload dialog starts
// private and offers no public / private choice (the .css hides the box).
//
// SAVE FOR LATER
//
// A candidate can leave an application half done and finish it another
// time. What they have typed, and the CV they attached, is kept on their own
// device (localStorage, per opening), as they type and when they press Save
// for later, and comes back when they open the form again. Nothing is sent
// anywhere until they apply, so no account, code or emailed link is needed;
// applying, or Discard, clears it.

const HA_APPLY_DRAFT = "hrms_addon:apply:";
const HA_APPLY_SKIP = ["job_title", "custom_screening_answers"];

window.hrms_addon_apply = {
	init() {
		this.private_uploads();
		this.save_for_later();
		const job_opening = frappe.utils.get_query_params().job_title;
		if (!job_opening) {
			this.restore_draft();
			return;
		}
		// Most candidates are not logged in, and a guest may not read Job
		// Opening, so the title comes from a guest-safe method that only
		// describes published openings.
		frappe.call({
			method: "hrms_addon.hrms_addon.careers.get_opening_summary",
			args: { job_opening: job_opening },
			callback: (r) => {
				this.show_opening(r.message);
				this.show_questions(r.message);
				this.restore_draft();
			},
		});
	},

	draft_key() {
		return HA_APPLY_DRAFT + (frappe.utils.get_query_params().job_title || "any");
	},

	// the Save for later button beside Submit, saving as the candidate types,
	// and clearing once they apply or discard
	save_for_later() {
		$(".web-form-actions .submit-btn").each((index, submit) => {
			if ($(submit).siblings(".lpl-save-later").length) return;
			$('<button type="button" class="lpl-save-later btn btn-default btn-sm ml-2"></button>')
				.text(__("Save for later"))
				.on("click", (event) => {
					event.preventDefault();
					if (this.save_draft()) {
						frappe.show_alert({
							message: __("Saved on this device. Come back to this page any time to finish."),
							indicator: "green",
						});
					}
				})
				.insertBefore(submit);
		});
		let timer = null;
		$(".web-form").on("input change", () => {
			clearTimeout(timer);
			timer = setTimeout(() => this.save_draft(), 800);
		});
		$(".discard-btn").on("click", () => this.clear_draft());
		frappe.web_form.after_save = () => this.clear_draft();
	},

	save_draft() {
		try {
			const values = frappe.web_form.get_values(true) || {};
			HA_APPLY_SKIP.forEach((fieldname) => delete values[fieldname]);
			window.localStorage.setItem(this.draft_key(), JSON.stringify({ saved_on: Date.now(), values }));
			return true;
		} catch (error) {
			return false; // a private window or blocked storage: the form still works, unsaved
		}
	},

	restore_draft() {
		let draft = null;
		try {
			draft = JSON.parse(window.localStorage.getItem(this.draft_key()) || "null");
		} catch (error) {
			draft = null;
		}
		const values = (draft && draft.values) || {};
		const fieldnames = Object.keys(values).filter(
			(fieldname) => !HA_APPLY_SKIP.includes(fieldname) && frappe.web_form.fields_dict[fieldname]
		);
		if (!fieldnames.length) return;
		const wanted = {};
		fieldnames.forEach((fieldname) => (wanted[fieldname] = values[fieldname]));
		frappe.web_form.set_values(wanted);
		const note = $('<div class="lpl-apply-draft"></div>')
			.text(__("Your saved application is back. "))
			.append(
				$('<a href="#"></a>')
					.text(__("Start again"))
					.on("click", (event) => {
						event.preventDefault();
						this.clear_draft();
						window.location.reload();
					})
			);
		$(".lpl-apply-draft").remove();
		note.insertAfter(".web-form-head .title");
	},

	clear_draft() {
		try {
			window.localStorage.removeItem(this.draft_key());
		} catch (error) {
			/* nothing was kept */
		}
	},

	// The opening's screening questions, one row each, to answer: the
	// applicant neither adds nor removes rows.
	show_questions(opening) {
		const field = frappe.web_form.fields_dict.custom_screening_answers;
		const questions = (opening && opening.screening_questions) || [];
		if (!field || !questions.length) {
			return;
		}
		field.df.cannot_add_rows = true;
		field.df.cannot_delete_rows = true;
		field.df.data = questions.map((question, index) => ({
			idx: index + 1,
			question: question.question,
			question_id: question.name,
			answer_type: question.answer_type === "Number" ? __("A number") : __("Yes or No"),
			answer: "",
		}));
		frappe.web_form.set_df_property("custom_screening_answers", "hidden", 0);
		field.grid.refresh();
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
