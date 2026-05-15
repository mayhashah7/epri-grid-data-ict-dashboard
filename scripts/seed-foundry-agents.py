"""Register (or update) every AMI agent in Azure AI Foundry.

Reads agent definitions from `agents/<name>/spec.yaml` + `prompt.md`,
maps tool names to JSON schemas via `ami_tools.schemas.TOOL_SCHEMAS`,
and creates/updates the agent in the project pointed to by
`outputs.json["foundryProjectEndpoint"]` (or env `FOUNDRY_PROJECT_ENDPOINT`).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_AGENTS_DIR = REPO_ROOT / "agents"


def load_outputs(path: str) -> dict:
    with open(path) as f:
        raw = json.load(f)
    if all(isinstance(v, dict) and "value" in v for v in raw.values()):
        return {k: v["value"] for k, v in raw.items()}
    return raw


def load_agent_specs(agents_dir: Path) -> list[dict]:
    out = []
    for d in sorted(agents_dir.iterdir()):
        if not d.is_dir() or d.name == "tools":
            continue
        spec_file = d / "spec.yaml"
        prompt_file = d / "prompt.md"
        if not spec_file.exists():
            continue
        spec = yaml.safe_load(spec_file.read_text(encoding="utf-8"))
        if prompt_file.exists():
            spec["_prompt"] = prompt_file.read_text(encoding="utf-8")
        spec["_dir"] = d.name
        out.append(spec)
    return out


def build_tool_defs(tool_names: list[str], agents_dir: Path) -> list[dict]:
    try:
        from ami_tools.schemas import TOOL_SCHEMAS
    except ImportError:
        sys.path.insert(0, str(agents_dir / "tools"))
        from ami_tools.schemas import TOOL_SCHEMAS  # type: ignore
    return [{"function": TOOL_SCHEMAS[n]} for n in tool_names if n in TOOL_SCHEMAS]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outputs", help="Path to outputs.json from deployment")
    ap.add_argument("--agents-dir", default=None, help="Path to agents/ directory")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    agents_dir = Path(args.agents_dir) if args.agents_dir else _DEFAULT_AGENTS_DIR

    outputs = load_outputs(args.outputs) if args.outputs else {}
    endpoint = outputs.get("foundryProjectEndpoint") or os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    deployment = outputs.get("aoaiDeploymentName") or os.environ.get("AOAI_DEPLOYMENT_NAME", "gpt-4o")
    if not endpoint:
        sys.exit("ERROR: foundryProjectEndpoint not in outputs and FOUNDRY_PROJECT_ENDPOINT not set")

    specs = load_agent_specs(agents_dir)
    if not specs:
        sys.exit("ERROR: no agent specs under agents/")

    if args.dry_run:
        print(f"[DRY] target endpoint: {endpoint}")
        for s in specs:
            print(f"  • {s.get('name')}  tools={len(s.get('tools', []))}  model={s.get('model')}")
        return

    try:
        from azure.identity import AzureCliCredential, ChainedTokenCredential, ManagedIdentityCredential
        from azure.ai.agents import AgentsClient
        from azure.ai.agents.models import FunctionDefinition, FunctionToolDefinition
    except ImportError:
        sys.exit("ERROR: install scripts/requirements.txt")

    client_id = os.environ.get("AZURE_CLIENT_ID")
    cred = ChainedTokenCredential(
        ManagedIdentityCredential(client_id=client_id) if client_id else ManagedIdentityCredential(),
        AzureCliCredential(),
    )
    client = AgentsClient(endpoint=endpoint, credential=cred)

    existing = {a.name: a.id for a in client.list_agents()}
    print(f"[seed] connected — {len(existing)} existing agents in project")

    results = []
    for s in specs:
        name = s.get("name", s["_dir"])
        instructions = s.get("_prompt", "")
        tool_names = s.get("tools", [])
        tool_defs = build_tool_defs(tool_names, agents_dir)
        tools = []
        for t in tool_defs:
            fn = t["function"]
            tools.append(FunctionToolDefinition(
                function=FunctionDefinition(
                    name=fn["name"],
                    description=fn.get("description", ""),
                    parameters=fn.get("parameters", {"type": "object", "properties": {}}),
                )
            ))

        model = (s.get("model") or "gpt-4o").replace("${AOAI_DEPLOYMENT_NAME}", deployment)

        try:
            if name in existing:
                agent = client.update_agent(
                    agent_id=existing[name], model=model, name=name,
                    description=s.get("description", ""), instructions=instructions, tools=tools,
                )
                action = "updated"
            else:
                agent = client.create_agent(
                    model=model, name=name,
                    description=s.get("description", ""), instructions=instructions, tools=tools,
                )
                action = "created"
        except Exception as e:  # noqa: BLE001
            print(f"  [ERROR] {name}: {e.__class__.__name__}: {e}")
            agent = None
            for a in client.list_agents():
                if a.name == name:
                    agent = a; break
            if agent is None:
                print(f"  [FAIL] {name}: could not recover"); continue
            action = "recovered"
        results.append((name, agent.id, action, model))
        print(f"  [{action}] {name} → {agent.id}  ({model})")

    print("\n┌─ Foundry agents ─────────────────────────────────────────┐")
    for n, i, a, mdl in results:
        print(f"│ [{a:>9}] {n:<28} {mdl:<14} {i}")
    print("└──────────────────────────────────────────────────────────┘")



if __name__ == "__main__":
    main()
