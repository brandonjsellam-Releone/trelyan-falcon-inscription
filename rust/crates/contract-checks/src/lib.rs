//! `contract-checks` — static checks over the committed TEAL artifacts in `contracts/out/`.
//!
//! Some contract invariants cannot be exercised on `LocalNet` at a sensible cost. The 1,024-cell
//! hard cap (spec §2) is the first one: reaching it needs 1,024 real ASAs. Instead of leaving it to
//! review, this crate checks the committed approval program itself, so a recompile that drops or
//! weakens the guard fails CI. CI already proves that the committed TEAL is what the source
//! compiles to (`contracts/verify_teal_matches_source.py`), so a check on the artifact is a check
//! on the program that gets deployed.
//!
//! The checks fail closed: a missing method, a missing constant block, or any change to the guard
//! is an error, never a skip.

#![forbid(unsafe_code)]

use std::fmt;

/// The global-state key of the registration counter, as the TEAL `bytecblock` spells it.
const COUNTER_KEY: &str = "\"cells_registered\"";

/// Why a static check failed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CheckError(String);

impl CheckError {
    fn new(message: impl Into<String>) -> Self {
        Self(message.into())
    }
}

impl fmt::Display for CheckError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for CheckError {}

/// Where the cap guard sits in the approval program (1-based TEAL line numbers).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CapGuard {
    /// The line of the `<` comparison against the cap.
    pub compare_line: usize,
    /// The line of the `app_global_put` that stores the incremented counter.
    pub counter_write_line: usize,
}

/// Reads the value of `TOTAL_CELLS = <n>` from the contract source (`contracts/inscription.py`).
///
/// # Errors
///
/// If the constant is missing, defined more than once, or not a plain integer.
pub fn total_cells_from_source(source: &str) -> Result<u64, CheckError> {
    let mut values = source.lines().filter_map(|line| {
        let rest = line.trim().strip_prefix("TOTAL_CELLS")?;
        let value = rest.trim_start().strip_prefix('=')?;
        Some(
            value
                .split('#')
                .next()
                .unwrap_or_default()
                .trim()
                .to_owned(),
        )
    });
    let value = values
        .next()
        .ok_or_else(|| CheckError::new("TOTAL_CELLS is not defined in the contract source"))?;
    if values.next().is_some() {
        return Err(CheckError::new(
            "TOTAL_CELLS is defined more than once in the contract source",
        ));
    }
    value
        .parse()
        .map_err(|_| CheckError::new(format!("TOTAL_CELLS = {value} is not a plain integer")))
}

/// Checks that `register_cell` enforces `cells_registered < total_cells` before it stores the
/// incremented counter.
///
/// The guard must be the sequence the compiler emits for
/// `assert self.cells_registered < TOTAL_CELLS`: read the `cells_registered` global of this app
/// (`app_global_get_ex`, then `assert` that it exists), optionally `dup`, push `total_cells`, `<`,
/// `assert`. Constant operands (`intc_N`, `bytec_N`, `pushint`, `pushbytes`) are resolved through
/// the program's `intcblock` / `bytecblock`, so the check follows the values, not the register
/// allocation.
///
/// # Errors
///
/// If the constant blocks or the `register_cell` method are missing, if the guard is absent or
/// weakened (a different key, bound, comparison, or no `assert`), or if the method writes the
/// counter before the guard or never writes it.
pub fn check_register_cell_cap(
    approval_teal: &str,
    total_cells: u64,
) -> Result<CapGuard, CheckError> {
    let constants = Constants::parse(approval_teal)?;
    let method = method_body(approval_teal, "register_cell")?;
    let insns = method
        .iter()
        .map(|&(line, code)| constants.resolve(code).map(|insn| (line, insn)))
        .collect::<Result<Vec<_>, _>>()?;

    let compare_line = find_guard(&insns, total_cells).ok_or_else(|| {
        CheckError::new(format!(
            "register_cell does not enforce `cells_registered < {total_cells}`: expected \
             `app_global_get_ex` of {COUNTER_KEY}, `assert`, `pushint {total_cells}`, `<`, `assert`"
        ))
    })?;

    let writes: Vec<usize> = insns
        .windows(3)
        .filter(|w| w[0].1 == Insn::Bytes(COUNTER_KEY) && w[2].1 == Insn::Op("app_global_put"))
        .map(|w| w[2].0)
        .collect();
    if let Some(&early) = writes.iter().find(|&&line| line < compare_line) {
        return Err(CheckError::new(format!(
            "register_cell writes cells_registered at line {early}, before the cap guard at line \
             {compare_line}"
        )));
    }
    let counter_write_line = writes
        .first()
        .copied()
        .ok_or_else(|| CheckError::new("register_cell never stores cells_registered"))?;

    Ok(CapGuard {
        compare_line,
        counter_write_line,
    })
}

/// A TEAL instruction with its constant operand resolved.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Insn<'a> {
    Int(u64),
    Bytes(&'a str),
    Op(&'a str),
}

/// The program's `intcblock` and `bytecblock`.
struct Constants<'a> {
    ints: Vec<u64>,
    bytes: Vec<&'a str>,
}

