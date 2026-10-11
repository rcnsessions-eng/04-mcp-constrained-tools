import logging
import time
import uuid
from typing import Literal

import httpx
from app.authz.contracts import (
    AuthorizationInput,
    CanonicalAction,
    Envelope,
    PrincipalContext,
    RequestContext,
    ResourceContext,
    TenantContext,
    WorkloadContext,
)
from app.domain import Principal
from app.errors import ServiceError
from pydantic import BaseModel, ConfigDict, StrictBool

from learning_tools.contracts import AssessmentArguments, EvidenceArguments, SearchArguments
from learning_tools.repository import ToolRepository

audit = logging.getLogger("learning.tools.authorization")


class WriteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    allow: StrictBool
    reason_code: Literal["ACCESS_DENIED", "OWNER_AND_TENANT_MATCH"]
    policy_version: Literal["1.1.0"]


class WriteEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    result: WriteDecision


class PolicyClient:
    def __init__(self, url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.client = httpx.AsyncClient(
            base_url=url, timeout=0.5, trust_env=False, transport=transport
        )

    async def enforce(
        self, principal: Principal, action: CanonicalAction, resource: ResourceContext
    ) -> None:
        request_id = uuid.uuid4().hex
        context = AuthorizationInput(
            principal=PrincipalContext(id=principal.subject, tenant_id=principal.tenant_id),
            workload=WorkloadContext(),
            action=action,
            resource=resource,
            tenant=TenantContext(id=principal.tenant_id),
            request=RequestContext(id=request_id),
        )
        await self.enforce_context(context)

    async def enforce_context(self, context: AuthorizationInput) -> None:
        write = context.action in {"assessment.create", "evidence.record"}
        endpoint = "tools" if write else "authz"
        started = time.monotonic()
        try:
            async with self.client.stream(
                "POST",
                f"/v1/data/learning/{endpoint}/decision",
                json={"input": context.model_dump(exclude_none=True)},
            ) as response:
                response.raise_for_status()
                payload = bytearray()
                async for chunk in response.aiter_bytes():
                    payload.extend(chunk)
                    if len(payload) > 4096 or time.monotonic() - started > 2:
                        raise ValueError("Invalid policy response")
                decision = (
                    WriteEnvelope.model_validate_json(bytes(payload)).result
                    if write
                    else Envelope.model_validate_json(bytes(payload)).result
                )
                expected = (
                    "TENANT_APPROVED_CONTENT"
                    if context.action == "content.search"
                    else "OWNER_AND_TENANT_MATCH"
                )
                if decision.reason_code != (expected if decision.allow else "ACCESS_DENIED"):
                    raise ValueError("Invalid policy response")
        except (httpx.HTTPError, ValueError):
            raise ServiceError(503, "policy_unavailable", "Authorization unavailable") from None
        audit.info(
            "action=%s request_id=%s reason=%s policy=%s",
            context.action,
            context.request.id,
            decision.reason_code,
            decision.policy_version,
        )
        if not decision.allow:
            raise ServiceError(403, "access_denied", "Access denied")

    async def close(self) -> None:
        await self.client.aclose()


class LearningToolsService:
    def __init__(self, repository: ToolRepository, policy: PolicyClient) -> None:
        self.repository = repository
        self.policy = policy

    async def authorize(self, principal: Principal, action: CanonicalAction) -> None:
        learner = self.repository.get_learner_metadata(principal.tenant_id, principal.subject)
        if learner is None:
            raise ServiceError(404, "not_found", "Resource not found")
        collection = action == "content.search"
        resource = ResourceContext(
            id=("approved-" + learner.tenant_id if collection else "progress-" + learner.id),
            type="approved-content-collection" if collection else "learner-progress",
            tenant_id=learner.tenant_id,
            owner_id=None if collection else learner.id,
        )
        await self.policy.enforce(principal, action, resource)

    async def search(self, principal: Principal, args: SearchArguments) -> dict[str, object]:
        await self.authorize(principal, "content.search")
        records = self.repository.read_content_for(principal, 20)
        query = args.query.casefold().strip()
        matches = [
            {"id": record.id, "course_id": record.course_id}
            for record in records
            if query in (record.title + " " + record.body).casefold()
        ]
        return {"items": matches[: args.limit]}

    async def progress(self, principal: Principal, learner_id: str) -> dict[str, object]:
        if learner_id != principal.subject:
            raise ServiceError(404, "not_found", "Resource not found")
        await self.authorize(principal, "progress.read")
        record = self.repository.read_progress_for(principal, learner_id)
        return {"course_id": record.course_id, "completion_percent": record.completion_percent}

    async def create_assessment(
        self, principal: Principal, args: AssessmentArguments, deadline: float
    ) -> dict[str, object]:
        await self.authorize(principal, "assessment.create")
        return self.repository.write_for(
            principal,
            "assessment.create",
            args.idempotency_key,
            {"course_id": args.course_id, "question_count": args.question_count},
            deadline,
        )

    async def record_evidence(
        self, principal: Principal, args: EvidenceArguments, deadline: float
    ) -> dict[str, object]:
        await self.authorize(principal, "evidence.record")
        return self.repository.write_for(
            principal,
            "evidence.record",
            args.idempotency_key,
            {"course_id": args.course_id, "kind": args.kind},
            deadline,
        )
