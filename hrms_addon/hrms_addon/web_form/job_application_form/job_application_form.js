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
// device (localStorage, per opening) as they type, and comes back when they
// open the form again there. Save for later also emails them a link that
// brings it back on any phone or computer, screening answers included, for
// 30 days (careers.save_draft; Luuka, 5 Nov 2026: "an option for temporary
// saving so that someone can start from there anytime"). The link's key goes
// only in that email. Applying, or Discard, clears the device's copy; applying
// removes the saved one.

const HA_APPLY_DRAFT = "hrms_addon:apply:";
const HA_APPLY_SKIP = ["job_title", "custom_screening_answers"];

window.hrms_addon_apply = {
	init() {
		this.private_uploads();
		this.save_for_later();
		this.place_table_dropdowns();
		const params = frappe.utils.get_query_params();
		const job_opening = params.job_title;
		// the emailed link first, else what this device kept
		const restore = () => (params.draft ? this.restore_emailed(params.draft) : this.restore_draft());
		if (!job_opening) {
			restore();
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
				restore();
			},
		});
	},

	draft_key() {
		return HA_APPLY_DRAFT + (frappe.utils.get_query_params().job_title || "any");
	},

	// A table cell's drop-down (Qualification Type and the like) opens under the cell. Frappe moves it beside the table
	// as the cell takes focus and places it by the cell's place in the window less the table's place in the page
	// (grid_row.js): the two agree only at the top of the page, so once the candidate has scrolled down to the tables
	// it opened that far above the cell. This runs after Frappe's own, and places it again, by the window alone.
	place_table_dropdowns() {
		$(document)
			.off("focusin.lpl-dropdown")
			.on("focusin.lpl-dropdown", ".web-form .grid-field .grid-static-col", (event) => {
				const input = event.target;
				const $grid_field = $(event.currentTarget).closest(".grid-field");
				const $wrapper = $grid_field
					.children("div.awesomplete")
					.filter((index, wrapper) => wrapper.style.position === "absolute")
					.last();
				if (!$wrapper.length || !input || !input.getBoundingClientRect) return;
				const box = $wrapper[0].offsetParent || $grid_field[0];
				const cell = input.getBoundingClientRect();
				const around = box.getBoundingClientRect();
				$wrapper.css({
					top: `${cell.bottom - around.top + box.scrollTop + 4}px`,
					left: `${cell.left - around.left + box.scrollLeft}px`,
				});
			});
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
					this.save_draft();
					this.email_panel();
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

	// what is sent to be kept: the form's values, and the screening answers
	// by question
	draft_values() {
		const values = frappe.web_form.get_values(true) || {};
		const answers = {};
		(values.custom_screening_answers || []).forEach((row) => {
			if (row.question_id && row.answer) answers[row.question_id] = row.answer;
		});
		HA_APPLY_SKIP.forEach((fieldname) => delete values[fieldname]);
		values.custom_screening_answers = answers;
		return values;
	},

	// where to send the link: the email typed on the form, and a button
	email_panel() {
		const shown = $(".lpl-save-later-mail");
		if (shown.length) {
			shown.find("input").trigger("focus");
			return;
		}
		const panel = $(
			'<div class="lpl-save-later-mail"><p></p><div class="lpl-save-later-row">' +
				'<input type="email" class="form-control input-sm">' +
				'<button type="button" class="btn btn-primary btn-sm"></button></div></div>'
		);
		panel
			.find("p")
			.text(__("We will email you a link that opens your application on any phone or computer, for 30 days."));
		panel
			.find("input")
			.val((frappe.web_form.get_values(true) || {}).email_id || "")
			.attr("placeholder", __("Your email"));
		panel
			.find("button")
			.text(__("Email me the link"))
			.on("click", () => this.email_link(panel));
		panel.insertAfter($(".web-form-actions").first());
		panel.find("input").trigger("focus");
	},

	email_link(panel) {
		const email = (panel.find("input").val() || "").trim();
		if (!email) {
			frappe.show_alert({ message: __("Give the email address to send the link to."), indicator: "orange" });
			return;
		}
		frappe.call({
			method: "hrms_addon.hrms_addon.careers.save_draft",
			type: "POST",
			args: {
				email: email,
				job_opening: frappe.utils.get_query_params().job_title || null,
				values: JSON.stringify(this.draft_values()),
			},
			btn: panel.find("button"),
			callback: (r) => {
				panel.remove();
				frappe.show_alert({
					message: __("Saved. The link is on its way to {0}.", [(r.message || {}).sent_to || email]),
					indicator: "green",
				});
			},
		});
	},

	// the emailed link: the application as it was saved, while it is kept
	restore_emailed(key) {
		frappe.call({
			method: "hrms_addon.hrms_addon.careers.load_draft",
			args: { key: key },
			callback: (r) => {
				const found = r.message || {};
				if (!found.values) {
					frappe.show_alert({
						message: __("That link has expired. Anything kept on this device is shown."),
						indicator: "orange",
					});
					this.restore_draft();
					return;
				}
				this.apply_values(found.values);
			},
		});
	},

	restore_draft() {
		let draft = null;
		try {
			draft = JSON.parse(window.localStorage.getItem(this.draft_key()) || "null");
		} catch (error) {
			draft = null;
		}
		this.apply_values((draft && draft.values) || {});
	},

	// values kept, back on the form, and the screening answers on their questions
	apply_values(values) {
		const answers = values.custom_screening_answers || {};
		const fieldnames = Object.keys(values).filter(
			(fieldname) => !HA_APPLY_SKIP.includes(fieldname) && frappe.web_form.fields_dict[fieldname]
		);
		const grid = (frappe.web_form.fields_dict.custom_screening_answers || {}).grid;
		const rows = (grid && grid.df.data) || [];
		const answered = rows.filter((row) => answers[row.question_id]);
		if (!fieldnames.length && !answered.length) return;
		const wanted = {};
		fieldnames.forEach((fieldname) => (wanted[fieldname] = values[fieldname]));
		frappe.web_form.set_values(wanted);
		if (answered.length) {
			answered.forEach((row) => (row.answer = answers[row.question_id]));
			grid.refresh();
		}
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
