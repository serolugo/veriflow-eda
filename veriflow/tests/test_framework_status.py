"""Tests for veriflow.framework.status.derive_run_status() -- the shared
run-status aggregation logic Project Mode and Database Mode both use.

See dev-docs/TRACEABILITY_AUDIT.md, Findings #4/#4b: before this shared
module existed, Project Mode's own copy of this logic treated an
all-SKIPPED run as "PASS" (a vacuous truth), while Database Mode's copy
already correctly downgraded any SKIPPED stage to "PARTIAL". One function
now backs both, so they can't silently re-diverge.
"""

from __future__ import annotations

import pytest

from veriflow.framework.status import derive_run_status


@pytest.mark.parametrize("statuses", [
    ["PASS", "PASS", "PASS"],
    ["PASS", "COMPLETED", "PASS"],
    ["PASS"],
    ["COMPLETED"],
])
def test_all_ran_and_passed_is_pass(statuses):
    assert derive_run_status(statuses) == "PASS"


@pytest.mark.parametrize("statuses", [
    ["FAIL", "PASS", "PASS"],
    ["PASS", "FAIL", "PASS"],
    ["PASS", "PASS", "FAIL"],
    ["FAIL", "SKIPPED", "SKIPPED"],
    ["FAIL"],
])
def test_any_fail_is_fail_regardless_of_others(statuses):
    assert derive_run_status(statuses) == "FAIL"


@pytest.mark.parametrize("statuses", [
    ["SKIPPED", "PASS", "PASS"],
    ["PASS", "SKIPPED", "PASS"],
    ["PASS", "PASS", "SKIPPED"],
    ["SKIPPED", "SKIPPED", "PASS"],
    ["SKIPPED"],
])
def test_no_fail_but_some_skipped_is_partial(statuses):
    assert derive_run_status(statuses) == "PARTIAL"


def test_all_skipped_is_partial_not_pass():
    """The exact vacuous-truth case from the original bug: every configured
    stage skipped, none failed because none ran -- must not be PASS."""
    assert derive_run_status(["SKIPPED", "SKIPPED", "SKIPPED"]) == "PARTIAL"


def test_zero_stages_is_partial_not_pass():
    """An empty pipeline (nothing ran at all) is the purest form of the
    vacuous-truth bug -- no stage to iterate, so a naive "no FAIL found"
    check would default to PASS. Must not."""
    assert derive_run_status([]) == "PARTIAL"


def test_matches_database_mode_three_stage_semantics_for_reachable_combinations():
    """Confirm the shared function reproduces what Database Mode's original
    3-argument _derive_status(conn, sim, synth) computed, for every
    combination of per-stage values each one can actually report in
    practice (conn/synth: "PASS"/"FAIL"/"SKIPPED"; simulation has no
    pass/fail concept of its own and reports "COMPLETED"/"FAILED" instead
    of "PASS"/"FAIL" -- see core/stages/simulation.py and
    core/backends/xsim.py, both of which use "FAILED", never "FAIL", for a
    genuine simulation failure) *except* the classes of input the original
    literal code got wrong -- see the two dedicated "masking" tests below,
    which document the intentional behavior changes."""
    conn_values = ("PASS", "FAIL", "SKIPPED")
    sim_values = ("COMPLETED", "FAILED", "SKIPPED")
    synth_values = ("PASS", "FAIL", "SKIPPED")

    def original_db_derive_status(conn, sim, synth):
        if conn == "FAIL":
            return "FAIL"
        if any(s == "SKIPPED" for s in (conn, sim, synth)):
            return "PARTIAL"
        if conn == "PASS" and sim in ("COMPLETED", "SKIPPED") and synth in ("PASS", "SKIPPED"):
            return "PASS"
        return "FAIL"

    for conn in conn_values:
        for sim in sim_values:
            for synth in synth_values:
                expected = original_db_derive_status(conn, sim, synth)
                actual = derive_run_status([conn, sim, synth])
                has_a_failure = "FAIL" in (conn, sim, synth) or "FAILED" in (conn, sim, synth)
                if expected == "PARTIAL" and has_a_failure:
                    # Known, intentional divergences -- see the two
                    # dedicated tests below (one per failure spelling).
                    continue
                assert actual == expected, (conn, sim, synth, expected, actual)


def test_fail_forces_fail_even_when_another_stage_is_also_skipped():
    """A real bug in Database Mode's original literal implementation,
    fixed by the shared function: `_derive_status` only special-cased a
    FAIL on the *connectivity* argument specifically (`if conn == "FAIL":
    return "FAIL"`) -- if simulation FAILed while synthesis was also
    SKIPPED (e.g. `db run --only-sim` with a failing testbench: conn and
    synth both SKIPPED, sim FAIL), the "any SKIPPED -> PARTIAL" check fired
    first and silently masked the real failure as PARTIAL. The task spec
    for this fix is explicit and unconditional ("any stage FAIL -> FAIL",
    no exception for a co-occurring SKIPPED), so the shared function
    reports FAIL here -- a real failure is never hidden behind an
    unrelated stage's SKIPPED status."""
    assert derive_run_status(["SKIPPED", "FAIL", "SKIPPED"]) == "FAIL"
    assert derive_run_status(["PASS", "FAIL", "SKIPPED"]) == "FAIL"
    assert derive_run_status(["SKIPPED", "SKIPPED", "FAIL"]) == "FAIL"


def test_failed_simulation_is_recognized_as_a_failure():
    """Regression test for a real bug found via genuine end-to-end testing
    of a packaged wheel install in a clean venv (2026-07-20, PyPI
    packaging audit) -- not a synthetic unit test case. Simulation
    backends (icarus, xsim) report "FAILED" for a genuine failure, never
    "FAIL" -- `derive_run_status` used to check for the single literal
    string "FAIL" only, so a real run (connectivity PASS, a testbench
    that genuinely failed to compile, synthesis PASS) came back with
    overall status "PASS" despite the simulation stage itself correctly
    showing "FAILED" -- exactly the kind of status falsification
    dev-docs/TRACEABILITY_AUDIT.md Findings #4/#4b were meant to close for
    good, reintroduced by a one-string-vs-another oversight in that same
    fix. "FAILED" must be recognized as a failure exactly like "FAIL",
    including when another stage is also SKIPPED (the same masking
    pattern as the test above, this time via the simulation spelling)."""
    assert derive_run_status(["PASS", "FAILED", "PASS"]) == "FAIL"
    assert derive_run_status(["PASS", "FAILED", "SKIPPED"]) == "FAIL"
    assert derive_run_status(["SKIPPED", "FAILED", "SKIPPED"]) == "FAIL"
