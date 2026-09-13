"""Start the local MCP server with Run in PyCharm or ``python main.py``."""

from pathlib import Path
import sys


def main():
    project_root = Path(__file__).resolve().parent
    # Resolve this checkout even if PyCharm uses a different working directory.
    sys.path.insert(0, str(project_root / "src"))
    from h3m.mcp_server import main as run_server

    run_server(default_workspace=project_root)


if __name__ == "__main__":
    main()