impl<'a> Constants<'a> {
    fn parse(teal: &'a str) -> Result<Self, CheckError> {
        let block = |name: &str| {
            teal.lines()
                .map(code_part)
                .find_map(|code| code.strip_prefix(name))
                .map(tokens)
                .ok_or_else(|| CheckError::new(format!("the approval program has no {name}")))
        };
        let ints = block("intcblock ")?
            .into_iter()
            .map(|t| {
                t.parse()
                    .map_err(|_| CheckError::new(format!("bad intcblock value `{t}`")))
            })
            .collect::<Result<_, _>>()?;
        let bytes = block("bytecblock ")?;
        Ok(Self { ints, bytes })
    }

    fn resolve(&self, code: &'a str) -> Result<Insn<'a>, CheckError> {
        let (op, operand) = code
            .split_once(char::is_whitespace)
            .map_or((code, ""), |(op, rest)| (op, rest.trim()));
        let index = |prefix: &str| -> Option<Result<usize, CheckError>> {
            let suffix = op.strip_prefix(prefix)?;
            let raw = if suffix.is_empty() {
                operand
            } else {
                suffix.strip_prefix('_')?
            };
            Some(
                raw.parse()
                    .map_err(|_| CheckError::new(format!("bad constant index in `{code}`"))),
            )
        };
        let missing = || CheckError::new(format!("`{code}` refers to a missing constant"));
        if let Some(i) = index("intc") {
            return self
                .ints
                .get(i?)
                .copied()
                .map(Insn::Int)
                .ok_or_else(missing);
        }
        if let Some(i) = index("bytec") {
            return self
                .bytes
                .get(i?)
                .copied()
                .map(Insn::Bytes)
                .ok_or_else(missing);
        }
        match op {
            "pushint" => operand
                .parse()
                .map(Insn::Int)
                .map_err(|_| CheckError::new(format!("bad pushint operand in `{code}`"))),
            "pushbytes" => Ok(Insn::Bytes(operand)),
            _ => Ok(Insn::Op(code)),
        }
    }
}

/// The code lines of a method, from its label to the next routing header, with 1-based line
/// numbers. Labels inside the method are kept, so a jump target splits any instruction sequence.
fn method_body<'a>(teal: &'a str, method: &str) -> Result<Vec<(usize, &'a str)>, CheckError> {
    let label = format!("{method}:");
    let mut lines = teal.lines().enumerate();
    lines
        .by_ref()
        .find(|(_, line)| line.trim() == label)
        .ok_or_else(|| CheckError::new(format!("the approval program has no `{label}` method")))?;
    Ok(lines
        .take_while(|(_, line)| !(line.starts_with("// ") && line.contains("[routing]")))
        .map(|(i, line)| (i + 1, code_part(line)))
        .filter(|(_, code)| !code.is_empty())
        .collect())
}

/// Finds the cap guard and returns the line of its `<`.
fn find_guard(insns: &[(usize, Insn<'_>)], total_cells: u64) -> Option<usize> {
    let load = [
        Insn::Int(0),
        Insn::Bytes(COUNTER_KEY),
        Insn::Op("app_global_get_ex"),
        Insn::Op("assert"),
    ];
    let compare = [Insn::Int(total_cells), Insn::Op("<"), Insn::Op("assert")];
    (0..insns.len()).find_map(|start| {
        let rest = insns.get(start..)?;
        let starts_with = |at: &[(usize, Insn<'_>)], pattern: &[Insn<'_>]| {
            at.len() >= pattern.len() && at.iter().zip(pattern).all(|((_, a), b)| a == b)
        };
        if !starts_with(rest, &load) {
            return None;
        }
        let mut after = rest.get(load.len()..)?;
        if after.first().map(|&(_, insn)| insn) == Some(Insn::Op("dup")) {
            after = after.get(1..)?;
        }
        starts_with(after, &compare).then(|| after[1].0)
    })
}

/// A TEAL line without its trailing `//` comment, trimmed. A `//` inside a quoted string is kept.
fn code_part(line: &str) -> &str {
    let bytes = line.as_bytes();
    let mut in_string = false;
    let mut i = 0;
    while i < bytes.len() {
        match bytes[i] {
            // Skip the escaped character inside a string.
            b'\\' if in_string => i += 1,
            b'"' => in_string = !in_string,
            b'/' if !in_string && bytes.get(i + 1) == Some(&b'/') => return line[..i].trim(),
            _ => {}
        }
        i += 1;
    }
    line.trim()
}

/// Splits a constant block's operands, keeping quoted strings (which may contain spaces) whole.
fn tokens(operands: &str) -> Vec<&str> {
    let mut out = Vec::new();
    let mut rest = operands.trim_start();
    while !rest.is_empty() {
        let end = if rest.starts_with('"') {
            let mut escaped = false;
            rest.char_indices()
                .skip(1)
                .find(|&(_, c)| {
                    let close = c == '"' && !escaped;
                    escaped = c == '\\' && !escaped;
                    close
                })
                .map_or(rest.len(), |(i, _)| i + 1)
        } else {
            rest.find(char::is_whitespace).unwrap_or(rest.len())
        };
        out.push(&rest[..end]);
        rest = rest[end..].trim_start();
    }
    out
}
