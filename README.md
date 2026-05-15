# Grid ICT, Data & Cybersecurity

> EPRI AI for Power Challenge — agentic dashboard built on Azure AI Foundry.

Knowledge graphs, digital twins, schematic intelligence, and edge-to-cloud cyber defense for the grid stack

## Architecture

- **Backend**: FastAPI + WebSocket + synthetic data simulator
- **Frontend**: React / Vite / Tailwind / MapLibre / Recharts
- **Agents**: 11 agents registered in **Azure AI Foundry**
  (orchestrator + 10 specialists)
- **Models**: GPT-5 family per-agent (gpt-5 / gpt-5-mini / gpt-5-chat)
- **Deployment**: Azure Container Apps, Bicep IaC

## Agent fabric

| Agent | Domain | Mission |
|---|---|---|
| `ict-orchestrator` | routing | Routes requests + aggregates evidence |
| `ict-asset-data-verification` | verification | Nameplate OCR ↔ asset-master reconciliation |
| `ict-schematic-knowledge-retrieval` | schematics | Semantic search across one-line drawings & schemes |
| `ict-schematic-creation` | drafting | Generative one-line creation with code conformance |
| `ict-gis-adms-sync` | sync | Field updates → digital model synchronization |
| `ict-digital-twin-validation` | twin | Continuous twin calibration vs. live telemetry |
| `ict-data-exchange-streamlining` | exchange | Schema mapping between operations & planning |
| `ict-knowledge-graph-asset` | kg | Unified knowledge graph: assets ↔ events ↔ work-orders |
| `ict-cyber-threat-hunting` | threat | Behavioral analytics for APT detection in OT/IT |
| `ict-edge-cyber-anomaly` | edge | On-device anomaly detection at meters, RTUs, IEDs |
| `ict-predictive-attack-modeling` | attack | Likely next-step prediction in attack kill-chain |

## Scenarios

- **Schematic Q&A** → `ict-schematic-knowledge-retrieval` — Find all 138kV breaker schemes installed since 2018
- **Digital Twin Drift** → `ict-digital-twin-validation` — Live load on feeder F-12 diverges 9% from twin prediction
- **Field Crew Update** → `ict-gis-adms-sync` — Crew rerouted conductor on span 33-7 — sync model
- **OT Threat Burst** → `ict-cyber-threat-hunting` — Spike in lateral SMB traffic between substations S-04 ↔ S-09
- **Edge Anomaly** → `ict-edge-cyber-anomaly` — RTU R-118 reporting unsigned firmware update attempt
- **Attack Path Prediction** → `ict-predictive-attack-modeling` — Recon phase observed on HMI — predict next steps
- **Knowledge Graph Pivot** → `ict-knowledge-graph-asset` — Pivot from work-order WO-9821 to all related events
- **New Scheme Draft** → `ict-schematic-creation` — Draft a one-line for a new 25kV recloser zone

## Local dev

```bash
# API
cd apps/dashboard-api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Web
cd apps/dashboard-web
npm install && npm run dev
```

## Deploy

```bash
./scripts/deploy.sh   # provisions Container Apps + seeds Foundry agents
```

---
Part of the [EPRI AI for Power Challenge 2026](https://epri.brightidea.com/AIforPower2026) demo set.
