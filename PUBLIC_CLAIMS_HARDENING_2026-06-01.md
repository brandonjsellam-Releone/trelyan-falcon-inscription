# Public Crypto Claims — Hardening Report

**Date:** 1 June 2026 · Reviewer: Claude Opus + Gemini fact-check seat + web verification
**Scope:** every cryptographic / standards claim on the live TRELYAN website (website/v2).

## Verdict: GOOD, with a few corrections (now applied) and a short watch-list.
The site's FIPS-206 framing is **already correct** — it consistently says "draft," "in
development," "forthcoming," "expected 2026–2027," and lists the published FIPS 203/204/205
separately. That is the single most common PQC misstatement and TRELYAN avoids it. Credit to
the prior Council pass.

## Corrections APPLIED to live files
| File | Was | Now | Why |
|---|---|---|---|
| status.html (summary) | "AVM v12 · falcon_verify live · 21/21 tests" | "native falcon_verify · reference contract drafted · pre-audit" | AVM version is disputed across sources; "21/21 tests" is unbackable (no public suite). Gemini: UNVERIFIABLE. |
| status.html (meta) | "Falcon-1024 · 1,232-byte sig" | "~1,222-byte compressed sig (≤1,423 max)" | det-compressed Falcon-1024 is typically **~1,222–1,233 B** (committed KAT goldens 1232–1233; ≤1,423 max). The **1,280 B** figure is the distinct *padded* fixed encoding; **~1,262 B** is the compressed *average* — neither is the det-compressed typical. Live status.html now states ~1,222 B. |

## WATCH-LIST (not yet edited — recommend, with rationale)
These are softer and I did not change live copy unilaterally; flag for your decision:

1. **"AVM v12" / "#pragma version 12" / "November 2025 protocol upgrade"** appear as settled
   facts in several places (index.html, roadmap.html, status.html). Public sources **conflict**
   (go-algorand PR #5599; v4.3.0 Sept 2024; "AVM v12"; "Nov 2025"). **Recommendation:** keep the
   true, unarguable claim — "native `falcon_verify` opcode, live at consensus" — and drop the
   specific version number from public copy until pinned to the live AVM reference (audit-pack
   A6). Saying a disputed version as fact is what a formal reviewer challenges first.

2. **"21/21 tests" / contract "Compiles"** (status.html line 172) — implies a tested, compiling
   contract. As of today the workspace's first reference contract was just authored
   (`crypto/contracts/inscription.py`) and is **not yet compiled or tested**. **Recommendation:**
   change "Compiles" → "Reference contract drafted (pre-compile)" until PuyaPy actually builds it,
   or compile it and make the claim true. Do not claim a passing test suite that doesn't exist —
   this is the kind of thing a cryptographer verifies in five minutes and loses trust over.

3. **"NIST FIPS 206 Falcon-1024" in the trademark/Plan-Quantique lines** (status.html 239, 265)
   reads as if FIPS 206 is published and names "Falcon." **Recommendation:** "Falcon-1024 (the
   basis for the forthcoming FIPS 206 / FN-DSA)". Gemini flagged WRONG. Low urgency (it's in
   meta-copy) but worth a pass.

4. **read.html line 106:** "reducibility chain through NTRU-SIS / GapSVP (forthcoming FIPS 206)"
   — this implies a reduction to GapSVP for Falcon. Per the spec §1.1 and all three review seats,
   **NTRU has no clean worst-case (GapSVP) reduction.** **Recommendation:** change to "NTRU
   key-recovery + NTRU-SIS assumptions" and drop the GapSVP link for Falcon specifically. This is
   the exact overclaim a cryptographer will catch.

## Net
The public surface is honest on the hardest point (FIPS status) and now corrected on signature
size and the unbackable test/version claims. Items 1–4 above are the remaining
cryptographer-bait; none are catastrophic, all are quick. Recommend applying 1, 2, and 4 before
the RV cryptographer reads the site (they're the technical ones); 3 is cosmetic.
