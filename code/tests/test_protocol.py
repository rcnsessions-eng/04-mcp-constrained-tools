import asyncio
import json

import httpx
from app.repositories.memory import demo_principals
from mcp import Client

from learning_tools.repository import ToolRepository
from learning_tools.server import Limits, create_server
from learning_tools.services import LearningToolsService, PolicyClient


def allow(request):
    context = json.loads(request.content)["input"]
    write = context["action"] in {"assessment.create", "evidence.record"}
    return httpx.Response(
        200,
        json={
            "result": {
                "allow": True,
                "reason_code": "TENANT_APPROVED_CONTENT"
                if context["action"] == "content.search"
                else "OWNER_AND_TENANT_MATCH",
                "policy_version": "1.1.0" if write else "1.0.0",
            }
        },
    )


def test_protocol_discovery_valid_calls_and_rejections():
    async def scenario():
        repository = ToolRepository()
        policy = PolicyClient("http://opa", httpx.MockTransport(allow))
        service = LearningToolsService(repository, policy)
        server = create_server(service, demo_principals()["learner-red-1"])
        async with Client(server) as client:
            tools = (await client.list_tools()).tools
            assert {tool.name for tool in tools} == {
                "content.search",
                "progress.read",
                "assessment.create",
                "evidence.record",
            }
            for tool in tools:
                assert tool.input_schema["properties"]["args"]
                assert "additionalProperties" in json.dumps(tool.input_schema)
            result = await client.call_tool("content.search", {"args": {"query": "network"}})
            assert not result.is_error
            assert result.structured_content is not None
            assert "tenant" not in str(result.structured_content)
            assert "body" not in str(result.structured_content)
            assert "title" not in str(result.structured_content)
            for name, args in [
                ("unknown.tool", {}),
                ("progress.read", {}),
                ("progress.read", {"args": {"learner_id": "learner-blue-1"}}),
                ("progress.read", {"args": {"learner_id": "learner-red-2"}}),
                ("content.search", {"args": {"query": "x" * 129}}),
                ("content.search", {"args": {"query": 42}}),
                ("content.search", {"args": {"query": "x", "limit": True}}),
                ("content.search", {"args": {"query": "x", "collection": "draft"}}),
                ("content.search", {"args": {"query": "x", "tenant_id": "tenant-blue"}}),
                ("content.search", {"args": {"query": "x"}, "principal": "admin"}),
                (
                    "assessment.create",
                    {"args": {"course_id": "course-blue", "idempotency_key": "one"}},
                ),
            ]:
                rejected = await client.call_tool(name, args)
                assert rejected.is_error, (name, args)
                assert "tenant-blue" not in str(rejected.content)
                assert "learner-blue-1" not in str(rejected.content)
                assert "x" * 129 not in str(rejected.content)
            for name, args in [
                ("assessment.create", {"course_id": "course-red", "idempotency_key": "one"}),
                (
                    "evidence.record",
                    {
                        "course_id": "course-red",
                        "kind": "content_read",
                        "idempotency_key": "one",
                    },
                ),
            ]:
                first = await client.call_tool(name, {"args": args})
                second = await client.call_tool(name, {"args": args})
                assert (
                    not first.is_error and first.structured_content == second.structured_content
                )
            assert repository.write_count() == 2 and repository.evidence_count() == 1
        await policy.close()
        repository.close()

    asyncio.run(scenario())


def test_protocol_timeout_cancels_before_side_effect():
    async def slow(request):
        await asyncio.Event().wait()
        return allow(request)

    async def scenario():
        repository = ToolRepository()
        policy = PolicyClient("http://opa", httpx.MockTransport(slow))
        service = LearningToolsService(repository, policy)
        server = create_server(
            service, demo_principals()["learner-red-1"], Limits(timeout=0.02)
        )
        async with Client(server) as client:
            result = await client.call_tool(
                "evidence.record",
                {
                    "args": {
                        "course_id": "course-red",
                        "kind": "content_read",
                        "idempotency_key": "one",
                    }
                },
            )
            assert result.is_error and "service_timeout" in str(result.content)
            assert repository.evidence_count() == repository.write_count() == 0
        await policy.close()
        repository.close()

    asyncio.run(scenario())


def test_limits_and_redaction(caplog):
    async def scenario():
        repository = ToolRepository()
        repository.connection.execute(
            "UPDATE content SET title=?,body=? WHERE tenant_id=? AND approved=1",
            ("SECRET-title", "SECRET-body", "tenant-red"),
        )
        policy = PolicyClient("http://opa", httpx.MockTransport(allow))
        service = LearningToolsService(repository, policy)
        principal = demo_principals()["learner-red-1"]
        server = create_server(service, principal)
        async with Client(server) as client:
            result = await client.call_tool("content.search", {"args": {"query": "SECRET"}})
            assert not result.is_error and result.structured_content["items"]
            assert "SECRET" not in result.model_dump_json()
            result = await client.call_tool(
                "progress.read", {"args": {"learner_id": principal.subject}}
            )
            assert not result.is_error
        for limits, expected in [
            (Limits(calls=1), "call_budget_exceeded"),
            (Limits(per_minute=1), "rate_limited"),
        ]:
            server = create_server(service, principal, limits)
            async with Client(server) as client:
                await client.call_tool("content.search", {"args": {"query": "SECRET"}})
                result = await client.call_tool("content.search", {"args": {"query": "SECRET"}})
                assert result.is_error and expected in str(result.content)

        async def oversized(principal, args):
            return {"items": ["SECRET" * 1000]}

        service.search = oversized
        async with Client(create_server(service, principal)) as client:
            result = await client.call_tool("content.search", {"args": {"query": "x"}})
            assert result.is_error and "output_limit_exceeded" in str(result.content)
            assert "SECRET" not in result.model_dump_json()
        assert "SECRET" not in caplog.text
        await policy.close()
        repository.close()

    asyncio.run(scenario())


def test_concurrency_is_bounded():
    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow(request):
            started.set()
            await release.wait()
            return allow(request)

        repository = ToolRepository()
        policy = PolicyClient("http://opa", httpx.MockTransport(slow))
        service = LearningToolsService(repository, policy)
        server = create_server(
            service, demo_principals()["learner-red-1"], Limits(concurrent=1)
        )
        async with Client(server) as client:
            first = asyncio.create_task(
                client.call_tool("content.search", {"args": {"query": "x"}})
            )
            await started.wait()
            second = await client.call_tool("content.search", {"args": {"query": "x"}})
            assert second.is_error and "busy" in str(second.content)
            release.set()
            assert not (await first).is_error
        await policy.close()
        repository.close()

    asyncio.run(scenario())
