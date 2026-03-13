"""Utility for syncing instruction content to an MCP server's knowledge graph."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def sync_instructions_to_mcp(mcp_base_url: str, agent_id: str, content: str) -> None:
    """Call MCP remember tool with MD content via JSON-RPC.

    Sends the full instruction content to the MCP server so the knowledge graph
    contains the same rules used in the MD condition. This ensures both evaluation
    conditions operate on identical rules.

    Args:
        mcp_base_url: Base URL of the MCP server (e.g. 'https://mcp.rippletide.com').
        agent_id: Agent identifier used to scope the knowledge graph.
        content: Full markdown content to inject into the graph via remember tool.
    """
    url = f'{mcp_base_url.rstrip("/")}/mcp?agentId={agent_id}'

    def _post(payload: dict) -> dict:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'MCP sync error {exc.code}: {exc.read().decode()[:200]}') from exc

    # Step 1: initialize session
    _post({
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'initialize',
        'params': {
            'protocolVersion': '2024-11-05',
            'capabilities': {},
            'clientInfo': {'name': 'harness', 'version': '1.0'},
        },
    })

    # Step 2: call remember tool with MD content
    result = _post({
        'jsonrpc': '2.0',
        'id': 2,
        'method': 'tools/call',
        'params': {
            'name': 'remember',
            'arguments': {'content': content},
        },
    })

    if 'error' in result:
        raise RuntimeError(f"MCP remember failed: {result['error']}")

    print(f'  MCP sync complete (agentId={agent_id})')
