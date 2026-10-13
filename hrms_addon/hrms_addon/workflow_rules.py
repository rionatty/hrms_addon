# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""What a submit may do to a document that is approved step by step.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_plain_submit.py checks it without a bench. workflows.py holds
the hook that asks it (refuse_plain_submit).

WHY

An approval here is a Frappe Workflow whose last step submits the document:
Frappe's apply_workflow sets the next state, then submits. Every check a
step makes hangs on the state changing (each module's validate compares the
state before the save with the state now).

A submit that does not come from a step changes no state, so validate sees
nothing to check. Frappe then moves the document itself, after validate has
run, to the first state that submits (frappe/model/document.py _validate ->
validate_workflow -> frappe/model/workflow.py set_workflow_state_on_action).
A Clearance Form in Draft, submitted that way, came out Cleared with no item
accounted for, no box signed and nobody having approved it (Luuka, 13 Oct
2026). The desk hides Submit while a workflow is active, but the API, an
import and a stale copy of the form in a browser do not.

  submitting_states  the states of a workflow that submit the document
  skips_approval     whether submitting a document at this state skips the
                     steps before it
  opening_state      the state a new document is given, where it came with
                     another

A NEW DOCUMENT OPENS AT THE FIRST STATE

Amend copies every field of the cancelled document, its workflow state among
them: frappe/public/js/frappe/model/create_new.js copy_doc honours no_copy
only when it is not an amendment, and the form sets the default state only
on an empty field. Frappe then refuses the copy on its first save, a new
document being allowed the first state and no other ("Workflow State
transition not allowed from Draft to Cancelled", frappe/model/workflow.py
validate_workflow). So a cancelled document of any of these workflows could
not be amended. It is given the first state before Frappe looks.
"""


def submitting_states(states):
    """The states that submit the document, in the workflow's own order.
    states: rows of {"state", "doc_status"}; no doc_status is a draft."""
    return [row.get("state") for row in states or [] if str(row.get("doc_status") or "0").strip() == "1"]


def skips_approval(states, state):
    """Whether a submit of a document standing at `state` skips its approval.

    It does not when the state is already one that submits: that is how a
    step arrives (the state is set, then the document submitted), and how
    code that knows the outcome writes one. It does not either on a
    workflow with no state that submits: there the workflow only follows a
    document that is submitted the ordinary way.
    """
    submitting = submitting_states(states)
    return bool(submitting) and state not in submitting


def opening_state(states, state):
    """The state to give a new document that came with `state`, or None
    where it needs none: it has the first state already, has no state yet
    (Frappe gives it the first), or the workflow has no states."""
    first = (states[0].get("state") if states else None) or None
    if not first or not state or state == first:
        return None
    return first
