# TRELYAN — independent verification entry point. See REVIEWER.md for what each step proves.
# Uses .RECIPEPREFIX='>' instead of TAB indentation for portability. Requires GNU make >= 3.82.
.RECIPEPREFIX = >
.PHONY: help verify verify-onchain verify-kat verify-digest

help:
> @echo "TRELYAN independent verification (read-only). Targets:"
> @echo "  make verify          on-chain + offline reviewer checks (needs network; pip installs trelyan-pq)"
> @echo "  make verify-kat      signer byte-identity KAT      (FALCON_DET1024_LIB=/path/to/libfalcon_det1024.so)"
> @echo "  make verify-digest   pinned Falcon source digest   (TREE=/path/to/falcon-src)"
> @echo "See REVIEWER.md for the 5-minute guide and what each step proves."

verify: verify-onchain
> @echo ""
> @echo "Reviewer verification complete. For offline determinism + the pinned build, also run:"
> @echo "  make verify-kat FALCON_DET1024_LIB=...    &&    make verify-digest TREE=..."

verify-onchain:
> python -m pip install --quiet --upgrade trelyan-pq
> python sdk/examples/verify_trelyan.py

verify-kat:
> @test -n "$(FALCON_DET1024_LIB)" || { echo "set FALCON_DET1024_LIB=/path/to/libfalcon_det1024.so"; exit 2; }
> FALCON_DET1024_LIB="$(FALCON_DET1024_LIB)" python -m pytest sdk/tests/test_signature_kat.py -v

verify-digest:
> @test -n "$(TREE)" || { echo "set TREE=/path/to/pinned/falcon/source/tree"; exit 2; }
> python sdk/ci/verify_pinned_digest.py "$(TREE)"
