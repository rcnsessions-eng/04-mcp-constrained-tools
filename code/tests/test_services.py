import asyncio
import time

import httpx
import pytest
from app.errors import ServiceError
from app.repositories.memory import demo_principals

from learning_tools.contracts import AssessmentArguments, EvidenceArguments
from learning_tools.repository import ToolRepository
from learning_tools.services import LearningToolsService, PolicyClient


def setup_service(allow=True):
    def policy(request):
        return httpx.Response(
            200,
            json={
                "result": {
                    "allow": allow,
                    "reason_code": "OWNER_AND_TENANT_MATCH" if allow else "ACCESS_DENIED",
                    "policy_version": "1.1.0",
                }
            },
        )

    repository = ToolRepository()
    client = PolicyClient("http://opa:8181", httpx.MockTransport(policy))
    return repository, client, LearningToolsService(repository, client)


def test_duplicate_conflicting_and_foreign_writes():
    async def scenario():
        repository, client, service = setup_service()
        principal = demo_principals()["learner-red-1"]
        args = EvidenceArguments(
            course_id="course-red", kind="content_read", idempotency_key="one"
        )
        first = await service.record_evidence(principal, args, time.monotonic() + 2)
        assert first == await service.record_evidence(principal, args, time.monotonic() + 2)
        assert repository.evidence_count() == repository.write_count() == 1
        for change, code in [
            ("course-blue", "not_found"),
            ("course-red", "idempotency_conflict"),
        ]:
            other = args.model_copy(update={"course_id": change, "kind": "practice_attempted"})
            with pytest.raises(ServiceError) as error:
                await service.record_evidence(principal, other, time.monotonic() + 2)
            assert error.value.code == code
        assert repository.evidence_count() == repository.write_count() == 1
        await client.close()
        repository.close()

    asyncio.run(scenario())


def test_policy_failures_never_write():
    async def scenario():
        principal = demo_principals()["learner-red-1"]
        for response in [
            httpx.Response(503),
            httpx.Response(200, content=b"not-json"),
            httpx.Response(200, content=b"x" * 4097),
            httpx.Response(
                200,
                json={
                    "result": {
                        "allow": "true",
                        "reason_code": "OWNER_AND_TENANT_MATCH",
                        "policy_version": "1.1.0",
                    }
                },
            ),
            httpx.Response(
                200,
                json={
                    "result": {
                        "allow": True,
                        "reason_code": "ACCESS_DENIED",
                        "policy_version": "1.1.0",
                    }
                },
            ),
            httpx.Response(
                200,
                json={
                    "result": {
                        "allow": True,
                        "reason_code": "OWNER_AND_TENANT_MATCH",
                        "policy_version": "1.0.0",
                    }
                },
            ),
        ]:
            repository = ToolRepository()
            client = PolicyClient(
                "http://opa", httpx.MockTransport(lambda request, current=response: current)
            )
            service = LearningToolsService(repository, client)
            with pytest.raises(ServiceError) as error:
                await service.record_evidence(
                    principal,
                    EvidenceArguments(
                        course_id="course-red",
                        kind="content_read",
                        idempotency_key="one",
                    ),
                    time.monotonic() + 2,
                )
            assert error.value.code == "policy_unavailable"
            assert repository.evidence_count() == repository.write_count() == 0
            await client.close()
            repository.close()

    asyncio.run(scenario())


def test_revocation_and_actor_bound_retries():
    async def scenario():
        repository, client, service = setup_service()
        args = EvidenceArguments(
            course_id="course-red", kind="content_read", idempotency_key="same"
        )
        principals = demo_principals()
        first = await service.record_evidence(
            principals["learner-red-1"], args, time.monotonic() + 2
        )
        second = await service.record_evidence(
            principals["learner-red-2"], args, time.monotonic() + 2
        )
        assert first["id"] != second["id"] and repository.evidence_count() == 2
        await client.close()

        def revoke(request):
            repository.revoke_membership("tenant-red", "learner-red-1")
            return httpx.Response(
                200,
                json={
                    "result": {
                        "allow": True,
                        "reason_code": "OWNER_AND_TENANT_MATCH",
                        "policy_version": "1.1.0",
                    }
                },
            )

        client = PolicyClient("http://opa", httpx.MockTransport(revoke))
        service = LearningToolsService(repository, client)
        with pytest.raises(ServiceError) as error:
            await service.record_evidence(
                principals["learner-red-1"], args, time.monotonic() + 2
            )
        assert error.value.code == "not_found"
        assert repository.evidence_count() == repository.write_count() == 2
        await client.close()
        repository.close()

    asyncio.run(scenario())


def test_deny_and_deadline_leave_no_effect():
    async def scenario():
        principal = demo_principals()["learner-red-1"]
        for allow, code in [(False, "access_denied"), (True, "service_timeout")]:
            repository, client, service = setup_service(allow)
            args = AssessmentArguments(course_id="course-red", idempotency_key="one")
            with pytest.raises(ServiceError) as error:
                await service.create_assessment(principal, args, time.monotonic() - 1)
            assert error.value.code == code
            assert repository.write_count() == 0
            await client.close()
            repository.close()

    asyncio.run(scenario())
