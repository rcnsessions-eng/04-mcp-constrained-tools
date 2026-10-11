# Constrained Learning MCP

Status: container acceptance verified on 2026-10-11 after Docker recovered. Checks passed 77 Python tests, 21 Rego tests, mutation, lint/format/mypy; actual private-OPA stdio discovery and 11 calls passed. Runtime Python 3.12.11, UID 10001. The identity-delegation workshop is now active. MCP is an integration protocol, not an authorization grant.

This project owns only the constrained-tools workshop. It depends on the resource and tenant isolation runtime/check images, which depend on the foundation and OPA authorization workshops. Earlier application sources are not copied here. The user approved adding prerequisite assessment/evidence business services in this milestone because preceding milestones expose no allowed write services.

## Run With Compose

From this `code` directory, with Docker Desktop responding:

```bash
bash scripts/check.sh
docker compose run --rm -T --no-deps mcp
```

The gate builds upstream dependencies and both constrained-tools images, runs 77 combined Python tests, 21 Rego tests, the inherited tenant-predicate mutation check, lint/format/type checks, waits for private OPA health, then runs the official MCP client and server as real stdio subprocesses inside the runtime container. These container steps are configured, **not yet executed successfully** for this workshop.

`bash scripts/run.sh` builds dependencies and starts the private OPA service before launching a stdio server. There is no HTTP MCP listener or published port. Use an MCP client rather than typing ordinary text into stdio. Open this `code` directory as the VS Code workspace to use [.vscode/mcp.json](.vscode/mcp.json); OPA and the built image must already be available.

Compose defaults use the existing synthetic `demo-learner-red` credential. To use another configured synthetic principal, set `LEARNING_MCP_CREDENTIAL` before starting a separate stdio process. Custom credential maps use the foundation `LEARNING_DEMO_CREDENTIALS_JSON` contract. Missing/unknown credentials fail startup without echoing values. Do not store real credentials in client configuration; [.env.example](.env.example) contains demo values only.

```bash
docker compose logs --tail=50 opa
docker compose ps
docker compose down
```

Cleanup affects only `zero-trust-constrained-tools`; it does not delete upstream projects or their volumes.

## Tool Contracts

Every call has one `args` object. Its typed runtime model forbids extra fields and coercion. No tool accepts tenant, role, credential, workload or principal identity. `learner_id` is a target resource identifier, not proof of identity.

| Tool | Mode | Bounded Arguments | Output |
| --- | --- | --- | --- |
| `content.search` | Read only | Query 1-128 characters; collection only `approved`; limit 1-10 | Matching content/course references only; no title/body/tenant |
| `progress.read` | Read only | Target learner ID 1-64 safe characters | Own course/completion only |
| `assessment.create` | Side effect | Own course, 1-3 synthetic questions, idempotency key | Assessment receipt and fixed synthetic practice prompts |
| `evidence.record` | Side effect | Own course, kind `practice_attempted` or `content_read`, idempotency key | Receipt only; no evidence value or owner |

Example: `{"args":{"query":"network","collection":"approved","limit":5}}`.

Schemas and annotations come from the official MCP 2.3.0 SDK. Input models are in [mcp/learning_tools/contracts.py](mcp/learning_tools/contracts.py); mechanically generated discovery schemas are under ignored `artifacts/tool-schemas.json`. Generate them with the built checks image:

```bash
docker compose --profile tools run --rm --no-deps -v "$PWD:/out" -w /out checks python /mcp-scripts/export_schemas.py
```

This generation command is configured but not container-verified. The equivalent local exporter executed and all four strict schemas were checked.

## Security Boundaries

- [mcp/learning_tools/server.py](mcp/learning_tools/server.py) attaches configured demo identity in trusted pre-validation middleware. Handlers are thin and use the business service; model arguments and request metadata cannot set identity.
- [mcp/learning_tools/services.py](mcp/learning_tools/services.py) performs asynchronous, non-cached, strict OPA decisions. Reads use the unchanged OPA authorization policy `1.0.0`; writes use this workshop's policy `1.1.0`. Malformed, oversized, wrong-version, wrong-reason and unavailable decisions fail closed.
- The narrow write policy authorizes the authenticated learner's progress aggregate. [mcp/learning_tools/repository.py](mcp/learning_tools/repository.py) independently checks active membership and the requested course in that learner's scoped progress, inside the mutation transaction.
- Idempotency binds tenant, actor, action, key and intent hash. Same intent returns the original receipt; conflicting intent fails. Replays must still pass current authorization/membership. Evidence and its receipt commit together.
- Calls have a 2-second wall deadline, at most 100 calls per process, 30 calls/minute, two concurrent calls, 1,024-byte argument objects and 4,096-byte serialized application results. Search examines at most 20 approved fixture records. Writes are capped at 100 per actor in the repository. No automatic tool retry is performed.
- Policy I/O is cancellable async I/O, not a background write thread. Bounded synchronous SQLite work rechecks the deadline before commit and rolls back if expired. Arbitrary slow/blocking external services are not supported by this design.
- Unknown/malformed calls return fixed error codes. Service errors reveal no query, credential, learner record or policy response. Audit logs contain canonical actions, server-generated IDs, policy reasons/versions, success/failure and duration; not arguments or evidence payloads.

Annotations/descriptions are hints, not enforcement. There are no SQL, shell, filesystem or unrestricted URL tools, real learner data, or live exam questions.

## Verified Locally

Python 3.14.7/macOS ARM64 fallback, MCP 2.3.0, OPA 1.21.1 with official release SHA-256 verified:

- 77 Python tests: 8 new plus all 69 earlier regressions.
- 21 real Rego tests: 9 new plus the earlier 12; original policy still denies writes.
- Tenant-predicate removal mutation rejected; source policy unchanged.
- Ruff lint/format and strict mypy: six implementation files passed.
- Actual subprocess stdio discovery and 11 calls against loopback OPA passed, including all four tools, duplicate writes, foreign resources and conflicting retries.
- After stopping the temporary OPA server, real stdio read/write calls failed closed without protected output. Container child dependency-path parameters were checked locally; this is not a container execution claim.
- Output redaction/size, invalid/extra/oversized arguments, call/rate/concurrency caps, service timeout with zero mutations, revocation during authorization and actor-bound retries passed.
- Compose YAML, shell syntax and the OPA health expression passed locally.

Exact executed commands and the Docker blocker are in [../../docs/security-test-report.md](../../docs/security-test-report.md).

## Limits And Next Gate

SQLite, idempotency records and budgets are volatile and process-local. A new stdio process resets state; this is not durable evidence storage, globally coordinated rate limiting, or distributed idempotency. Demo credential resolution and fixed `learning-api` workload metadata are not cryptographic identity, OAuth, delegation or mTLS. The identity-delegation and Istio workload-security workshops own those controls. No production readiness, hosted CI, scans, SBOM or signing claim is made.

Recover Docker Desktop, then run `bash scripts/check.sh`. Only after its image/runtime/protocol gate passes should the constrained-tools workshop be marked complete and the identity-delegation workshop begin. This work did not restart Docker, prune resources, change Kubernetes contexts, initialize Git, or touch previous workshops/book sources.