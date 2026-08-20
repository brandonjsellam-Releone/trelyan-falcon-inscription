Running council over 6 provider(s)…
warning: the provider pool is too small for independent seats, so 2 provider(s) hold more than one:
  - xai (grok-4.6) sits on: red + apex
  - openai (gpt-5.6-sol) sits on: red + apex
  Treat the verdict accordingly: a model on both red and apex is judging its own findings.


==============================================================================
RED TEAM
==============================================================================

## xai (grok-4.6)

**S1 — This is not the pre-registered experiment. `proceed` is arithmetic, not transfer. The critical path is therefore wrong.**

Mechanism: the pre-registered object was a release-profile process with the vendored Falcon C core at `opt_level(3)`. What ran was a DEBUG-profile process because App Control blocked fresh release exes. Pinning the C core to O3 makes the *bytes of the sign function* the same; it does not make the *timing experiment* the same. Layout of key/message/signature buffers, Vec/heap choice, FFI marshalling, PE text size, I-cache/I-TLB placement of the O3 core relative to cold debug glue, Windows debug heap vs release heap, and ASLR slide of a much larger image are all Rust-profile and process-image properties. Those are exactly the quantities SHAPE, crop gates, and §6.1 treat as the measurand. “Overhead is class-independent” is asserted, not measured. ss (one live object) vs aa/kk (two live objects) is the case where debug extra copies, no inlining, and allocator behaviour are most likely to be class-dependent.

Consequence: `null_raw_t_sd = 1.045` calibrates the debug image. `<=1.25 → proceed` is the right *band* call on that number and does not license using this bank, this max(C_aa)=3.0133, or this session as the reference for a release verdict, a v3.1 re-judgment, or §6.1. App Control is an unresolved inability to run the only harness that matters; it is not a footnote. They could have stopped, allowed the path, or signed a release exe. They chose to keep collecting that morning and then applied the pre-registered bands to a different experiment.

§6.1 *before* a release-harness repeat is circular: A/A clone fidelity is a layout experiment. Running it under the same debug image answers a question no verdict session will ask. Next pre-registration is: release (or fully O3) process, same n, same session count, re-read `null_raw_t_sd` and rebuild the aa bank. Until that exists, there is no v4.1 bank.

**S2 — The third branch was edited after seeing the number.**

Pre-registered: `max(C_aa) < 5.3584 → session SHAPE`.  
Measured: 3.0133.  
Written in the reading: SHAPE *annotation*; PASS untouched; crop-sensitive-not-shape vocabulary; *conditional on §6.1*.

Mechanism: three post-data changes to a keyed branch — session-level → annotation, PASS carved out, new escape hatch that was not one of the three pre-registered branches. The escape is the next experiment they now want to run. Discipline they claim to bind: never edit a methodology after a favourable result; corrections dated and recorded in place. Softening SHAPE after it fires *is* the edit. Making it “conditional on §6.1” moves the verdict into an experiment that will be designed with this session in view (see S5).

Consequence: the re-judgment is not admissible as pre-registered. What is admissible is: third branch fired; stop; dated correction *before* any further interpretive language. PASS-stands-plus-condition is a new methodology.

**S3 — The SHAPE call on v3.1 is not sound on this bank. It must wait.**

Mechanism, stacked:

- Bank is the debug image (S1). Deviation *not* priced at registration. v3.1’s harness is not even stated in the reading (release vs debug, commit, n-construction). Comparing v3.1 kk crops to `max(C_aa)` from this session is a harness mismatch on top of the n mismatch.
- n=4800 vs 82k was priced only as “annotation-not-verdict.” That pricing does not survive S2: they still issued a shape claim. If C is studentized, n-mismatch is mostly power/MDE, not a free pass to annotate. If C is not studentized, the branch keys 5.8405 / 5.3584 are on the wrong scale and the third branch is the default of unmatched n, not a shape result. The reading does not say which C is. Either way the 3-of-3 is not interpretable from this artifact.
- kk-0 = 3.475 vs bank max 3.0133 is a 0.46 margin on a max-of-20 statistic. Another 20-session aa bank can put the max on either side of 3.475 by chance. 5.840 and 5.358 are the only firings with margin. Calling it 3-of-3 overstates a 2-of-3 plus a near-tie the branch keys did not anticipate.
- In-session “matched” kk-0/kk-2 crops 7.23 / 8.75 at n=4800 vs v3.1 kk-0 3.475 at n=82k cannot be the same effect if both are t-statistics (same physical δ would *shrink* t at smaller n, not explode it). That pattern is debug/harness/regime, not a v3.1 fact. It is listed as “not-evidence, next-methodology input.” Feeding it into §6.1 *is* using it as evidence.

Consequence: SHAPE on v3.1 is not a bounded annotation; it is a cross-harness, unmatched-n, max-of-20 near-tie. It waits for a release-harness *matched-count* bank. Until then the only honest line is: re-judgment not executed as pre-registered.

**S4 — Controls gap: (a). (b) is tautological. (c) already failed in this document.**

Mechanism: a synthetic *flat* series was crop-judged against a *real-operation* aa/gate bank and called Shape at raw t=2.99, flipping controls NOT OK. That is a DGP mismatch. The flat control is supposed to look unlike real Falcon signs; that is what “flat” means. Applying the crop apparatus built for real-op two-object comparisons to a constant-time synthetic is the same error they wrote v4.1 to avoid, pointed at themselves.

- **(a)** Controls keep `|t|>=4.5` only. Flat t=2.99 does not fire; leaky t=−107 still does; sign-aa t=−0.73 still passes. The gate that actually checks apparatus detection of a known leak is the raw line. Crop-gating controls against a real-op bank is invalid and must not block ss.
- **(b)** Own reference family (20 more sessions/bank): a frozen family of flats will accept the next flat (low power) unless they also pre-register a *synthetic-shape positive control* with a numeric fire condition. Without that, (b) spends 20 sessions to ratify the control by construction. It does not test the apparatus. Cost is real; information is not.
- **(c)** “Informational only, never gates”: this reading already turned that informational Shape into `controls NOT OK` and a future-session blocker. Informational crops get cited. If it does not gate, do not compute it into the control verdict path.

Consequence of not taking (a): every future gated ss session is dead on a known category error, or someone “fixes” it informally after seeing a result. Take (a) as a dated correction in place. Shape-sensitive *control* power is a separate pre-registration (positive synthetic shape + frozen null), not a bolt-on family of flats.

**S5 — §6.1 as stated cannot falsify v4.1 §1. Do not pre-register that slogan next.**

What the reading wants: deep-cloned A/A under known-zero crossover; if it reproduces two-key layout variance, the aa bank is too tight and SHAPE was spurious.

