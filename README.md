# SIH26182 — VASP Attribution (SetuAI)

Takes a wallet address, walks a recorded transaction path, and reports where the
funds land: which VASP, how confident we are, whether that VASP is domestic or
foreign, and — if the trail dies — what the investigator should do next.

This is a **testing-phase prototype**. The tracer reads a fixture file; it makes
no network calls and touches no chain. Read-only by construction.

---

## Run it

Two terminals.

**Backend** (http://localhost:8010):

```bash
cd E:\SIH26182\backend && .venv\Scripts\activate && uvicorn app.main:app --reload --port 8010
```

**Frontend** (http://localhost:5183):

```bash
cd E:\SIH26182\frontend && npm run dev
```

Open http://localhost:5183, click one of the fixture-case buttons under the
input, and hit **Trace**. Interactive API docs are at
http://localhost:8010/docs.

First-time backend setup, if the venv is missing:

```bash
cd E:\SIH26182\backend && python -m venv .venv && .venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

## Layout

```
backend/
  fixtures/trace_fixtures.json   the ONE fixture file — all demo data lives here
  data/watchlist.json            synthetic risk watchlist; not an intelligence feed
  app/models.py                  Pydantic request/response contract
  app/tracer.py                  fixture lookup, returns the hop sequence
  app/scoring.py                 weighted confidence sum
  app/risk_classification.py     independent explainable risk rules and score
  app/deadend.py                 terminal-node check + recommended_action
  app/main.py                    FastAPI app: POST /trace, GET /cases, GET /health
frontend/
  src/App.jsx                    the whole UI: input, badge, result card
```

---

## API

### `POST /trace`

```json
{ "wallet_address": "bc1qh4kl29xr7vt0m3qeuz8fj6ldw5s0navxp2yqte", "chain": "BTC" }
```

Returns the hops, the destination label, a 0–100 confidence score with its
full breakdown, a `domestic`/`foreign`/`unknown` flag, a
`clean_path`/`dead_end` status, a separate `risk_classification` object, and a
`recommended_action` when the path dies. Risk contains a 0–100 score, tier,
matched typology flags, and per-rule explanations. It is independent of
attribution confidence: confidence estimates whether the VASP attribution is
correct; risk summarizes suspicious patterns in the traced flow.

Unknown address → `404` with a message pointing at `GET /cases`.

### `GET /cases`

Lists the addresses the fixture can trace. The UI uses this for its one-click
demo buttons, so adding a case to the fixture makes it appear in the UI with no
code change.

### `GET /health`

`{"status": "ok"}`.

---

## Fixture cases

| Start address | Path | Result |
|---|---|---|
| `bc1qh4kl29xr7v…` | BTC 4-leg peel → bridge → EVM → exchange | **55** · foreign · `clean_path` |
| `bc1qv3n0xu7ld8…` | BTC → 2 hops → coinjoin | **23** · unknown · `dead_end` |
| `0x7c3e0a9d15…917da6` | ETH → offshore exchange | **66** · foreign · `clean_path` |
| `0x41e7b2d0956a…` | ETH → deposit → hot wallet | **80** · domestic · `clean_path` |
| `bc1qrapidmix…` | BTC rapid hops → mixer | **High risk** · mixer + rapid-hop rules |
| `0x7f3c9a1d5e…` | ETH → sample watchlist address → VASP | **Critical risk** · watchlist match |

Chosen so confidence bands, path statuses, and risk tiers are demoable without
editing anything.

---

## Risk classification

`risk_classification.py` evaluates the traced hops with independent, deterministic
rules: mixer or unlabeled-DEX exposure; three or more timestamps within ten
minutes; two or more bridge hops; a hop value above the configurable
`HIGH_VALUE_THRESHOLD` (default 100000); and addresses matching
`backend/data/watchlist.json`. Rule functions can be tested independently.
Matched rules contribute transparent points (capped at 100); a watchlist match
sets the tier to **Critical**, two or more other matched rules to **High**, one
to **Medium**, and none to **Low**. The response includes the score, flags, and
rule explanations separately from confidence.

**The watchlist is synthetic sample data for demonstrating the risk-scoring
architecture only.** Its fabricated addresses and labels are not allegations,
not verified matches, and not a real intelligence feed. For production, replace
it with a vetted, maintained source such as applicable OFAC SDN data or licensed
provider labels (for example Arkham), subject to legal, licensing, provenance,
and false-positive review. Production high-value rules should also normalize
asset amounts to a common fiat value before applying a shared threshold.

---

## How confidence is scored

A transparent weighted sum in `scoring.py` — no ML, no randomness. Same inputs
always give the same score, and every component ships with a plain-English
reason that the UI renders under "How this score was reached".

| Component | Points |
|---|---|
| Base (any successfully traced path) | +40 |
| Label freshness | +25 ≤7d · +15 ≤30d · +8 ≤90d · +3 ≤180d · 0 older |
| Path directness | +25 ≤2 hops · +18 ≤4 · +10 ≤6 · +5 ≤8 · 0 longer |
| Mixer on path | −35 |
| Bridge on path | −15 |
| DEX on path | −10 |

Clamped to 0–100. Bands: **high** ≥70, **medium** 40–69, **low** <40.

---

## What counts as a dead end

`dead_end` means the trail **terminates** somewhere unattributable — a mixer, a
bridge whose payout we cannot follow, or an unlabelled DEX. Crossing one of
those mid-path is *not* a dead end: if the funds came out the other side and
landed on an identifiable VASP, the path is still actionable, it just costs
confidence. That is why the worked example scores 55 and still returns
`clean_path` despite its bridge hop.

A terminal node with no `vasp_name` is also a dead end, even if it looks like an
ordinary address — there is nobody to serve a request on.

Recommended actions are keyed to the terminal node type in `deadend.py`:
mixer → escalate to a demixing analyst; bridge → request operator logs for the
matching payout; DEX → identify the router and pivot to the post-swap output.

---

## Boundaries — do not mistake these for real

- **All fixture data is synthetic.** Addresses are plausible-format but *not*
  checksum-valid; they will fail a real bech32/EIP-55 validator. Tx hashes,
  amounts and timestamps are fabricated. The named exchanges have not received
  these funds — they are placeholder labels for a demo.
- **No chain access of any kind.** No RPC, no block explorer, no API key. The
  tracer only reads the JSON file.
- **No persistence.** No database, no audit log, no case store. Every request is
  computed fresh and forgotten.
- **The `chain` field in the request is a hint, not a filter.** Lookup is by
  address alone, and the response's `chain` comes from the fixture. A BTC path
  that bridges to Ethereum legitimately reports hops on both chains, so the
  recorded path wins over the requested chain.
- **Deliberately out of scope for this phase:** LLM drafting, SAHYOG routing,
  audit dashboard, continuous monitoring, clustering, auth, Docker, Postgres.
