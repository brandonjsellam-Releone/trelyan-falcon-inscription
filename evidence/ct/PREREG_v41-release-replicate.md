# Pre-registration — v4.1 validation REPLICATE on the intended (release) harness

**Written 2026-08-20, before the measurement it governs, while the release binary cannot yet
be built** (Windows App Control hash-blocks freshly built release executables on the primary
machine; the founder decides the unblock). This document exists so the run can launch the
moment that decision lands, with nothing chosen after seeing data. It implements fix F1 of the
six-seat review of `session-2026-08-20-local-v41-validation` (transcript committed in that
session's directory): the debug-profile session was not the pre-registered experiment, and its
reading calibrates only the debug image.

## 1. The run

- **Binary:** `falcon-ct`, **release profile**, built from a stated commit (recorded in the
  session dir at launch), on the primary laptop. The executable's **SHA-256 is recorded in the
  session directory BEFORE launch.** The vendored C core is pinned `opt_level(3)` in both
  profiles; this replicate exists because the surrounding process image — heap regime, image
  size, I-cache placement, allocator, ASLR — is profile-dependent and is part of what the crop
  machinery measures.
- **Command:** `--null-design ss --samples 4800 --null-sessions 20 --aa-repeats 20`
  (rr-sessions defaulting to 20) — identical to the debug session.
- **Environment:** same laptop as every prior local session; nothing else running (no builds,
  no council processes, no timing-relevant load); on AC power. CPU pinning/turbo state is not
  controlled on this machine and is recorded as such.
- **Session directory:** `evidence/ct/session-<date>-local-v41-release-replicate/`, with
  `report.json`, all raw CSVs (both banks), `console.log`, the exe hash, and `SHA256SUMS`.

## 2. The one reading (unchanged bands, registered limitations)

**`controls.null_raw_t_sd`** over the 20 null-ss sessions, against the bands committed in
`METHODOLOGY-v4.md` §2 before any ss session existed:

- **≤ 1.25 → proceed** to the next step of the ruled path (controls pre-registration, then a
  fully specified §6.1);
- 1.25–1.60 → partial;
- > 1.60 → stop;
- undefined (fewer than 2 usable sessions) → no reading.

Registered limitation, stated now per review finding F4: this is a **point-estimate branch
call**. At n = 20 the 95% CI on the true SD spans roughly ±35–45% of the estimate, so a
"proceed" here is a low-information proceed and is never described as demonstrating
proceed-quality tail behaviour. Zero |t| ≥ 4.5 crossings in 20 sessions bounds the per-session
crossing probability only at ≈ 14% (one-sided 95%).

## 3. What is explicitly NOT read or used

- **No v3.1 re-judgment from this session.** Review finding F2 stands: judging v3.1's 82k-
  sample crops requires a bank **matched to v3.1 in count and harness** (20 × 82k sessions —
  a separately priced decision), not this session's 4800-sample banks.
- **The aa and rr banks this session produces are frozen but unused** until (a) the controls
  pre-registration and (b) the fully specified §6.1 clone-fidelity experiment exist and rule
  on them. No SHAPE judgment of any kind is minted from this session.
- Every experiment remains ungated and INCONCLUSIVE (`validation_only: true`) — unchanged.
- The in-session kk crop values, whatever they are, do not tune any margin or threshold.

## 4. Deviation rule (this morning's lesson, written down)

If ANY element of §1 cannot be met as stated — different binary, profile, commit, machine, or
concurrent load — **the run may still be executed but is EXPLORATORY: the §2 bands are not
applied, no reading is minted, and this document does not govern it.** A blocked release build
is a reason to stop and wait, never a reason to substitute the process and keep the bands.

## 5. The two founder branches

- **Branch A — App Control unblocked:** run as §1. This document governs.
- **Branch B — the founder directs debug-as-official-harness instead:** this document is VOID.
  That path requires a dated prospective amendment to METHODOLOGY-v4 naming the debug profile
  as the intended harness, followed by a NEW pre-registration and new banks. Nothing from the
  2026-08-20 debug session is retroactively accepted under either branch.
