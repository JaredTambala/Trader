"""Reproducible OpenAPI export without environment credentials or app startup."""

from argparse import ArgumentParser
import json
from pathlib import Path

from pydantic import SecretStr

from .application import create_app
from .configuration import ConsoleApiSettings
from .contracts import BrokerAccountBinding, ConsoleEnvironment, ConsoleScope


def render_openapi() -> str:
    """Render the actual application's schema without opening a connection pool.

    Fixed settings avoid dependence on developer credentials or environment.
    The app factory registers routes; its database-owning lifespan is not run.
    """
    settings = ConsoleApiSettings(
        database_url=SecretStr("postgresql://unused.invalid/openapi"),
        scope=ConsoleScope(
            scope_id="schema-export",
            display_name="Schema export",
            environment=ConsoleEnvironment.SYNTHETIC_DEMO,
            broker_account_binding=BrokerAccountBinding.NOT_APPLICABLE,
        ),
    )
    return json.dumps(create_app(settings).openapi(), indent=2, sort_keys=True) + "\n"


def main(arguments: list[str] | None = None) -> None:
    """Write the generated artifact, or exit nonzero if its checked copy drifts."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args(arguments)
    rendered = render_openapi()
    if options.check:
        if (
            not options.output.is_file()
            or options.output.read_text(encoding="utf-8") != rendered
        ):
            parser.exit(1, f"OpenAPI artifact is missing or stale: {options.output}\n")
        return
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
