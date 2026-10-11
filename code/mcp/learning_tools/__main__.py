import asyncio
import logging
import os

from learning_tools.repository import ToolRepository
from learning_tools.server import configured_principal, create_server
from learning_tools.services import LearningToolsService, PolicyClient


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    principal = configured_principal()
    repository = ToolRepository()
    policy = PolicyClient(os.getenv("LEARNING_OPA_URL", "http://opa:8181"))
    server = create_server(LearningToolsService(repository, policy), principal)

    async def run() -> None:
        try:
            await server.run_stdio_async()
        finally:
            await policy.close()
            repository.close()

    asyncio.run(run())


if __name__ == "__main__":
    main()