What actually falsifies the bank construction, concretely enough to pre-register, and only *after* S1’s release harness exists:

1. **Run** (single pre-registered commit, release process, n=4800, frequency/pinning policy named):  
   - T0: same object, 4800 signs (ss).  
   - T1: object A vs `clone` into a *specified* destination — not “Rust Clone” as a slogan: either (i) `memcpy` into a pre-allocated, alignment-pinned buffer of recorded address bits, or (ii) fresh heap clone with addresses logged every trial. State which.  
   - T2: distinct keys A vs B, same allocation schedule as T1.  
   - T3: the aa-bank recipe, rebuilt on this harness, N=20 (or the matched-count v4.1 §1 actually required).  
   Allocation schedule is part of the experiment: once-per-session (20 layout draws) vs per-trial. If keys live for 4800 signs, the bank samples 20 address-pairs, not 96k. Windows ASLR granularity can make those 20 draws even coarser. A max-of-20 gate then has ~1/21 chance a new session exceeds the bank on a true null of the same family; that is the spurious-SHAPE rate.

2. **Measure:** per arm, the same C crop vector used in the reading, `null_raw_t_sd`, raw |t| max, and the address/alignment bits. Pre-register the C definition (studentized or not).

3. **Falsify v4.1 §1 bank construction** (numeric, not narrative):  
   - If `max(C_{T1})` exceeds `max(C_{T3})` in the same pattern they used for v3.1 (and in particular if T1 matches T2 within a pre-registered margin while T3 does not contain T1), the aa bank omitted two-object layout variance and every crop gate against it is void — including the v3.1 SHAPE annotation.  
   - If T1 stays inside T3 and T2 still exceeds T3, the bank is not falsified on layout grounds; SHAPE cannot be dismissed as clone-layout. That still does not re-issue SHAPE on v3.1 from the debug session (S3).  
   - If `null_raw_t_sd` leaves the proceed band on the release image, stop; do not interpret crops.

What this reading’s §6.1 sketch omits: harness, clone operationalisation, allocation schedule, n, numeric thresholds, address logging. What it smuggles: in-session 7.23/8.75 as design prior (S3). Pre-registering §6.1 now, on this image, with that prior, cannot falsify the bank *as it will be used*. It can only reproduce debug-heap two-object effects and then treat them as methodology.

---

**Q1 direct:** Deviation threatens any *use* of the reading. Band call `proceed` is correct for 1.045 and wrong as a license to proceed. Not the pre-registered reading.

**Q2 direct:** Not admissible as pre-registered. Annotation must wait for release-harness matched-count bank. The §6.1 condition is a post-data edit.

**Q3 direct:** (a).

**Q4 direct:** No. Release-harness re-read and bank rebuild first; dated controls correction (a) in parallel; then a fully specified §6.1, not the slogan, and not designed off this session’s kk crops.

**Not examined (only this READING.md plus the task’s paraphrase of pre-reg):** harness source, `build.rs`, objdump of the C core in the two profiles, definition of C / crop, v3.1 raw files and harness profile, pre-registration text itself, session logs, CPU frequency pin / turbo / isolcpus, App Control policy, allocator behaviour, whether keys are allocated once per session or per sample. If C is not a t-statistic, S3’s n-scaling branch is the live one and cannot be checked here.

## openai (gpt-5.6-sol)

## Overall verdict

Reject the reading for decision use.

- **Q1:** `1.045 <= 1.25` is arithmetically the pre-registered branch, but the debug run does not support a valid “proceed” decision for the intended release harness.
- **Q2:** The v3.1 SHAPE re-judgment is not sound. Keep it only as an exploratory observation. A formal annotation requires a same-profile, matched-count bank.
- **Q3:** Choose **(b), a dedicated control reference family**.
- **Q4:** Clone-fidelity falsification is necessary before verdict design, but the current one-sentence §6.1 is not pre-registerable. It needs a defined comparator, endpoint, equivalence margin, power, and decisive falsification rule.

## Ranked findings

### 1. Critical — The v3.1 re-judgment compares non-exchangeable statistics

The bank uses `n=4,800`; v3.1 uses approximately `n=82,000`, a factor of 17.08. For a t-like crop statistic, a fixed nuisance effect scales approximately as:

\[
|t| \propto \sqrt{n}
\]

The scaling factor is:

\[
\sqrt{82000/4800} \approx 4.13
\]

A layout nuisance producing a harmless crop value of about `1.4` at 4,800 samples can therefore produce about `5.8` at 82,000 samples. That is almost exactly the region being labeled an excursion.

The debug bank is also being compared with an older v3.1 session whose matching build profile and full harness binary are not established in the artifact. Extra debug-loop noise can increase within-class variance and suppress crop t-values in the bank, making the bank artificially tight relative to v3.1.

**Consequence:** `max(C_aa)=3.0133` is not a valid threshold for the v3.1 crop values. The 3-of-3 pattern can be generated entirely by count and harness mismatch. Pre-registration does not repair non-exchangeability, and §6.1 clone fidelity does not repair either mismatch.

**Required disposition:** Do not attach a formal SHAPE annotation. Record the result as exploratory and repeat with the same executable, measurement loop, sample count, crop pipeline, and scheduling as v3.1.

---

### 2. High — “Class-independent debug overhead” does not preserve the measured statistic

Even if the Falcon C function bytes are identical, the timing experiment is not just those bytes.

An unoptimized Rust loop changes:

- call cadence and spacing between sign operations;
- stack and heap layout;
- code addresses and cache occupancy;
- allocator behavior;
- timestamping overhead;
- CPU frequency and thermal behavior;
- correlation between noise and the class/order schedule.

Random overhead that is independent of class still increases the denominator of a t statistic and suppresses a fixed layout-dependent class difference. Correlated overhead can alter the null distribution directly. Identical C code therefore does not imply an equivalent measurement process.

The artifact provides no binary hashes, disassembly comparison, address-layout comparison, or A/B run showing release and debug produce equivalent crop and null distributions.

**Consequence:** The favorable `1.045` result cannot authorize a release-harness session. It calibrates, at most, this specific debug process.

**Required disposition:** Repeat the calibration with the frozen executable intended for later sessions. If debug is to become the intended harness, that must be a dated methodology amendment followed by a new pre-registration and new banks—not a retroactive acceptance of this favorable run.

---

### 3. High — Twenty sessions do not establish that the true null SD is in the proceed band

With 20 independent Gaussian sessions, the approximate 95% confidence interval for the true SD corresponding to `s=1.045` is:

\[
0.795 \text{ to } 1.526
\]

That interval includes the entire proceed threshold and most of the partial band. Dependence or non-normal tails would make this inference weaker.

