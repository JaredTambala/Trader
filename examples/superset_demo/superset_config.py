"""Configuration for the local Superset trial, loaded only inside its image."""

import os

from sqlalchemy.engine import URL


SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = URL.create(
    "postgresql+psycopg2",
    username="superset_metadata",
    password=os.environ["SUPERSET_DEMO_METADATA_PASSWORD"],
    host="metadata",
    database="superset_metadata",
).render_as_string(hide_password=False)
APP_NAME = "Trader · Synthetic demo"
ROW_LIMIT = 1000
SQLLAB_TIMEOUT = 30
# The pinned release's Talisman defaults support local HTTP and retain its CSP.
WTF_CSRF_ENABLED = True
FEATURE_FLAGS = {"ENABLE_TEMPLATE_PROCESSING": False}

# Superset's local MCP development mode delegates tool permissions to this
# existing demo administrator. This is intentionally local-only configuration,
# not a production authorization design.
MCP_DEV_USERNAME = "admin"
MCP_AUTH_ENABLED = False
SUPERSET_WEBSERVER_ADDRESS = "http://web:8088"
WEBDRIVER_BASEURL = "http://web:8088/"
WEBDRIVER_BASEURL_USER_FRIENDLY = "http://127.0.0.1:8088/"
