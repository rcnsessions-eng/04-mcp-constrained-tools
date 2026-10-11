import argparse
import asyncio
import os
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters


async def smoke(local: bool, container: bool) -> None:
    code = Path(__file__).resolve().parents[1]
    env = {"LEARNING_MCP_CREDENTIAL": "demo-learner-red"}
    if container:
        env["LEARNING_OPA_URL"] = os.getenv("LEARNING_OPA_URL", "http://opa:8181")
        env["PYTHONPATH"] = "/app/mcp:/app"
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "learning_tools"],
            env=env,
        )
    elif local:
        env["LEARNING_OPA_URL"] = os.environ["LEARNING_OPA_URL"]
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(code / "scripts/local_server.py")],
            env=env,
        )
    else:
        params = StdioServerParameters(
            command="docker",
            args=[
                "compose",
                "--project-directory",
                str(code),
                "run",
                "--rm",
                "-T",
                "--no-deps",
                "mcp",
            ],
            env=env,
        )
    async with Client(params, read_timeout_seconds=5) as client:
        assert {tool.name for tool in (await client.list_tools()).tools} == {
            "content.search",
            "progress.read",
            "assessment.create",
            "evidence.record",
        }
        for name, args in [
            ("content.search", {"query": "network"}),
            ("progress.read", {"learner_id": "learner-red-1"}),
            (
                "assessment.create",
                {"course_id": "course-red", "idempotency_key": "assessment-1"},
            ),
            (
                "evidence.record",
                {
                    "course_id": "course-red",
                    "kind": "content_read",
                    "idempotency_key": "evidence-1",
                },
            ),
        ]:
            result = await client.call_tool(name, {"args": args})
            assert not result.is_error, (name, result.content)
            assert result.structured_content is not None
            if name in {"assessment.create", "evidence.record"}:
                retry = await client.call_tool(name, {"args": args})
                assert (
                    not retry.is_error and result.structured_content == retry.structured_content
                )
        for name, args in [
            ("shell.execute", {}),
            ("content.search", {"query": "x" * 129}),
            ("progress.read", {"learner_id": "learner-blue-1"}),
            ("assessment.create", {"course_id": "course-blue", "idempotency_key": "foreign"}),
            (
                "evidence.record",
                {
                    "course_id": "course-red",
                    "kind": "practice_attempted",
                    "idempotency_key": "evidence-1",
                },
            ),
        ]:
            result = await client.call_tool(name, {"args": args})
            assert result.is_error, name
    print("Real stdio MCP smoke: discovery + 11 calls passed against actual OPA")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--local", action="store_true")
    mode.add_argument("--container", action="store_true")
    arguments = parser.parse_args()
    asyncio.run(smoke(arguments.local, arguments.container))