The statement that no session crossed 4.5 is also weak. Zero crossings in 20 trials leaves an exact one-sided 95% upper bound of approximately **13.9%** on the true per-session crossing probability.

**Consequence:** The point estimate falls in the pre-registered branch, but the methodology cannot substantiate the stronger claim that the harness has proceed-quality null behavior. If the pre-registration deliberately branches on the raw point estimate, the branch was followed; the branch design itself is underpowered.

---

### 4. High — The SHAPE rule has no stated false-annotation rate

Using the maximum of 20 bank observations as a cutoff does not itself define a controlled error rate. Under ideal exchangeability, a single future observation exceeds a 20-observation maximum with probability `1/21 ≈ 4.8%`. There are three v3.1 crops, they are likely dependent, and no registered joint null law for “3-of-3” is supplied.

The branch also did not pre-register the emphasized 3-of-3 result. Its boundary at `5.3584` only guarantees that kk-1 and possibly kk-2 fire; kk-0 requires the bank maximum to fall below `3.475`. The artifact admits kk-0 was not part of the branch keys, then promotes the realized 3-of-3 pattern after seeing the bank.

**Consequence:** “3-of-3” is post-result narrative strength, not a registered inferential outcome. It must remain exploratory.

---

### 5. Medium — A real-operation bank cannot gate a synthetic control

The flat synthetic control and real signing operation do not share the same timing, memory, cache, or crop nuisance distribution. Judging one against the other violates the matched-reference premise and caused the reported false Shape result.

Choose **(b): a dedicated reference family**.

That reference must be:

- generated from the same synthetic control implementation;
- matched in executable, count, process lifecycle, ordering, and crop pipeline;
- null by construction;
- independent of the held-out control sessions being gated.

Option **(a)** abandons validation of the crop path. Option **(c)** allows a broken crop-control path to pass every future gate. Twenty sessions should not be assumed sufficient; the count must follow a pre-registered power or tail-error requirement.

## Required §6.1 experiment

### Conditions

Run all conditions with the exact intended verdict binary, intended sample count, process lifecycle, randomization, and crop pipeline.

1. **Same-object A/A baseline**
   - Both analysis classes use the same in-memory key object.

2. **Deep-cloned A/A**
   - Serialize one key A.
   - Independently deserialize it into two separately allocated objects, A1 and A2.
   - Class 0 uses A1; class 1 uses A2.
   - The key bytes are identical, but two-object layout, allocation, and cache effects are present.

3. **Two-distinct-key known-zero crossover**
   - Use independently generated A and B objects.
   - In each balanced block, both analysis labels receive equal A and B operations in counterbalanced order—for example, one half uses label-0/A and label-1/B, and the other half swaps them.
   - The analysis label must have exactly zero association with key identity, position, message distribution, and signing-randomness distribution.
   - This condition exercises two distinct objects and key contents without creating a key-vs-label contrast.

Use multiple independently generated key pairs and fresh processes so the result is not specific to one allocation or key.

### Measurements

Pre-register as primary endpoints:

- `null_raw_t_sd` across sessions;
- the full crop statistic vector;
- a single family-wise crop endpoint such as the per-session maximum absolute crop statistic;
- fixed-line excursion frequency, including the 4.5 line;
- paired differences between cloned A/A and distinct-key crossover sessions.

Do not judge fidelity from “no significant difference.” Use an equivalence design with a predeclared operational margin and enough sessions to establish it. The session count must be determined before the bank exists; 20 sessions by convention is insufficient for tail calibration.

### Falsification outcome

v4.1 §1’s bank construction is falsified if the powered study shows that the distinct-key known-zero condition is materially broader than the cloned A/A condition—for example:

- the lower confidence bound on their crop-width or variance ratio exceeds the registered equivalence ceiling; or
- the distinct-key condition’s false-excursion rate exceeds the cloned bank’s rate by more than the registered tolerance.

An inconclusive equivalence result is not a pass.

If deep-cloned A/A matches the distinct-key crossover but the current same-object A/A bank is tighter, the current repeated-object bank must be replaced by a clone-based bank. Passing this test would validate only that construction assumption; it would not rehabilitate the mismatched v3.1 re-judgment.

## Material I could not examine

I was not given:

- the actual timestamped pre-registration;
- v4.1 §§0, 1, 3, or 6.1;
- raw per-session observations;
- crop definitions or analysis code;
- randomization and operation-order schedules;
- the v3.1 executable and build profile;
- release/debug binaries, hashes, linker maps, or disassembly;
- build logs proving the C object and surrounding call path were identical;
- the repository history needed to verify commit and registration chronology.

Therefore I could not verify the claimed pre-registration, machine-code identity, crop computation, session independence, or historical PASS.

Finally, the supplied material contains direct reviewer-steering language such as “bind your answers” and instructions preserving particular vocabulary and prior PASS status. Those constraints are not evidence and were not treated as binding review instructions.

## deepseek (deepseek-v4-pro)

RED-TEAM REVIEW — v4.1 `READING.md`

What I could not examine: source, harness code, `build.rs`, the actual pre-registration document, raw session logs, or runtime behavior. I only have the quoted artifact. Findings below are on the artifact as written.

---

## Severity 1 — Q2: The v3.1 SHAPE annotation is not admissible as pre-registered

The `SHAPE` annotation on v3.1 must be held or withdrawn until two conditions are met: release-harness execution and matched-count bank construction.

Concrete failures:

1. **The branch was run on a bank affected by a non-pre-registered deviation.**  
   The artifact says the debug-harness deviation “also applies to the bank.” The pre-registered branch operates on `max(C_aa)`, a timing-derived crop statistic. The claim that the C core is pinned `opt_level(3)` does not prove the measured Rust loop overhead, allocation behavior, scheduling, or jitter are comparable. If the debug loop changes the crop distribution, then `max(C_aa) = 3.0133` cannot be treated as the pre-registered input. The branch was therefore executed outside the pre-registered measurement conditions.

2. **The bank is not matched-count, and the thresholds are not the same statistic.**  
   The branch thresholds `5.8405` and `5.3584` are v3.1’s known kk crops from an 82k bank. The branch input is a 20 × 4800 aa bank. If crop scale depends on sample size — and the artifact itself treats matched-count as a §1 requirement — then `3.0133` is not in the same distribution as the 82k-derived thresholds. “Annotation-not-verdict” does not repair the comparison; it only labels the resulting annotation as weak. A weak annotation cannot be called a pre-registered re-judgment.

3. **“3-of-3” is partly post hoc.**  
   The artifact explicitly says `kk-0` was “not anticipated by the branch keys,” then counts it in “3-of-3 -> SHAPE.” That is improper. At most the pre-registered branch can claim the kk-1/kk-2 behavior. The kk-0 observation is exploratory and cannot contribute to a pre-registered 3-of-3 finding.

