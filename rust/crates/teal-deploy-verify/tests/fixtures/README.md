# Recorded algod responses (read-only, 2026-11-05)

Recorded once from `https://testnet-api.algonode.cloud` with plain GET / `POST /v2/teal/compile`
requests: no account, no key, no transaction. The offline tests replay them byte for byte.

| File | Request |
|---|---|
| `application_recorded.json` | `GET /v2/applications/770964251` — **one field removed**, see below |
| `compile_approval.json` | `POST /v2/teal/compile` with `recorded_approval.teal` |
| `compile_clear.json` | `POST /v2/teal/compile` with `recorded_clear.teal` |
| `versions_testnet.json` | `GET /versions` |
| `app_not_found_404.json`, `compile_error_400.json` | error bodies, for the exit-2 paths |
| `recorded_approval.teal`, `recorded_clear.teal` | the committed TEAL the compiles were made from |

**`application_recorded.json` is not byte-identical to the response.** `params.global-state` was
removed before committing: its base64 state-variable names (for example `cells_registered`) trip
gitleaks' generic API-key rule, the same false positive `.gitleaks.toml` already allows for the
ARC-56 spec. The verifier never reads that field; every field it does read (`id`,
`params.approval-program`, `params.clear-state-program`) is as served. The unmodified response is
kept outside the repository.

`sdk/tests/test_app_id_references_are_coherent.py` classifies `application_recorded.json` as
FROZEN evidence: it records what the chain served that day and must not be retargeted after a
redeploy.
