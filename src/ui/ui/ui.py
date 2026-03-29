"""Reflex app entrypoint."""

from pathlib import Path

from dotenv import load_dotenv
import reflex as rx


load_dotenv(Path(__file__).resolve().parents[3] / ".env")

app = rx.App(
    stylesheets=["/styles.css"],
    theme=rx.theme(
        appearance="light",
        accent_color="teal",
        gray_color="sand",
        radius="large",
        font_family="Space Grotesk",
    ),
)

# Import pages after app creation so @rx.page decorators register with this app.
from .pages.backtest import backtest  # noqa: F401,E402
from .pages.backtest_result import backtest_result_page  # noqa: F401,E402
from .pages.index import index  # noqa: F401,E402
