"""Start, check or stop the standalone local Superset evaluation."""

from argparse import ArgumentParser

from .database import bootstrap, check_access
from .runtime import DemoStack


def main(arguments: list[str] | None = None) -> None:
    """Run one explicit operation without accepting arbitrary project names or DSNs."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("up", "bootstrap", "fixtures", "candlestick", "check", "down", "restart", "status"))
    parser.add_argument("--database-port", type=int, default=25433)
    parser.add_argument("--ui-port", type=int, default=8088)
    parser.add_argument("--mcp-port", type=int, default=5008)
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--output", default="examples/superset_demo/.local/candlestick.html")
    options = parser.parse_args(arguments)
    stack = DemoStack(database_port=options.database_port, ui_port=options.ui_port, mcp_port=options.mcp_port)
    if options.command == "up":
        stack.up()
        print(f"Open http://127.0.0.1:{stack.ui_port}; username admin.")
        print("Dashboards: open ‘Trader real · MCP · bars’ for loaded Alpaca bars, ‘Trader demo · MCP · bars’ for the fixture, or ‘Trader backtest · MCP · single-run review’ for BacktestRunner evidence.")
        print(f"Password: ADMIN_PASSWORD in {stack.state_directory / 'credentials.json'} (keep private).")
    elif options.command == "bootstrap":
        bootstrap(stack)
    elif options.command == "fixtures":
        from .backtest_fixtures import fixture_summary, generate_fixtures

        counts = generate_fixtures(stack)
        print("Generated Trader backtest fixtures through BacktestRunner:")
        for name, total_runs in counts.items():
            print(f"- {name}: total_runs={total_runs}")
        print(f"Stored experiment rows: {len(fixture_summary(stack))}")
    elif options.command == "candlestick":
        from .candlestick import export

        path = export(stack, options.output, symbol=options.symbol, limit=options.limit)
        print(f"Exported generic Candlestick prototype: {path}")
    elif options.command == "check":
        from .smoke import check_preview

        check_access(stack)
        check_preview(stack)
    elif options.command == "down":
        stack.down()
    elif options.command == "restart":
        stack.restart()
    else:
        stack.compose("ps")


if __name__ == "__main__":
    main()
