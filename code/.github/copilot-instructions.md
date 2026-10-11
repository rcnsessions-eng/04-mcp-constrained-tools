# PRD 04 Constrained MCP

- Use the official Python SDK, pinned MCP 2.3.0. Verify installed APIs before changes.
- References: https://github.com/modelcontextprotocol/python-sdk, https://py.sdk.modelcontextprotocol.io/client/, https://py.sdk.modelcontextprotocol.io/servers/.
- This folder owns only PRD 04. User-approved prerequisite assessment/evidence business services belong here, separate from the MCP adapter.
- Reuse PRDs 01-03 through explicit dependencies; do not copy their implementations.
- Stdio server identity comes from trusted process configuration, not tool arguments. It is a local demo, not OAuth or delegated identity.
- Expose only content.search, progress.read, assessment.create and evidence.record. Require runtime schemas, bounded results/output/time/calls, default-deny policy and idempotent writes.
- Use deterministic protocol/security tests, not a model, and record actual execution only.