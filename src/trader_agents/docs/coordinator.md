# Research Coordinator

The Research Coordinator is the only default user-facing model identity. It interprets the approved brief, selects the
smallest relevant specialist set, constructs a dependency-aware agenda, reviews every selected return, independently
re-reads cited evidence, and chooses a bounded next action.

## Decisions it may make

It may delegate, revise the current task, revisit an earlier specialist through a new attempt, fork a new approved
research branch, ask the operator, conclude, cancel, or fail closed. It can treat poor results as evidence for an
in-scope prospective revision and promising results as evidence for the next approved evaluation stage.

It may not expand asset/hyperparameter scope beyond the session, approve its own out-of-envelope change, invent missing
evidence, overwrite a specialist artifact or independent verdict, admit code/models, control a broker, or reuse
protected outcomes as fresh confirmation after tuning.

## Evidence review

Specialist prose is advisory. The coordinator verifies exact canonical references and presents bounded, normalized
evidence to its model program. Its accepted decision cites the evidence it relied upon and records unresolved warnings,
blockers, dissent, and budget usage. Missing, mismatched, or unreadable evidence blocks the transition.

The join retains each task's terminal specialist return, including conditional, partial, blocked, and failed results.
Only the latest ready return for a task satisfies a dependent agenda task; a terminal but non-ready return remains
reviewable and cannot silently unlock downstream work. A conclusion requires every current agenda task, rather than
merely every specialist role, to be ready. A later partial revision revokes eligibility from an earlier ready attempt.
The coordinator records a fail-closed decision when its canonical reread cannot verify exact evidence; the specialist
outcomes remain visible for review.

## Loop control

Code fingerprints semantically equivalent transitions while ignoring paraphrase and disposable identifiers. A repeated
decision with no material evidence gain terminates as a low-information loop. Revision, tool, model, token, duration,
and mutation budgets impose independent ceilings. The coordinator cannot narrate its way around them.
