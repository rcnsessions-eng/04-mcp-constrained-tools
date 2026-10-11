import os
import sys
from pathlib import Path

if os.getenv("LEARNING_LOCAL_DEPENDENCIES") == "1":
    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root / "01-foundation-learning-api/code"))
    import app

    app.__path__.extend(
        [
            str(root / "02-opa-authorization/code/app"),
            str(root / "03-resource-tenant-isolation/code/app"),
        ]
    )
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp"))
