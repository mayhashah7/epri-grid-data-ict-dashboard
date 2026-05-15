# AMI Agentic Dashboard ⚡🤖

> **Spectacular, agentic Advanced Metering Infrastructure (AMI) intelligence platform** for power & utilities — built on **Azure AI Foundry**, deployed on **Azure Container Apps**, and demoed live to enterprise utility customers.

This solution goes far beyond a typical AMI dashboard. It pairs a **real-time smart-meter telemetry pipeline** with a **multi-agent reasoning fabric** that autonomously triages outages, hunts energy theft, orchestrates demand response, manages distributed energy resources (DER), predicts transformer failures, surfaces billing anomalies, and answers customer questions in natural language.

---

## Why this is different

| Solution-accelerator pattern | What we built instead |
|---|---|
| Single chatbot bolted onto a BI dashboard | **Specialist agent fabric** with an orchestrator that routes by intent and resource class |
| Static synthetic CSV | **Streaming synthetic AMI generator** producing 15-minute interval reads, outages, voltage sags, theft scenarios, DER backfeed, and weather correlation |
| Generic RAG | Tool-augmented agents calling **typed AMI tools** (`get_meter_reads`, `correlate_outage_calls`, `score_theft`, `dispatch_crew`, `compute_demand_response`, `forecast_load`, `score_transformer_health`, `detect_billing_anomaly`) |
| One LLM | Foundry-managed agents with per-agent prompt, model, and tool scope; full trace persisted to Cosmos DB and streamed to the UI over WebSocket |
| Click-ops deploy | One-shot **Bicep + GitHub Actions** deploy, OIDC federated identity, no stored secrets |

---

## Capabilities (a.k.a. what to demo)

1. **Live Grid Map** — 50,000 simulated meters across 12 substations with sub-second updates over WebSocket.
2. **Outage Storm Simulator** — inject a feeder fault and watch the *Outage Intelligence Agent* correlate last-gasp messages, group by transformer, predict restoration time, and dispatch a crew.
3. **Energy Theft Hunter** — the *Theft Detection Agent* runs an unsupervised anomaly score on consumption vs. neighbors and writes an investigation case.
4. **DER & Net-Metering** — the *DER Management Agent* tracks rooftop-solar backfeed, flags over-voltage on the secondary, and recommends Volt-VAR setpoints.
5. **Demand Response Event** — fire a heat-wave scenario; the *Demand Response Agent* selects the optimal cohort, computes expected MW shed, and stages the dispatch.
6. **Predictive Maintenance** — the *Predictive Maintenance Agent* scores transformer health from harmonic distortion and load profile.
7. **Billing Anomaly** — the *Billing Anomaly Agent* explains a customer's spiked bill in plain English (vampire load, tariff change, weather, neighbor benchmark).
8. **Customer Service Copilot** — the *Customer Service Agent* answers "why is my bill high?", "when will my power be back?", and "how do I sign up for time-of-use?" using grounded data.
9. **AMI 2.0 Edge Hooks** — every agent action is recorded as a trace event so utility ops teams can audit AI decisions (governance + cybersecurity story).

---

## Architecture

```
                     ┌────────────────────────────────────────────────┐
                     │  Synthetic AMI Generator (50k meters, 15-min)  │
                     └──────────────────┬─────────────────────────────┘
                                        │  Event Hubs / in-proc queue
                                        ▼
        ┌──────────────────────────────────────────────────────────────────┐
        │  Dashboard API (FastAPI)                                         │
        │  ├─ Telemetry ingestion → Cosmos DB (meters, reads, events)      │
        │  ├─ WebSocket fan-out → React UI                                 │
        │  └─ Chat endpoint → Foundry Orchestrator Agent                   │
        └──────────────────────────────────┬───────────────────────────────┘
                                           │  Azure AI Agents SDK
                                           ▼
        ┌──────────────────────────────────────────────────────────────────┐
        │            Azure AI Foundry — AMI Multi-Agent Fabric             │
        │  ┌──────────────┐                                                │
        │  │ Orchestrator │ classifies intent / event → routes             │
        │  └──────┬───────┘                                                │
        │         │                                                        │
        │  ┌──────┴──┬──────────┬───────────┬──────────┬──────────┬─────┐  │
        │  ▼         ▼          ▼           ▼          ▼          ▼     ▼  │
        │ Outage  Theft     DER          Demand    Predictive  Billing CSR │
        │ Detect  Detect    Management   Response  Maintenance Anomaly     │
        │  └──── shared `ami_tools` library (typed tool schemas) ──────────┘
        └──────────────────────────────────┬───────────────────────────────┘
                                           ▼
                            Cosmos DB (traces, cases, recs) ──► live UI
```

See [`docs/architecture.md`](docs/architecture.md) for the full breakdown.

---

## Repo layout

```
ami-agentic-dashboard/
├── docs/                   Architecture, agents catalog, deploy, demo runbook
├── infra/                  Bicep IaC (subscription-scope main + modules)
├── agents/                 Foundry agent specs + shared `ami_tools` Python library
│   ├── orchestrator/
│   ├── outage-detection/
│   ├── theft-detection/
│   ├── der-management/
│   ├── demand-response/
│   ├── predictive-maintenance/
│   ├── billing-anomaly/
│   ├── customer-service/
│   └── tools/              ami_tools package (schemas + handlers)
├── apps/
│   ├── dashboard-api/      FastAPI + WebSocket + Foundry agent client + simulator
│   └── dashboard-web/      Vite + React + Tailwind + Recharts + MapLibre
├── scripts/                deploy.ps1/sh, seed-foundry-agents.py, simulate-fault.py
├── data/synthetic/         Generators for meters, weather, tariffs, outages
└── .github/workflows/      OIDC-authenticated CI/CD pipelines
```

---

## Quickstart

Prerequisites: `az` CLI, `bicep`, `docker`, `python 3.11+`, `node 20+`, an Azure subscription with quota for **gpt-4o** (10K TPM) and Container Apps.

```pwsh
# 1. Login + set subscription
az login
az account set --subscription <SUBSCRIPTION_ID>

# 2. One-shot deploy (provisions Foundry, Cosmos, Container Apps, ACR, App Insights)
./scripts/deploy.ps1 -Location eastus2 -EnvName ami-dev

# 3. Seed agents into Foundry (idempotent)
python scripts/seed-foundry-agents.py --outputs ./outputs.json

# 4. Open the dashboard URL printed at the end and click "Run Demo Scenario"
```

Local dev (no Azure required, in-process simulator + mock LLM):

```pwsh
cd apps/dashboard-api && pip install -r requirements.txt && uvicorn app.main:app --reload
cd apps/dashboard-web && npm install && npm run dev
```

See [`docs/deploy.md`](docs/deploy.md) for the full guide and [`docs/demo-script.md`](docs/demo-script.md) for the customer demo runbook.

---

## Cost

Designed to fit within **~$15/day** in a sandbox subscription (Container Apps consumption tier, Cosmos serverless, Foundry pay-per-token gpt-4o). Tear down with:

```pwsh
az group delete -n rg-ami-dev --yes --no-wait
```

---

## License

MIT — see [`LICENSE`](LICENSE).
