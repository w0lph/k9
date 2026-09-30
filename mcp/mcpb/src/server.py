"""Entry point for the Claude Desktop bundle: run the dog-geroscience-mcp server over stdio.

The host installs the dependencies declared in ../pyproject.toml with uv and executes this
file. The server downloads its prebuilt database on first run.
"""

import sys

from dog_geroscience_mcp.cli import main

if __name__ == "__main__":
    sys.exit(main(["serve"]))
