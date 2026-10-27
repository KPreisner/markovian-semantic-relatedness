"""Write the API's OpenAPI schema without running the API (`python -m msr_api.openapi <file>`).
The BFF's types and Zod schemas are generated from it (`task web:typegen`), so the file is
committed and CI checks it's current."""

import json
import sys
from pathlib import Path

from msr_api.main import create_app

# The path the API is served under, behind web (compose.yaml: uvicorn --root-path).
ROOT_PATH = "/fastapi"


def schema() -> str:
    app = create_app()
    app.root_path = ROOT_PATH
    spec = app.openapi()
    spec["servers"] = [{"url": ROOT_PATH}]
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python -m msr_api.openapi <file>")
    Path(sys.argv[1]).write_text(schema(), encoding="utf-8")


if __name__ == "__main__":
    main()