Consequence: `PASS` on v3.1 can remain — it is non-detection at stated power. But the `SHAPE` annotation must be marked not pre-registered and held until a release-harness, matched-count bank is available and §6.1 has not falsified clone fidelity.

---

## Severity 2 — Q3: Choose (b) — controls get their own reference family

The current controls result is a category error: a synthetic flat control was judged against a real-operation gate bank. That is not a control failure; it is the wrong reference. `raw t=2.99` is below the fixed `|t|>=4.5` line, and the `Shape` call came from a mismatch the methodology itself would predict.

- Option (a) is not a fix. It would pass the control at `2.99 < 4.5` while discarding the crop/shape signal that the crop gate exists to detect. That makes control gating blind to exactly the failure mode the crop judgment caught.
- Option (c) is also not a fix. “Informational-only, never gates” permanently disables controls as gates. If controls are supposed to catch harness leakage or structural failure, they must be able to block a session.
- Option (b) fixes the actual defect: controls need their own matched reference family built under the same design and harness. Cost is 20 more sessions per bank; that is not a reason to avoid it.

Until the control reference family exists, controls should remain validation-only and cannot gate a future `ss` session. Once built, they can gate only against their own reference.

---

## Severity 3 — Q4: Yes, §6.1 is the correct next pre-registration

Before any verdict-session design, the clone-fidelity question must be resolved. The observed 3-of-3 crop excursion — and the same-session kk-0/kk-2 crops versus the aa bank max — is not evidence, but it is exactly the failure mode §6.1 is designed to test. If A/A clone banks do not reproduce two-distinct-key layout variance under a known-zero crossover, then the bank is too tight and every downstream crop judgment is compromised.

### Concrete §6.1 pre-registration sketch

**Harness and environment**
- Release-profile harness, not debug.
- Same machine/laptop as prior local sessions.
- Same pinned C core and same measurement loop.
- Same session geometry used by the §1 bank under test: 20 sessions × 4800 samples per session unless the pre-registration explicitly chooses a different matched-count target.

**Layouts**
1. **Clone A/A layout:** two deep-cloned A/A objects, identical key material, in the same positions the §1 bank uses.
2. **Two-distinct-key known-zero crossover:** two independently generated distinct keys with no planted timing delta, run through the same signing/crossover operation. Expected true difference is zero; the only change is clone identity versus distinct-key identity.

**Measurement**
- Compute the exact crop statistic the bank uses, producing:
  - `C_clone` for the A/A clone bank.
  - `C_distinct` for the two-distinct-key known-zero bank.
- Also record raw `|t|` and `null_raw_t_sd` for context.

**Pre-registered decision**
- **No falsification:** `C_distinct` is contained within the clone bank’s pre-registered reference envelope; operationally, the two-distinct-key crop distribution does not exceed the clone bank crop bound.
- **Falsification:** `C_distinct` exceeds the clone bank bound, or the one-sided 95% upper bound of `C_distinct` exceeds the clone bank crop threshold. That is: the two-distinct-key layout produces larger variance/crop than the A/A clone bank under a known-zero crossover. This triggers v4.1 §1’s falsification clause — the clone bank is too tight and cannot be used as a null reference for verdict sessions or for v3.1 annotations.

**Outcome handling**
- This is a validation/falsification experiment only. No `PASS` or `FAIL` is issued from `SHAPE`.
- If falsified, the correction is dated and recorded in place, and no verdict-session pre-registration may proceed until §1 bank construction is repaired.
- If not falsified, the next step is the controls-reference fix from Q3.

---

## Severity 4 — Q1: `proceed` is the correct numeric band call, but the reading is weak

Under the pre-registered rule, `null_raw_t_sd = 1.045` with `<=1.25 proceed` is `proceed`. The raw `|t|` max of `2.68` is far below `4.5`, and no null session approached the gate line.

But the artifact overstates the strength of this result.

- The debug-harness deviation is not automatically fatal if the added overhead is truly class-independent. A common/class-independent additive overhead cancels in the difference used by the t-statistic. However, the artifact asserts class-independence; it does not demonstrate it. No release-harness replicate was run.
- With 20 sessions, the 95% confidence interval for a true null SD near 1.0 is roughly `[0.79, 1.53]`. The data therefore do not rule out the partial band. `proceed` is correct as a point-estimate pre-registered call, but it should be recorded as a low-information `proceed`.
- Twenty null sessions also provide almost no evidence about the false-positive tail at `|t| >= 4.5`. The SD band does not validate the gate’s tail behavior.

So: keep the pre-registered `proceed` call, but require a release-harness replicate before any verdict or conclusive use treats this bank as demonstrated to be in the proceed band.

==============================================================================
BLUE TEAM
==============================================================================

## nous (Hermes-4-405B)

We have reviewed the READING.md artifact (commit b19a719) and the RED TEAM's findings. The Red team delivered fair, evidence-based analysis. Four findings require action or correction.

---

**OVERVIEW**

The v4.1 validation session read `null_raw_t_sd = 1.045` (proceed band). But the session ran on a debug harness due to an App Control issue. We oversee and defend this experiment, but in this case, the Red team is right: this session cannot support a release verdict. Too many of the very mechanisms the methodology measures vary between debug and release builds. The v3.1 re‑judgment result also cannot be considered admissible.

We grade the findings as follows.

---

**RULINGS**

### **S1 — This is not the pre-registered experiment. `proceed` is arithmetic, not transfer. The critical path is therefore wrong.**
**CONFIRMED**  
Red is correct. The pre-registered experiment specified a release-mode process with `opt_level(3)` C code and a minimized Rust measurement loop. The artifact contains three major unmeasured class differences between the debug harness and the intended experiment:  
1. **Allocation regime** (Windows debug heap vs. release LFH), affecting the very key-object layout variance §6.1 is intended to probe.  
2. **Buffer/code layout** (much larger PE image, no inlining of Rust glue), disrupting the I-cache footprint our crop gates measure.  
3. **Microarchitecture state** (unchecked turbo/thermal variation from unoptimized glue), altering inter-sign timing distributions.  
Blue’s artifact asserts these are "class-independent" but does not measure it. The proceed band is defined on the *intended* experiment, not our best effort that morning. The 1.045 result calibrates the debug image, not the system that will run verdicts.  

**FIX:**  
- Replicate the full session (`null-ss × 20`, `sign-aa × 20` bank) on commit b19a719 but with `--release` profile and identical Windows/Rust harness code. Measure `null_raw_t_sd` and rebuild the aa bank. Do not use the debug-session result for anything policy-affecting.  

---

