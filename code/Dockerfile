FROM zero-trust-tenant-isolation-api:0.1.0 AS runtime
USER root
COPY 04-mcp-constrained-tools/code/requirements.lock /tmp/mcp-requirements.lock
RUN pip install --no-cache-dir -c /tmp/mcp-requirements.lock mcp==2.3.0
COPY 04-mcp-constrained-tools/code/mcp /app/mcp
COPY 04-mcp-constrained-tools/code/scripts/smoke.py /app/scripts/smoke.py
USER 10001:10001
ENV PYTHONPATH=/app/mcp:/app
CMD ["python", "-m", "learning_tools"]

FROM zero-trust-tenant-isolation-checks:0.1.0 AS checks
USER root
COPY 04-mcp-constrained-tools/code/requirements.lock /tmp/mcp-requirements.lock
RUN pip install --no-cache-dir -c /tmp/mcp-requirements.lock mcp==2.3.0
COPY 04-mcp-constrained-tools/code/mcp /app/mcp
COPY 04-mcp-constrained-tools/code/tests /mcp-tests
COPY 04-mcp-constrained-tools/code/scripts /mcp-scripts
COPY 04-mcp-constrained-tools/code/policy /tools-policy
COPY 04-mcp-constrained-tools/code/pyproject.toml /app/mcp/pyproject.toml
USER 10001:10001
ENV PYTHONPATH=/app/mcp:/app
WORKDIR /app/mcp
ENV MYPYPATH=/app
CMD ["sh", "-c", "ruff check learning_tools /mcp-tests && ruff format --check learning_tools /mcp-tests && mypy learning_tools && python -m pytest -p no:cacheprovider --import-mode=importlib /mcp-tests /isolation-tests /checks /app/tests && opa test /policy /tools-policy -v && python /scripts/mutation_check.py"]