"""Deprecated entrypoint kept only to redirect users to injected wrappers."""

from __future__ import annotations


def main() -> None:
    raise SystemExit(
        "run_trader_service.py is no longer supported. "
        "Create your own wrapper script or use examples/run_injected_trader_service.py."
    )


if __name__ == "__main__":
    main()
