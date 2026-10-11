"""Local diagnostic launcher; Compose uses learning_tools directly instead."""

import sys
from importlib import import_module
from pathlib import Path

root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root / "01-foundation-learning-api/code"))
app = import_module("app")

app.__path__.extend(
    [
        str(root / "02-opa-authorization/code/app"),
        str(root / "03-resource-tenant-isolation/code/app"),
    ]
)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))

if __name__ == "__main__":
    import_module("learning_tools.__main__").main()
