"""Reflex app entrypoint."""

from pathlib import Path

from dotenv import load_dotenv
import reflex as rx

from .pages.index import index


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
app.add_page(index)
