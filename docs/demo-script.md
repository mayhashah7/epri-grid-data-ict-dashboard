# Customer demo runbook (~15 minutes)

> Audience: utility VP of Distribution Ops, CIO, head of Customer Experience.
> Goal: show that an agentic AI fabric can turn AMI data into action — not just charts.

## Setup (T-5 minutes)

1. Browse to the deployed `dashboardWebUrl` from `outputs.json`.
2. Confirm the **Live Grid Map** shows ~50k meters in steady state (mostly green).
3. Confirm **System Load** chart is updating.
4. Open the **Chat** panel.

## Act 1 — "AMI 2.0 isn't billing — it's situational awareness" (3 min)

1. Hit **Run Scenario → Storm Outage (Feeder F-07)**.
2. Watch the map: ~1,200 meters drop offline within 30 seconds.
3. In the **Active Cases** rail, the `ami-orchestrator` opens case `case-OUT-####`, then routes to `ami-outage-detection`.
4. The outage agent live-traces: `received → group_by_transformer → correlate_with_calls → predict_restoration → recommend_dispatch`.
5. A dispatch recommendation card appears: "Crew Alpha to Transformer T-0734 (88% confidence, ETA 42 min)."

**Talking point:** *"Notice that no human triaged this. The agent fabric correlated 1,200 last-gasp messages with three customer calls and a SCADA trip in under five seconds."*

## Act 2 — "Find the theft" (2 min)

1. Type into chat: *"Are there any meters that look like theft on Substation S-04?"*
2. The orchestrator routes to `ami-theft-detection`, which calls `score_theft` over the substation cohort.
3. Two meters surface with anomaly scores ≥ 0.85 — both with **flat overnight consumption** (a classic bypass tell).
4. Click one — drill-down shows the 30-day load shape vs. the cohort median.

**Talking point:** *"Utilities lose 1–3% of revenue to theft. This agent flags it without you writing a SQL query."*

## Act 3 — "Solar backfeed and Volt-VAR" (2 min)

1. Hit **Run Scenario → DER Backfeed Burst (Feeder F-02)**.
2. The `ami-der-management` agent flags over-voltage on 47 secondaries, recommends an inverter Volt-VAR curve adjustment, and stages a setpoint change.

**Talking point:** *"AMI 2.0 + DERMS — your grid edge becomes controllable."*

## Act 4 — "Heat-wave demand response" (2 min)

1. Hit **Run Scenario → Heat Wave (System Peak)**.
2. Forecast climbs into reserve margin; orchestrator opens a DR case.
3. `ami-demand-response` selects an opt-in residential cohort of ~3,400 meters, projects 4.7 MW shed for 60 minutes, and stages dispatch.

**Talking point:** *"Cohort selection used to take a planner two days. Here it took two seconds and is fully explainable."*

## Act 5 — "Customer self-service" (2 min)

1. Switch chat persona to **Customer**.
2. Type: *"Why was my August bill 40% higher than July?"*
3. `ami-customer-service` calls `get_meter_reads` + `get_weather` + `compare_to_neighbors` and answers:
   * +18% from cooling degree-days (heat wave)
   * +12% from a new always-on load (likely EV charger introduced Aug 12)
   * +10% tariff drift (tier 3 hours)
   * Recommendation: enroll in TOU-D5 to save ~$22/mo.

**Talking point:** *"Your call center burns 4 minutes per bill-shock call. This agent answers in 8 seconds, with citations to the customer's own meter."*

## Act 6 — "Governance & audit" (2 min)

1. Open any case → **Trace** tab.
2. Show the full chronological agent trace: every tool call, parameters, return value, and reasoning step.
3. Show the **Cosmos DB** `traces` container in the Azure Portal — every row is queryable for compliance.

**Talking point:** *"Every AI decision is auditable. This is how we get past the regulator."*

## Tear down

```pwsh
az group delete -n rg-ami-dev --yes --no-wait
```