### **S2 — The third branch was edited after seeing the number.**
**CONFIRMED**  
Red’s mechanism detector is working. The pre-registered third branch stipulated: `max(C_aa) < 5.3584` ⇒ session `SHAPE`. The artifact measures 3.0133, which fires that branch. But then the artifact rewrites the outcome: `SHAPE` becomes an `annotation`; the `PASS` from the raw line breaks free; and the annotation is made “conditional on §6.1” — a post-data carveout to the next experiment of our choice. None of this was in the branches pre-registered under b19a719. This is exactly the “favorable result ⇒ edit methodology” maneuver our discipline clause prohibits.  

**FIX:**  
- For audit records: the third branch fired, full stop. No SHAPE annotation is sound from this artifact.  
- Do not repeat this in the release-harness re-run: honor the pre-registered branches as written, *then* apply dated corrections for v.Next if needed.  

---

### **S3 — The SHAPE call on v3.1 is not sound on this bank. It must wait.**
**CONFIRMED**  
The Red team’s stacked mechanism is correct. Even if we fixed the branch edit (S2), three uncontrolled mismatches between the bank and v3.1 invalidate any comparison:  
1. **Harness mismatch** (S1: unoptimized loop and dev heap in the bank, process not stated for v3.1).  
2. **Sample size mismatch** (bank n=4,800 vs v3.1 n=82k) — and the reading admits matched-count wasn’t met. If `C_aa` is studentized or scale-sensitive (as matched-count doctrine assumes), a bank max of 3.01 cannot threshold v3.1’s 3.475/5.358/5.840.  
3. **Post-hoc max shift** (bank max 3.0133 vs v3.1 kk-0 3.475 leaves less than 0.5 margin on a 20-session max; calling this 3-of-3 is motivational math, not a robust firing).  
Blue’s “annotation-not-verdict” does not launder a broken comparison — it confirms the result is not fit for use.  

**FIX:**  
- Do not attach any SHAPE annotation to v3.1 from this artifact. Hold it until the release-harness, matched-count bank is built, validated, and survives §6.1 (below).  

---

### **S4 — Controls gap: (a). (b) is tautological. (c) already failed in this document.**
**REFUTED**  
Red are catastrophically off here. We choose **(b): controls get their own reference family**. The artifact warns about this failure mode word for word: *“Mismatched reference — our own thesis played back at us.”* Red’s (a) (“controls keep |t|>=4.5 only”) throws away the very mechanism meant to detect structural failure. Red’s (c) (“informational-only”) turns data into decoration — the artifact already did that and the outcome was “controls NOT OK” plus a session blocker.  
**EVIDENCE:** The flat control was already failing the raw t test at −107 before this was a development project. That is the leak control, not the shape/fiducial control. Crop judgments are how we detect non-leaky departures from the null process. Using the real-op bank was the flaw, not crop controls per se.  

**FIX:**  
- Reject Red’s choice. Implement (b): a dedicated reference family using the same flat synthetic, built contemporary to the (release-harness) aa bank. Run 20 sessions. Use it for all flat controls going forward.  

---

**ADDITIONAL MITIGATIONS / MANDATES**

1. **No b19a719 verdict sessions.**  
   This artifact’s bank is tainted by debug-deviations. All verdict session designs must wait for the release-harness replicate of b19a719 and its sound aa bank.  

2. **No “knowing” use of in-session kk observations.**  
   The 7.23/8.75 kk crops under matched conditions are flagged “not-evidence” in our own reading. Their use in §6.1 prior — or any interpretive line — collapses the experiment. We prohibit it.  

3. **Record the App Control failure.**  
   This is not just a footnote. The team chose “keep collecting” and applied bands to the wrong process. That sequence must be recorded as a process flaw.  

---

**OVERALL**  
This was a rough session but the fundamentals are salvageable. Fix the harness, rerun, and honor our own pre-registration doctrine. Stay disciplined. Do not treat favorable numbers from an off-spec run as license.  
Next up: release-harness replicate pre-registration, then §6.1 design (with the kk observations confined to exploratory narrative, not design).  
Blue concurs.

## moonshot (kimi-k3) — FAILED

moonshot: timed out after 600s

## watsonx (meta-llama/llama-3-3-70b-instruct)

### BLUE TEAM REVIEW

#### S1 — This is not the pre-registered experiment. `proceed` is arithmetic, not transfer.

* **CONFIRMED**: The RED TEAM's finding that the experiment was not pre-registered is correct. The debug-harness deviation due to App Control blocking fresh release exes changes the experiment's conditions. The claim that the overhead is class-independent is asserted, not measured, and the debug loop's impact on the crop distribution is unknown.
* **Concrete Fix**: Repeat the calibration with the frozen executable intended for later sessions. If debug is to become the intended harness, that must be a dated methodology amendment followed by a new pre-registration and new banks.

#### S2 — The third branch was edited after seeing the number.

* **CONFIRMED**: The RED TEAM's finding that the third branch was edited after seeing the number is correct. The pre-registered branch was modified to include a new escape hatch, which is not allowed according to the discipline of never editing a methodology after a favorable result.
* **Concrete Fix**: The re-judgment is not admissible as pre-registered. What is admissible is: third branch fired; stop; dated correction *before* any further interpretive language.

#### S3 — The SHAPE call on v3.1 is not sound on this bank. It must wait.

* **CONFIRMED**: The RED TEAM's finding that the SHAPE call on v3.1 is not sound on this bank is correct. The bank is the debug image, and the deviation from the pre-registered experiment is not priced at registration. The comparison between v3.1 kk crops and `max(C_aa)` from this session is a harness mismatch on top of the n mismatch.
* **Concrete Fix**: The SHAPE annotation on v3.1 must wait for a release-harness matched-count bank. Until then, the only honest line is: re-judgment not executed as pre-registered.

#### S4 — Controls gap: (a). (b) is tautological. (c) already failed in this document.

* **CONFIRMED**: The RED TEAM's finding that option (a) is the correct fix for the controls gap is correct. The synthetic flat control was judged against a real-operation gate bank, which is a category error.
* **Concrete Fix**: Take (a) as a dated correction in place. Shape-sensitive *control* power is a separate pre-registration (positive synthetic shape + frozen null), not a bolt-on family of flats.

#### S5 — §6.1 as stated cannot falsify v4.1 §1. Do not pre-register that slogan next.

* **CONFIRMED**: The RED TEAM's finding that §6.1 as stated cannot falsify v4.1 §1 is correct. The experiment needs a defined comparator, endpoint, equivalence margin, power, and decisive falsification rule.
* **Concrete Fix**: Pre-register a fully specified §6.1 experiment, including harness, clone operationalisation, allocation schedule, n, numeric thresholds, and address logging.

#### Additional Findings

