//! The 1,024-cell hard cap (spec §2), checked statically against the committed approval program.
//!
//! A `LocalNet` test would need 1,024 real ASAs, so this reads
//! `contracts/out/TrelyanInscription.approval.teal` and requires the compiled form of
//! `assert self.cells_registered < TOTAL_CELLS` on the `register_cell` path, before the counter is
//! stored. The bound comes from `TOTAL_CELLS` in `contracts/inscription.py`.
//!
//! Fail closed: a missing file panics with the path, and the mutation tests below show that each
//! way of dropping or weakening the guard is an error rather than a pass.

#![allow(clippy::expect_used, clippy::unwrap_used, clippy::panic)]

use std::path::PathBuf;

use contract_checks::{check_register_cell_cap, total_cells_from_source};

const APPROVAL_TEAL: &str = "contracts/out/TrelyanInscription.approval.teal";
const CONTRACT_SOURCE: &str = "contracts/inscription.py";

/// Reads a file relative to the repository root. Missing files fail the test; they never skip it.
fn read_repo_file(relative: &str) -> String {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .join(relative);
    std::fs::read_to_string(&path).unwrap_or_else(|err| {
        panic!(
            "cannot read {}: {err}. This check fails closed; the file must exist.",
            path.display()
        )
    })
}

fn committed_teal() -> String {
    read_repo_file(APPROVAL_TEAL)
}

fn total_cells() -> u64 {
    total_cells_from_source(&read_repo_file(CONTRACT_SOURCE)).expect("TOTAL_CELLS in source")
}

/// Applies one textual change to the committed TEAL, insisting it actually happened.
fn mutate(from: &str, to: &str) -> String {
    let teal = committed_teal();
    assert_eq!(
        teal.matches(from).count(),
        1,
        "mutation target `{from}` must occur exactly once in the committed TEAL"
    );
    teal.replacen(from, to, 1)
}

#[test]
fn source_fixes_the_cap_at_1024() {
    assert_eq!(
        total_cells(),
        1024,
        "spec §2 sets the hard cap at 1,024 cells"
    );
}

#[test]
fn committed_approval_program_enforces_the_cap_before_counting() {
    let guard = check_register_cell_cap(&committed_teal(), total_cells())
        .unwrap_or_else(|err| panic!("{APPROVAL_TEAL}: {err}"));
    assert!(guard.compare_line < guard.counter_write_line);
}

#[test]
fn removing_the_assert_fails() {
    let teal = mutate(
        "    <\n    assert // all 1024 cells registered",
        "    <\n    pop",
    );
    assert!(check_register_cell_cap(&teal, total_cells()).is_err());
}

#[test]
fn weakening_the_comparison_fails() {
    let teal = mutate(
        "    <\n    assert // all 1024 cells registered",
        "    <=\n    assert // all 1024 cells registered",
    );
    assert!(check_register_cell_cap(&teal, total_cells()).is_err());
}

#[test]
fn raising_the_bound_fails() {
    let teal = mutate("    pushint 1024\n    <", "    pushint 1025\n    <");
    assert!(check_register_cell_cap(&teal, total_cells()).is_err());
}

#[test]
fn guarding_a_different_key_fails() {
    let teal = mutate(
        "bytecblock \"admin\" \"cells_registered\"",
        "bytecblock \"admin\" \"cells_minted\"",
    );
    assert!(check_register_cell_cap(&teal, total_cells()).is_err());
}

#[test]
fn a_missing_register_cell_method_fails() {
    let teal = mutate("\nregister_cell:\n", "\nregister_cell_renamed:\n");
    assert!(check_register_cell_cap(&teal, total_cells()).is_err());
}

#[test]
fn a_missing_constant_block_fails() {
    let teal = mutate("    intcblock 0 1 8 32\n", "");
    assert!(check_register_cell_cap(&teal, total_cells()).is_err());
}

#[test]
fn a_missing_counter_write_fails() {
    let teal = mutate(
        "    bytec_1 // \"cells_registered\"\n    swap\n    app_global_put",
        "    pop\n    pop",
    );
    assert!(check_register_cell_cap(&teal, total_cells()).is_err());
}

#[test]
#[should_panic(expected = "fails closed")]
fn a_missing_artifact_fails() {
    read_repo_file("contracts/out/DoesNotExist.approval.teal");
}

#[test]
fn source_without_the_constant_fails() {
    assert!(total_cells_from_source("CELLS = 1024\n").is_err());
    assert!(total_cells_from_source("TOTAL_CELLS = 1024\nTOTAL_CELLS = 2048\n").is_err());
    assert!(total_cells_from_source("TOTAL_CELLS = lots\n").is_err());
    assert_eq!(
        total_cells_from_source("TOTAL_CELLS = 1024  # spec §2\n"),
        Ok(1024)
    );
}
