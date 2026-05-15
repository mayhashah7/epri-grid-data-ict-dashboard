# Agent catalog

Every agent is a Foundry agent (model `gpt-4o`) defined by:

* `agents/<name>/spec.yaml` — name, model, tool list, metadata
* `agents/<name>/prompt.md` — system instructions
* Tool implementations in `agents/tools/ami_tools/`

The orchestrator is the only agent reachable directly from the chat endpoint; everything else is invoked indirectly via `dispatch_to_agent`.

## Tools (shared library)

| Tool | Owner agent(s) | Purpose |
|---|---|---|
| `record_trace` | all | Append a step to a case's reasoning trace |
| `open_case` / `update_case` / `close_case` | orchestrator + specialists | Case lifecycle |
| `dispatch_to_agent` | orchestrator | Hand off to a specialist |
| `get_meter` / `get_meter_reads` | most | Fetch meter metadata + interval reads |
| `get_substation_status` | outage, DR, DER | Aggregate state per substation |
| `correlate_outage_calls` | outage | Cross-reference customer calls with last-gasp messages |
| `group_outage_by_topology` | outage | Cluster offline meters by transformer/feeder |
| `predict_restoration` | outage | ETA based on outage size + crew availability |
| `recommend_crew_dispatch` | outage | Pick crew + ETA |
| `score_theft` | theft | Per-meter anomaly score vs. peer cohort + tamper flags |
| `score_transformer_health` | predictive-maintenance | Health 0–100 from harmonic + thermal proxies |
| `compute_demand_response` | demand-response | Cohort selection + MW shed forecast |
| `get_weather` | billing, DR, outage | Hourly temperature + humidity |
| `get_tariff` | billing, customer-service | Tariff structure for a meter |
| `compare_to_neighbors` | billing, customer-service | Peer benchmark |
| `detect_billing_anomaly` | billing | Decompose a bill spike into drivers |
| `recommend_volt_var` | DER | Inverter Volt-VAR curve recommendation |
| `get_der_status` | DER | Solar/storage backfeed view |

All schemas are in [`agents/tools/ami_tools/schemas.py`](../agents/tools/ami_tools/schemas.py) and exported via `TOOL_SCHEMAS`.
