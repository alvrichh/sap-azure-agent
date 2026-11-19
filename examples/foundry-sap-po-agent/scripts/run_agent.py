#!/usr/bin/env python3
"""Creates the Foundry prompt agent with the SAP MCP tool, then chats with it or runs the evaluation set.

  pip install azure-ai-projects azure-identity openai     # latest versions, as Microsoft Learn recommends
  az login
  python3 examples/foundry-sap-po-agent/scripts/run_agent.py --ask "Status of PO 4500000001?"
  python3 examples/foundry-sap-po-agent/scripts/run_agent.py --eval
  python3 examples/foundry-sap-po-agent/scripts/run_agent.py --eval --keep   # don't delete the agent version

Follows the Python sample in Microsoft Learn "Connect to Model Context Protocol servers" (Foundry Agent Service).
The MCP project connection (config: foundry.mcpConnectionName) must exist and pass the caller's Entra token
(user-entra-token) or an identity APIM accepts; see the README, phase 5.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from po_agent.evaluation import load_cases, score_case, tool_calls_from_output  # noqa: E402
from po_agent.tool_config import build_mcp_tool_kwargs, should_approve  # noqa: E402


def ask_human(tool_name, arguments):
    print(f"Approval requested for {tool_name} with {json.dumps(arguments, default=str)}")
    return input("Approve this SAP tool call? (y/N): ").strip().lower() == "y"


def run_turn(openai, conversation_id, text, settings, interactive):
    from openai.types.responses.response_input_param import McpApprovalResponse

    mcp = settings["mcp"]
    response = openai.responses.create(conversation=conversation_id, input=text)
    outputs = list(response.output)
    for _ in range(3):  # at most three approval rounds per question
        approvals = []
        for item in response.output:
            if item.type == "mcp_approval_request" and item.id:
                approve = should_approve(getattr(item, "name", ""), getattr(item, "arguments", None),
                                         mcp["tools"], mcp.get("readOnlyTools", []),
                                         ask_human if interactive else (lambda *_: False))
                approvals.append(McpApprovalResponse(type="mcp_approval_response", approve=approve,
                                                     approval_request_id=item.id))
        if not approvals:
            break
        response = openai.responses.create(conversation=conversation_id, input=approvals)
        outputs.extend(response.output)
    return response.output_text, outputs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", default=str(ROOT / "config/settings.json"))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ask")
    group.add_argument("--eval", action="store_true")
    parser.add_argument("--keep", action="store_true", help="keep the agent version after the run")
    args = parser.parse_args()

    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import MCPTool, PromptAgentDefinition
    from azure.identity import DefaultAzureCredential

    settings = json.loads(Path(args.settings).read_text())
    foundry = settings["foundry"]
    tool = MCPTool(**build_mcp_tool_kwargs(settings))
    instructions = (ROOT / "agent/instructions.md").read_text()

    with AIProjectClient(endpoint=foundry["projectEndpoint"], credential=DefaultAzureCredential(),
                         allow_preview=True) as project:
        agent = project.agents.create_version(
            agent_name=foundry["agentName"],
            definition=PromptAgentDefinition(model=foundry["modelDeployment"], instructions=instructions, tools=[tool]),
        )
        print(f"Agent {agent.name} version {agent.version}")
        failures_total = 0
        try:
            with project.get_openai_client(agent_name=agent.name) as openai:
                if args.ask:
                    conversation = openai.conversations.create()
                    answer, outputs = run_turn(openai, conversation.id, args.ask, settings, interactive=True)
                    print("Tool calls:", tool_calls_from_output(outputs))
                    print(answer)
                    openai.conversations.delete(conversation_id=conversation.id)
                else:
                    test = settings["test"]
                    for case in load_cases(ROOT / "eval/cases.json", test["purchaseOrder"], test["supplier"]):
                        conversation = openai.conversations.create()
                        answer, outputs = run_turn(openai, conversation.id, case["question"], settings, interactive=False)
                        failures = score_case(case, tool_calls_from_output(outputs), answer)
                        failures_total += bool(failures)
                        print(f"{'PASS' if not failures else 'FAIL'} {case['id']}: {'; '.join(failures)}")
                        openai.conversations.delete(conversation_id=conversation.id)
        finally:
            if not args.keep:
                project.agents.delete_version(agent_name=agent.name, agent_version=agent.version)
        return 1 if failures_total else 0


if __name__ == "__main__":
    sys.exit(main())
