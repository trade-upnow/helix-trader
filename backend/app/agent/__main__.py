"""python -m app.agent [cli|mcp] ..."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        print(
            "Usage:\n"
            "  python -m app.agent cli <command> [options]\n"
            "  python -m app.agent mcp\n"
            "  python -m app.agent <cli-command> [options]\n"
        )
        return 0

    mode = args[0]
    if mode == "mcp":
        from app.agent.mcp_server import run_stdio_server

        run_stdio_server()
        return 0

    if mode == "cli":
        from app.agent.cli import main as cli_main

        return cli_main(args[1:])

    # Default: treat as CLI command for convenience.
    from app.agent.cli import main as cli_main

    return cli_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