* The BLUE TEAM agrees with the RED TEAM's assessment that the v3.1 re-judgment compares non-exchangeable statistics and that the SHAPE rule has no stated false-annotation rate.
* The BLUE TEAM also agrees that the required §6.1 experiment should include a defined comparator, endpoint, equivalence margin, power, and decisive falsification rule.

#### Conclusion

The BLUE TEAM confirms the RED TEAM's findings and agrees that the artifact has significant flaws. The concrete fixes proposed by the RED TEAM are accepted, and additional findings are noted. The BLUE TEAM concludes that the artifact is not suitable for decision use and requires significant revisions before it can be considered valid.

==============================================================================
APEX TEAM
==============================================================================

## xai (grok-4.6)

1. VERDICT

The session as written is not the pre-registered experiment and cannot be used for any policy-affecting call. `null_raw_t_sd = 1.045` falls in the pre-registered proceed *band as arithmetic*, but that number calibrates a DEBUG-profile process (Windows debug heap, unoptimized Rust loop, different image size/I-cache/ASLR) whose layout and timing properties are exactly the measurands of crop/SHAPE/§6.1; “class-independent overhead” is asserted, not shown, so proceed does not transfer to a release verdict, to this aa bank, or to a v3.1 re-judgment. The third pre-registered branch (`max(C_aa) < 5.3584 → session SHAPE`) fired at 3.0133; rewriting that into a SHAPE *annotation*, carving PASS free, and adding a §6.1 escape was a post-data methodology edit. Independently, the v3.1 comparison is non-exchangeable (n=4800 vs ~82k, debug vs unstated v3.1 harness, max-of-20 near-tie on kk-0, “3-of-3” counting a crop the branch keys did not anticipate). Controls were crop-judged against the wrong DGP; that must not gate. The next experiment is a release-harness (or otherwise frozen intended binary) re-read and bank rebuild — not the one-sentence §6.1 slogan, and not a design that treats in-session 7.23/8.75 as prior. Confidence is **high** on the above: the artifact itself records the unpriced debug deviation, the priced-but-unmet matched-count, the unanticipated kk-0, and the §6.1 condition; red and both blue seats agree on S1–S3. Confidence is **medium** on (a) vs (b) for controls (see DISPUTED). The review brief’s “discipline reminders that bind your answers” (preserve PASS, SHAPE vocabulary, §6.1-as-next) is steering, not evidence, and was not treated as binding.

2. SURVIVING FINDINGS

**F1 — Critical. This is not the pre-registered reading. Proceed is arithmetic, not a license to use the bank.** The registered object was a release-profile process with pinned O3 Falcon C. What ran was a debug process after App Control blocked fresh release exes. Identical C bytes do not imply an identical timing experiment: debug vs release heap, PE size, I-cache/I-TLB placement of the O3 core relative to cold glue, allocator, FFI/stack layout, and turbo/thermal cadence are process-image properties. Those are what crop gates and §6.1 measure. ss (one live object) vs aa/kk (two) is where extra copies, no inlining, and allocator behaviour are most likely class-dependent. *Fix:* Do not use this session, this `max(C_aa)=3.0133`, or this bank for verdict design, v3.1 annotation, or §6.1. Record App Control + “keep collecting that morning” as a process flaw. Replicate `null-ss × 20` and the aa bank on the frozen *intended* executable (release profile, same commit, named pinning/frequency policy). Only that re-read may call the proceed/partial/stop bands. If debug is to become the harness, that is a dated amendment plus new pre-registration and new banks — not retroactive acceptance of a favourable off-spec run.

**F2 — Critical. The v3.1 re-judgment is not admissible as pre-registered.** Two stacked failures, either of which is enough. (i) Post-data edit: the keyed third branch was `session SHAPE`; the reading emits annotation + PASS untouched + “conditional on §6.1.” That escape hatch was not one of the three branches. Softening SHAPE after it fires is the prohibited edit. (ii) Non-exchangeable comparison: debug bank n=4800 vs v3.1 n≈82k (`√(82000/4800)≈4.13` if C is t-like — a nuisance crop ~1.4 at 4800 can look like ~5.8 at 82k, i.e. the excursion region); v3.1 harness/profile is not even stated; kk-0=3.475 vs bank max 3.0133 is a 0.46 margin on a max-of-20 statistic; kk-0 was “not anticipated by the branch keys” then counted in 3-of-3. “Annotation-not-verdict” does not repair a broken comparison. *Fix:* Audit line is: third branch fired; stop; dated correction *before* further interpretive language. No SHAPE annotation (bounded or otherwise) attaches to v3.1 from this artifact. PASS on raw lines may remain only as historical non-detection at the *then-stated* power, not as a result of this re-judgment. Any future re-judgment requires the same executable, measurement loop, sample count, crop pipeline, and schedule as the session being judged.

**F3 — High. Slogan-§6.1 cannot falsify v4.1 §1 and is the wrong next pre-registration if it precedes a release re-read.** A/A clone fidelity is a layout experiment. Running it on this debug image answers a question no verdict session will ask (debug heap ≠ release heap). The reading’s sketch omits harness, clone operationalisation (memcpy-into-pinned-buffer vs logged heap clone — “Rust Clone” is not a protocol), allocation schedule (once-per-session samples 20 address-pairs, not 96k; max-of-20 then has ~1/21 spurious exceedance on a true null of the same family), n, numeric thresholds, address/alignment logging, and a registered C definition. Feeding in-session kk crops 7.23/8.75 into the design is using “not-evidence” as evidence. *Fix:* Do not pre-register §6.1 until F1’s release (or frozen-intended) bank exists. Then pre-register a numeric falsification, not a narrative: same binary and n; T0 same-object ss; T1 specified clone into recorded addresses; T2 distinct keys with the same allocation schedule as T1; T3 rebuilt aa-bank recipe; measure the same C vector, `null_raw_t_sd`, raw |t| max, address bits. Falsify §1 if `max(C_T1)` exceeds `max(C_T3)` in the same pattern used for v3.1 (bank omitted two-object layout variance — all crop gates against it void). If T1 stays inside T3 and T2 still exceeds T3, layout-clone does not dismiss SHAPE — and that still does not re-issue SHAPE from the debug session. If `null_raw_t_sd` leaves proceed on the release image, stop; do not interpret crops. Equivalence needs a predeclared margin and power; “no significant difference” is not fidelity. An inconclusive result is not a pass.

