import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from commerceguard.store import Store


def test_real_stdio_protocol(tmp_path):
    path = str(tmp_path / "mcp.db")
    store = Store(path)
    store.seed()

    async def scenario():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "commerceguard.mcp_server"],
            env={**os.environ, "COMMERCE_OWNER": "alice", "COMMERCE_DB": path},
        )
        async with stdio_client(parameters) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            names = {tool.name for tool in (await session.list_tools()).tools}
            assert names == {"get_transaction", "request_refund", "triage_receipt"}
            result = await session.call_tool("get_transaction", {"transaction_id": "tx_demo"})
            assert not result.isError
            blocked = await session.call_tool("get_transaction", {"transaction_id": "tx_other"})
            assert blocked.isError
            arguments = {
                "request": {"transaction_id": "tx_demo", "amount_cents": 100, "idempotency_key": "mcp-test-1"}
            }
            result = await session.call_tool("request_refund", arguments)
            assert not result.isError
            replay = await session.call_tool("request_refund", arguments)
            assert json.loads(replay.content[0].text) == json.loads(result.content[0].text)

    asyncio.run(asyncio.wait_for(scenario(), timeout=30))
    with store.connect() as db:
        assert store.ledger(db, "tx_demo", "alice")["refunded_cents"] == 100
