"""Shared run-status aggregation logic for Project Mode and Database Mode.

Both `ProjectWorkflow.run()` (Project Mode) and `DatabaseWorkflow.run_tile()`
(Database Mode) verify the same three stage types (connectivity, simulation,
synthesis) and need to collapse their individual statuses into one overall
run status. This used to be two separate implementations that had already
diverged: Project Mode treated an all-SKIPPED run (e.g. `project run
--skip-check --skip-sim --skip-synth`) as "PASS" -- a vacuous truth, since
nothing that ran actually failed because nothing ran at all -- while
Database Mode already correctly downgraded any SKIPPED stage to "PARTIAL"
(dev-docs/TRACEABILITY_AUDIT.md, Findings #4/#4b). One shared function, used
by both modes, closes that gap for good and keeps the two from silently
re-diverging in the future.
"""

from __future__ import annotations

from collections.abc import Iterable

_FAIL = "FAIL"
_INCOMPLETE = frozenset({"SKIPPED", "NOT_RUN"})


def derive_run_status(stage_statuses: Iterable[str]) -> str:
    """Aggregate individual stage statuses into one overall run status.

    *stage_statuses* is the raw `StageResult.status` of every stage that
    was part of the flow (e.g. "PASS", "FAIL", "SKIPPED", "NOT_RUN", or
    "COMPLETED" for a simulation backend with no pass/fail concept of its
    own).

    - Any stage "FAIL" -> "FAIL".
    - No FAIL, but at least one stage "SKIPPED"/"NOT_RUN" (or no stages at
      all) -> "PARTIAL": not every stage that was part of this flow
      actually ran, so the result can't be called a full PASS -- whether
      the gap is an explicit `--skip-*` flag, a stage type that was never
      configured to begin with, a stage that never got a turn because an
      earlier one FAILed ("NOT_RUN", see
      dev-docs/TRACEABILITY_AUDIT.md Finding #5b), or nothing having run
      at all.
    - No FAIL, nothing incomplete (every stage reported PASS/COMPLETED) ->
      "PASS".
    """
    statuses = list(stage_statuses)
    if any(s == _FAIL for s in statuses):
        return _FAIL
    if not statuses or any(s in _INCOMPLETE for s in statuses):
        return "PARTIAL"
    return "PASS"


__all__ = ["derive_run_status"]