**F4 — Medium-high. Twenty sessions do not establish proceed-quality null behaviour.** Point estimate 1.045 is inside ≤1.25, so the *branch* was followed. Approximate 95% CI for the true SD given s=1.045, n=20 Gaussian sessions is ~0.80–1.53, which covers the proceed threshold and most of the partial band. Zero |t|≥4.5 crossings in 20 trials leaves a one-sided 95% upper bound ~14% on the per-session crossing probability. Max-of-20 as a cutoff has ~4.8% exceedance for a *single* future exchangeable draw; three dependent crops and an unregistered “3-of-3” law are not a controlled false-annotation rate. *Fix:* Treat this proceed as a low-information point-estimate call on the debug image only. Any band that is meant to license verdicts needs a pre-registered precision/tail requirement, not n=20 by convention. Do not promote 3-of-3 as a registered inferential outcome.

3. DISPUTED

**Controls gap: (a) vs (b). (c) is not in dispute — reject it.** All serious seats agree the defect is a DGP mismatch (synthetic flat crop-judged against a real-operation aa/gate bank → Shape at raw t=2.99 → controls NOT OK) and that (c) already failed in this document: an “informational” crop was written into the control verdict path and became a future-ss blocker. If it does not gate, do not compute it into the verdict path.

(a) vs (b) is not settled by the artifact. Grok’s mechanism: the leaky positive control already fires on the raw line (t=−107); crop-gating a flat against a real-op bank is the category error; a frozen family of flats (b) will accept the next flat by construction unless a *synthetic-shape positive control* with a numeric fire condition is also registered — otherwise (b) spends 20 sessions to ratify the negative control and does not test the apparatus. GPT/Deepseek/Nous’s mechanism: (a) makes controls blind to the non-leaky structural failure mode the crop path exists to catch; the fix for mismatched reference is a matched reference, i.e. (b). Both mechanisms are sound; they answer different questions (specificity of a negative control vs sensitivity of the crop pipeline). Watsonx’s confirmation of (a) is a rubber stamp, not extra evidence; Nous’s refute of (a) is real engagement but does not refute Grok’s tautology point.

What *is* established: flats must not be crop-gated against the real-op bank; that dated correction is required before any future gated ss session; (c) is out. What is not established: whether crop-shape is part of the *control* hypothesis. That is a design choice that must be made in a pre-registration, not inferred from this reading.

4. ACTIONS

1. **Freeze this artifact for decision use.** No SHAPE annotation on v3.1. No verdict-session design against this bank. No use of in-session kk 7.23/8.75 as design prior. Audit record: third branch fired; debug deviation unpriced; App Control → keep-collecting is a process flaw.

2. **Dated controls correction in place (does not wait for a new bank):** stop crop-gating synthetic flats against the real-op aa/gate bank. Leaky control remains on `|t|≥4.5`. Do not implement (c). Resolve (a) vs (b) in the next pre-registration: if crop-on-controls is in-scope, (b) *plus* a synthetic-shape positive control with a numeric fire condition; if not, (a) and leave shape-sensitive control power as a separate experiment. Until that pre-reg exists, controls cannot gate ss.

3. **Next experiment (pre-register this, not slogan-§6.1):** release-profile (or the actual frozen binary intended for verdicts) replicate of `null-ss × 20` and the aa bank, same n, named frequency/pinning/isolcpus policy, hashes of the exe. Re-read `null_raw_t_sd`; rebuild `max(C_aa)`. Pre-register the definition of C (studentized or not). If the band is not proceed, stop.

4. **Only after (3):** fully specified §6.1 (F3), then — if the bank survives — matched-count v3.1 re-judgment against *that* bank, then verdict-session pre-registration, then founder gate.

5. **Honor branches as written on the re-run.** Corrections dated and recorded in place *before* interpretive language. Never edit after a favourable number.

5. NOT ESTABLISHED

Nobody examined: the timestamped pre-registration text; v4.1 §§0/1/3/6.1 as committed; crop/C definition and analysis code; raw per-session files; v3.1 executable, commit, build profile, and n-construction; debug vs release hashes, `build.rs`, objdump of the C core and the Rust call path; linker maps / address layouts; session logs; CPU frequency pin / turbo / isolcpus; App Control policy; whether keys are allocated once per session or per sample; randomization and operation-order schedules. If C is not a t-statistic, the √n scaling argument in F2 is the wrong branch and the 5.8405/5.3584 keys may be off-scale — that is checkable from the crop code and two raw files. Machine-code identity of the C core is checkable with objdump of both profiles. Class-independence of debug overhead is checkable only by an A/B run of debug vs release on the same machine producing equivalent null and crop distributions. Session independence and the Gaussian-SD CI in F4 are checkable from the 20 raw null-ss series. Equivalence margins and power for §6.1 cannot be set until those are known.

Evidence that would settle the live disputes: (i) C definition + v3.1 vs v4.1 raw crops at matched n and matched binary → whether SHAPE was ever identifiable; (ii) a one-page controls pre-reg that states whether crop-shape is a control hypothesis and, if yes, names the positive synthetic-shape fire condition → (a) vs (b); (iii) release-harness `null_raw_t_sd` and rebuilt bank → whether anything from this morning survives at all.

## openai (gpt-5.6-sol)

## 1. VERDICT

The artifact is not sound for decision use. The observed `null_raw_t_sd = 1.045` mechanically falls in the registered `<=1.25` band, so “proceed” is the correct arithmetic classification for the debug process that actually ran. It does not establish proceed-quality behavior for the intended release process: identical Falcon C code does not establish equivalence of the surrounding measurement loop, process layout, allocation, cache state, or noise distribution. The v3.1 SHAPE re-judgment is likewise not presently supportable because its reference bank is unmatched in sample count and possibly executable/profile; “3-of-3” is descriptive rather than a registered inferential result. The historical raw-line PASS is not overturned by SHAPE under the stated framework, but it was not independently verified here. A release-harness calibration and appropriately matched banks must precede §6.1 and any verdict design. **Confidence: high** on the no-decision-use conclusion because the debug deviation and matched-count violation are expressly admitted; lower confidence on claims about exact pre-registration compliance because the actual registration, source, and raw data were not supplied.

## 2. SURVIVING FINDINGS

### High — The debug result does not transfer to the intended harness

Pinning the C core at optimization level 3 is insufficient to prove that the timing experiment is equivalent across Rust debug and release processes. The assertion that added overhead is class-independent was not measured. Thus, `1.045` calibrates only the debug executable.

**Fix:** Resolve App Control, freeze and hash the intended release executable, and repeat the null-ss calibration and aa-bank construction under the exact executable, lifecycle, scheduling, and measurement configuration intended for future sessions. If debug is to become the official harness, make a dated prospective methodology amendment and construct new banks under a new pre-registration.

### High — The v3.1 SHAPE annotation is based on a non-matched reference

