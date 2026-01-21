"""Reflex app entrypoint."""

import reflex as rx

from .pages.index import index


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
