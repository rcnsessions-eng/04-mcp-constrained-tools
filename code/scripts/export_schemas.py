import asyncio
import json
from pathlib import Path

from app.repositories.memory import demo_principals

from learning_tools.repository import ToolRepository
from learning_tools.server import create_server
from learning_tools.services import LearningToolsService, PolicyClient


async def export() -> None:
    repository = ToolRepository()
    policy = PolicyClient("http://opa:8181")
    try:
        tools = await create_server(
            LearningToolsService(repository, policy),
            demo_principals()["learner-red-1"],
        ).list_tools()
        destination = Path("artifacts/tool-schemas.json")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                [tool.model_dump(by_alias=True, exclude_none=True) for tool in tools], indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        print("Generated four official SDK tool schemas in artifacts/tool-schemas.json")
    finally:
        await policy.close()
        repository.close()


if __name__ == "__main__":
    asyncio.run(export())