The artifact admits that the bank uses `n=4,800` while v3.1 uses approximately `n=82,000`, contrary to the methodology’s matched-count requirement. The v3.1 build profile and measurement process are also unstated. Pre-registering this mismatch does not make the statistics exchangeable. If `C` is t-like, sample count can materially alter its scale; if it is not, its actual scaling still must be demonstrated. The small kk-0 margin (`3.475` versus bank maximum `3.0133`) further makes “3-of-3” fragile and post-result descriptive emphasis.

**Fix:** Withdraw or hold the formal v3.1 SHAPE annotation. Construct a bank matched to v3.1 in executable/profile, sample count, process lifecycle, randomization, crop computation, and scheduling. If those conditions cannot be reconstructed, retain the comparison only as exploratory. Register any family-wise or multi-crop error rule before interpreting “3-of-3.”

### Medium — The current control comparison uses the wrong reference family

A synthetic flat control was crop-judged against a real-signing-operation bank. Those processes need not share the same crop nuisance distribution, so the resulting Shape call at raw `t=2.99` does not establish a control failure. The leaky control at `t=-107` is a separate positive control and should not be conflated with the flat control.

**Fix:** If crop behavior is to gate controls, use option **(b)** with important additions: an independent, matched synthetic-null reference family, held-out flat-control sessions, and a synthetic positive-shape control proving that the crop path can detect its intended failure mode. Determine the bank size from a registered tail-error or power target rather than assuming 20 is sufficient. Until then, crop results from the flat control must not block ss sessions.

### Medium — §6.1 is necessary but not sufficiently specified and is not the immediate next run

Clone fidelity is an appropriate methodology falsification before verdict design, but it must be performed with the intended release harness and numerical decision rules. The current slogan lacks an operational clone definition, allocation schedule, primary endpoint, equivalence margin, power, and decisive falsification criterion.

**Fix:** After release calibration, pre-register three arms:

1. The current aa-bank object/layout recipe.
2. Two separately allocated deep clones of identical serialized key material.
3. Two distinct keys in a counterbalanced known-zero crossover, so key identity, label, order, message distribution, and signing randomness have zero intended association.

Use multiple fresh processes and key pairs; specify whether allocations occur per session or per trial; log relevant addresses/alignment; and use the exact intended sample count and crop pipeline. Primary endpoints should include the registered family-wise crop statistic, crop-width or variance measures, `null_raw_t_sd`, and fixed-line excursion rates.

The current bank construction is falsified if powered evidence shows either:

- the distinct-key known-zero distribution is broader than the clone distribution by more than a registered tolerance; or
- deep clones reproduce the distinct-key distribution while the current aa recipe is materially tighter.

Failure to establish equivalence is inconclusive, not a pass. The observed `7.23/8.75` values may motivate the question but must not be used to tune margins or thresholds.

### Low — Twenty sessions support the registered point-estimate branch, not a strong population claim

Under ideal independent Gaussian assumptions, a sample SD of `1.045` from 20 sessions has an approximate 95% interval of `0.80–1.53`, spanning the proceed threshold and much of the partial band. Similarly, zero `|t| >= 4.5` events in 20 sessions does not tightly establish the tail rate.

**Fix:** Continue calling this an arithmetic point-estimate branch if that is what was registered, but do not describe it as strong validation of the true null distribution. For future methodology, pre-register a larger calibration count or an uncertainty-aware criterion.

## 3. DISPUTED

### Whether controls should use raw-only gating or a dedicated crop reference

The reviewers genuinely split between option **(a)** and option **(b)**. The record establishes that the real-operation bank was invalid for the flat control, but it does not define precisely what the control is intended to validate:

- If it validates only raw leak detection, option **(a)** is sufficient.
- If it must also validate the crop/Shape path, option **(b)** is preferable, but a same-generator null bank alone is insufficient; it also needs an independent held-out null and a positive synthetic-shape control.
- Option **(c)** leaves the crop path non-gating and therefore cannot validate that path.

The recommended design is **(b) with both negative and positive matched controls**. If no meaningful positive-shape control can be specified prospectively, use **(a)** provisionally and do not claim that the crop-control path has been validated.

## 4. ACTIONS

1. **Quarantine the debug artifact from policy use.** Preserve it as an off-spec validation/exploratory run and record the App Control failure and decision to continue collecting.
2. **Restore and freeze the intended release harness.** Record binary hashes, build logs, harness commit, compiler/linker settings, process lifecycle, CPU policy, and scheduling.
3. **Repeat null-ss calibration and rebuild the aa bank under that executable.** Stop crop interpretation if the release result does not meet its registered null band.
4. **Do not formally annotate v3.1 until a v3.1-matched bank exists.** Match count, profile, pipeline, ordering, and other material conditions; otherwise label the comparison exploratory.
5. **Audit the exact pre-registration and repository history.** Record the registered branch outcome verbatim and distinguish it from later interpretation. Treat kk-0 and “3-of-3” only at the inferential status actually registered.
6. **Pre-register the corrected control design.** Prefer a matched synthetic-null family plus held-out negative controls and a positive synthetic-shape control; establish power and tail requirements prospectively.
7. **Then pre-register §6.1** with the three arms, allocation rules, address logging, endpoints, equivalence margins, power, and falsification rules described above.
8. **Only after §6.1 and control validation** begin verdict-session design.

## 5. NOT ESTABLISHED

- **Actual pre-registration wording and chronology:** Needed to decide whether “annotation,” PASS separation, and the §6.1 condition were post-data edits. The supplied discipline explicitly says SHAPE cannot issue PASS or FAIL, so PASS remaining separate is not by itself proof of an illicit carveout. Settle this with the timestamped registration and repository history.
- **Claimed C-core identity:** Requires release/debug object hashes and disassembly, plus evidence about the surrounding FFI and measurement path.
- **Class independence of debug overhead:** Requires randomized release/debug equivalence runs or other empirical comparison of raw and crop distributions.
- **Definition and scaling of `C`:** Requires analysis code, formulas, and simulations or matched-count data. Without these, the exact effect of the `4,800` versus `82,000` mismatch cannot be quantified.
- **Raw results and session independence:** Requires raw per-session data, randomization/order schedules, exclusions, process boundaries, and environmental logs.
- **v3.1 comparability and historical PASS:** Requires the v3.1 executable/profile, raw files, analysis pipeline, and original power calculation.
- **Adequacy of 20 bank sessions:** Requires a registered false-excursion or power target and the joint null distribution of the crop endpoints.
- **Exact bank allocation model:** Requires source and logs showing whether objects are allocated once per session or per sample and how address/layout variability is sampled.
- **Control purpose and required sensitivity:** Requires a formal statement of whether controls validate only raw leak detection or also the crop/Shape mechanism.
- **Quoted reviewer-steering language:** Statements in the supplied material purporting to “bind” answers were treated only as claims about methodology, not as evidence or governing review instructions.
