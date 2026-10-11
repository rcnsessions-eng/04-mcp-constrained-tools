import asyncio
import json
import logging
import os
import time
import uuid
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.domain import Principal
from app.errors import ServiceError
from app.repositories.memory import demo_principals
from mcp.server import MCPServer
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, ValidationError

from learning_tools.contracts import (
    SCHEMAS,
    AssessmentArguments,
    EvidenceArguments,
    ProgressArguments,
    SearchArguments,
)
from learning_tools.services import LearningToolsService

trusted_context: ContextVar[tuple[Principal, float]] = ContextVar("learning_tool_identity")
audit = logging.getLogger("learning.tools.calls")


@dataclass(frozen=True)
class Limits:
    timeout: float = 2.0
    calls: int = 100
    per_minute: int = 30
    concurrent: int = 2
    output_bytes: int = 4096

    def __post_init__(self) -> None:
        if not (
            0.01 <= self.timeout <= 2.0
            and 1 <= self.calls <= 100
            and 1 <= self.per_minute <= 30
            and 1 <= self.concurrent <= 2
            and 256 <= self.output_bytes <= 4096
        ):
            raise ValueError("Invalid tool limits")


def error_result(code: str) -> CallToolResult:
    return CallToolResult(is_error=True, content=[TextContent(type="text", text=code)])


class TrustedToolBoundary:
    def __init__(self, principal: Principal, limits: Limits) -> None:
        self.principal = principal
        self.limits = limits
        self.used = 0
        self.active = 0
        self.recent: deque[float] = deque()

    async def __call__(
        self, ctx: ServerRequestContext[Any, Any], call_next: CallNext
    ) -> HandlerResult:
        if ctx.method != "tools/call":
            return await call_next(ctx)
        now = time.monotonic()
        if self.used >= self.limits.calls:
            return error_result("call_budget_exceeded")
        self.used += 1
        while self.recent and self.recent[0] <= now - 60:
            self.recent.popleft()
        if len(self.recent) >= self.limits.per_minute:
            return error_result("rate_limited")
        self.recent.append(now)
        if self.active >= self.limits.concurrent:
            return error_result("busy")
        params = ctx.params
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            return error_result("invalid_arguments")
        name = params["name"]
        if name not in SCHEMAS:
            return error_result("unknown_tool")
        arguments = params.get("arguments")
        if not isinstance(arguments, dict) or set(arguments) != {"args"}:
            return error_result("invalid_arguments")
        try:
            if len(json.dumps(arguments).encode()) > 1024:
                return error_result("invalid_arguments")
            SCHEMAS[name].model_validate(arguments["args"])
        except (ValueError, TypeError, ValidationError):
            return error_result("invalid_arguments")
        self.active += 1
        identity_token = trusted_context.set((self.principal, now + self.limits.timeout))
        result: HandlerResult
        try:
            async with asyncio.timeout(self.limits.timeout):
                result = await call_next(ctx)
            encoded = (
                result.model_dump_json()
                if isinstance(result, BaseModel)
                else json.dumps(result)
            )
            if len(encoded.encode()) > self.limits.output_bytes:
                result = error_result("output_limit_exceeded")
        except TimeoutError:
            result = error_result("service_timeout")
        except Exception:
            result = error_result("service_unavailable")
        finally:
            self.active -= 1
            trusted_context.reset(identity_token)
        audit.info(
            "action=%s request_id=%s error=%s duration_ms=%.2f",
            name,
            uuid.uuid4().hex,
            (
                result.is_error
                if isinstance(result, CallToolResult)
                else isinstance(result, dict)
                and result.get("isError", result.get("is_error", False))
            ),
            (time.monotonic() - now) * 1000,
        )
        return result


def configured_principal(settings: Settings | None = None) -> Principal:
    settings = settings or Settings.from_environment()
    credential = os.getenv("LEARNING_MCP_CREDENTIAL", "")
    subject = settings.demo_credentials.get(credential)
    if subject is None:
        raise ValueError("A configured local demo credential is required")
    return demo_principals()[subject]


def create_server(
    service: LearningToolsService, principal: Principal, limits: Limits | None = None
) -> MCPServer[None]:
    server: MCPServer[None] = MCPServer(
        "Constrained learning tools",
        version="0.1.0",
        log_level="WARNING",
        middleware=[TrustedToolBoundary(principal, limits or Limits())],
    )
    read = ToolAnnotations(read_only_hint=True, open_world_hint=False)
    write = ToolAnnotations(
        read_only_hint=False,
        open_world_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
    )

    @server.tool(name="content.search", annotations=read)
    async def content_search(args: SearchArguments) -> dict[str, object]:
        principal, _ = trusted_context.get()
        try:
            return await service.search(principal, args)
        except ServiceError as error:
            raise ToolError(error.code) from None
        except Exception:
            raise ToolError("service_unavailable") from None

    @server.tool(name="progress.read", annotations=read)
    async def progress_read(args: ProgressArguments) -> dict[str, object]:
        principal, _ = trusted_context.get()
        try:
            return await service.progress(principal, args.learner_id)
        except ServiceError as error:
            raise ToolError(error.code) from None
        except Exception:
            raise ToolError("service_unavailable") from None

    @server.tool(name="assessment.create", annotations=write)
    async def assessment_create(args: AssessmentArguments) -> dict[str, object]:
        principal, deadline = trusted_context.get()
        try:
            return await service.create_assessment(principal, args, deadline)
        except ServiceError as error:
            raise ToolError(error.code) from None
        except Exception:
            raise ToolError("service_unavailable") from None

    @server.tool(name="evidence.record", annotations=write)
    async def evidence_record(args: EvidenceArguments) -> dict[str, object]:
        principal, deadline = trusted_context.get()
        try:
            return await service.record_evidence(principal, args, deadline)
        except ServiceError as error:
            raise ToolError(error.code) from None
        except Exception:
            raise ToolError("service_unavailable") from None

    return server
