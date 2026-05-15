# Architecture

## High-level

```
[Synthetic AMI Generator] ──► [Dashboard API (FastAPI)] ──► [Cosmos DB]
                                       │       ▲                ▲
                                       │       │                │
                                       ▼       │                │
                              [Foundry Multi-Agent Fabric] ─────┘
                                       │
                                       ▼
                              [WebSocket → React UI]
```

## Components

### 1. Synthetic AMI generator (`apps/dashboard-api/app/simulator.py`)

Produces realistic streaming smart-meter telemetry:

* **50,000 meters** across **12 substations**, **96 feeders**, **800 transformers** (configurable).
* **15-minute interval reads** with diurnal + weekly + seasonal patterns.
* Per-meter persona: `residential`, `commercial-small`, `commercial-large`, `industrial`, `ev-owner`, `solar`.
* Injected scenarios: feeder fault, voltage sag, theft (meter bypass), DER backfeed, brownout, demand spike.
* Outputs both: (a) raw reads, (b) derived events (last-gasp, tamper, voltage excursion).

Backed by NumPy + a deterministic seed so demos are repeatable.

### 2. Dashboard API (`apps/dashboard-api/`)

FastAPI service. Responsibilities:

* Owns the simulator loop (asyncio task).
* Persists meters/reads/events to **Cosmos DB** (or in-memory store for local dev).
* Exposes:
  * `GET /api/meters`, `GET /api/substations`, `GET /api/events`
  * `POST /api/scenarios/{name}` — fire a demo scenario
  * `WS /ws/stream` — real-time fan-out of reads + events + agent traces
  * `POST /api/chat` — chat completion routed through the Foundry orchestrator agent
  * `GET /api/agents/traces?case_id=...` — replay agent reasoning

### 3. Multi-agent fabric (`agents/`)

Eight Foundry agents:

| Agent | Role |
|---|---|
| `ami-orchestrator` | Classifies intents/events, routes to specialists, owns case lifecycle |
| `ami-outage-detection` | Correlates last-gasp messages, predicts restoration, recommends crew dispatch |
| `ami-theft-detection` | Scores meter consumption vs. peer cohort + tamper flags, opens investigation cases |
| `ami-der-management` | Monitors solar/storage backfeed, flags over-voltage, recommends inverter setpoints |
| `ami-demand-response` | Designs DR events, selects cohorts, forecasts MW shed, stages dispatch |
| `ami-predictive-maintenance` | Scores transformer/feeder health from harmonic + thermal proxies |
| `ami-billing-anomaly` | Explains bill spikes (weather, vampire load, tariff, neighbor benchmark) |
| `ami-customer-service` | Customer-facing Q&A grounded on per-meter data |

All share the typed Python tool library `ami_tools/` (see `agents/tools/`).

### 4. Azure infrastructure (`infra/`)

Bicep, subscription-scoped:

* Resource group `rg-<envName>`
* User-assigned managed identity (UAMI)
* Log Analytics + App Insights
* Azure Container Registry (ACR)
* Cosmos DB (SQL API, serverless) — containers: `meters`, `reads`, `events`, `cases`, `traces`
* Azure AI Foundry account (`AIServices` kind, no Hub) with `gpt-4o` + `text-embedding-3-large` deployments and a project
* Azure Container Apps environment + two apps: `dashboard-api`, `dashboard-web`

### 5. UI (`apps/dashboard-web/`)

Vite + React + TypeScript + Tailwind. Panels:

* **Grid Map** (MapLibre + GeoJSON) with substation/feeder/meter layers, real-time color by status.
* **Live Reads** (Recharts) — system load, voltage profile, top consumers.
* **Active Cases** — cards for each open agent case (outage, theft, DR, etc.) with the live agent trace.
* **Chat** — natural-language interface that routes through the orchestrator agent and renders streaming token output + tool calls.
* **Scenario Runner** — buttons to inject demo events.

## Data model (Cosmos DB)

| Container | PK | Doc shape |
|---|---|---|
| `meters` | `/substation_id` | `{id, meter_id, persona, lat, lon, transformer_id, feeder_id, substation_id, tariff, installed_at}` |
| `reads` | `/meter_id` | `{id, meter_id, ts, kwh, kw, voltage, current, pf, temperature_c}` (TTL 7d) |
| `events` | `/substation_id` | `{id, kind, severity, meter_ids, substation_id, ts, payload}` |
| `cases` | `/case_id` | `{id, kind, status, opened_at, closed_at, owner_agent, summary, recommendation}` |
| `traces` | `/case_id` | `{id, case_id, agent, step, payload, status, ts}` (TTL 30d) |

## Security & governance

* All workload identities use **UAMI**; no client secrets stored in code or config.
* Foundry, Cosmos, ACR all reachable only via UAMI RBAC (`Cognitive Services OpenAI Contributor`, `Cosmos DB Built-in Data Contributor`, `AcrPull`).
* Every agent step is recorded as a trace document → full **auditability** for regulators (a hard requirement for utilities).
* Front-end never sees a Foundry endpoint or model key.
* Container Apps run on managed cert HTTPS by default.
