"""Explicit local demo setup and API entrypoints; no migrations in API startup."""

from argparse import ArgumentParser

from .runtime import (
    DemoAuthenticationProvider,
    api_settings,
    bootstrap,
    break_schema,
    restore_schema,
)


def main(arguments: list[str] | None = None) -> None:
    """Run the selected demo action against the dedicated database only."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("bootstrap", "break-schema", "restore-schema", "api")
    )
    parser.add_argument("--database-port", type=int, default=55432)
    parser.add_argument("--api-port", type=int, default=8001)
    options = parser.parse_args(arguments)
    if options.command == "api":
        import uvicorn
        from trader_console_api import create_app

        uvicorn.run(
            create_app(
                api_settings(options.database_port),
                authentication_provider=DemoAuthenticationProvider(),
            ),
            host="127.0.0.1",
            port=options.api_port,
        )
        return
    action = {
        "bootstrap": bootstrap,
        "break-schema": break_schema,
        "restore-schema": restore_schema,
    }[options.command]
    action(options.database_port)
    print(
        f"Console demo: {options.command} complete (database port {options.database_port})."
    )


if __name__ == "__main__":
    main()
