"""Model Context Protocol (MCP) server for RepoSage repository tools.

Exposes inspection tools over the MCP standard protocol so external clients
or orchestrator agents interact across a formalized protocol boundary.
"""

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from reposage.tools.impl import grep_impl, list_symbols_impl, read_file_impl

# Initialize FastMCP application server
mcp = FastMCP("reposage-tools")


@mcp.tool()
async def read_file(
    snapshot_dir: str,
    path: str,
    start_line: int,
    end_line: int,
) -> dict[str, Any]:
    """Read a specific range of lines from a file in the repository."""
    return await read_file_impl(
        snapshot_root=Path(snapshot_dir),
        path=path,
        start_line=start_line,
        end_line=end_line,
    )


@mcp.tool()
async def grep(
    snapshot_dir: str,
    pattern: str,
    path_prefix: str = "",
    regex: bool = False,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search for literal string or regex patterns in repository files."""
    return await grep_impl(
        snapshot_root=Path(snapshot_dir),
        pattern=pattern,
        path_prefix=path_prefix,
        is_regex=regex,
        limit=limit,
    )


@mcp.tool()
async def list_symbols(
    snapshot_dir: str,
    path: str,
) -> list[dict[str, Any]]:
    """List all functions, classes, and methods defined in a Python file."""
    return await list_symbols_impl(
        snapshot_root=Path(snapshot_dir),
        path=path,
    )


if __name__ == "__main__":
    mcp.run()
