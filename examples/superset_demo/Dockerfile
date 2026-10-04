FROM apache/superset:6.1.0

USER root
RUN uv pip install --python /app/.venv/bin/python psycopg2-binary==2.9.13 \
    'apache-superset[fastmcp]==6.1.0'
COPY --chown=superset:superset superset_config.py initialize.py /app/trader_demo/
COPY --chown=superset:superset mcp_seed.py /app/trader_demo/
ENV SUPERSET_CONFIG_PATH=/app/trader_demo/superset_config.py
USER superset
