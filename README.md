# SIH26182 — VASP Attribution (prototype)

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
  app/models.py                  Pydantic request/response contract
  app/tracer.py                  fixture lookup, returns the hop sequence
  app/scoring.py                 weighted confidence sum
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
`clean_path`/`dead_end` status, and a `recommended_action` when the path dies.

Unknown address → `404` with a message pointing at `GET /cases`.

### `GET /cases`

Lists the addresses the fixture can trace. The UI uses this for its one-click
demo buttons, so adding a case to the fixture makes it appear in the UI with no
code change.

### `GET /health`

`{"status": "ok"}`.

---

## The three fixture cases

| Start address | Path | Result |
|---|---|---|
| `bc1qh4kl29xr7v…` | BTC 4-leg peel → bridge → EVM → exchange | **55** · foreign · `clean_path` |
| `bc1qv3n0xu7ld8…` | BTC → 2 hops → coinjoin | **23** · unknown · `dead_end` |
| `0x41e7b2d0956a…` | ETH → deposit → hot wallet | **80** · domestic · `clean_path` |

Chosen so all three confidence bands and both statuses are visible without
editing anything.

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
