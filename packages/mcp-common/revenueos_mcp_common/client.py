"""MCP client used by orchestrator and agents. Propagates trace context in the envelope,
retries transient failures with backoff, and returns the structured result."""
import asyncio

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from .ratelimit import retry_with_backoff
from .telemetry import inject_traceparent


class McpClient:
    def __init__(self, url: str, token: str, timeout_s: float = 30.0):
        self.url = url.rstrip("/") + "/mcp"
        self.token = token
        self.timeout_s = timeout_s

    async def _call(self, tool: str, envelope: dict):
        transport = StreamableHttpTransport(self.url, headers={"Authorization": f"Bearer {self.token}"})
        async with Client(transport, timeout=self.timeout_s) as client:
            res = await client.call_tool(tool, envelope)
            return res.structured_content if res.structured_content is not None else res.data

    def call(self, tool: str, *, task_id: str, agent_id: str, args: dict, approval_id: str | None = None) -> dict:
        envelope = {"task_id": task_id, "agent_id": agent_id, "args": args,
                    "approval_id": approval_id, "traceparent": inject_traceparent()}
        return retry_with_backoff(lambda: asyncio.run(self._call(tool, envelope)), retry_on=(ConnectionError, TimeoutError))

    async def acall(self, tool: str, *, task_id: str, agent_id: str, args: dict, approval_id: str | None = None) -> dict:
        envelope = {"task_id": task_id, "agent_id": agent_id, "args": args,
                    "approval_id": approval_id, "traceparent": inject_traceparent()}
        return await self._call(tool, envelope)
