import hashlib
import json
import time
import uuid
from typing import Literal

from app.domain import Principal
from app.errors import ServiceError
from app.isolation.repository import SQLiteLearningRepository


class ToolRepository(SQLiteLearningRepository):
    def __init__(self) -> None:
        super().__init__()
        self.connection.execute("""
            CREATE TABLE tool_writes(tenant_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                action TEXT NOT NULL, key TEXT NOT NULL, intent TEXT NOT NULL,
                result TEXT NOT NULL, PRIMARY KEY(tenant_id,owner_id,action,key),
                FOREIGN KEY(tenant_id,owner_id) REFERENCES learners(tenant_id,id))
        """)

    def write_for(
        self,
        principal: Principal,
        action: Literal["assessment.create", "evidence.record"],
        key: str,
        intent: dict[str, str | int],
        deadline: float,
    ) -> dict[str, object]:
        digest = hashlib.sha256(json.dumps(intent, sort_keys=True).encode()).hexdigest()
        with self.transaction() as connection:
            self.require_current_member(connection, principal)
            course = connection.execute(
                "SELECT 1 FROM progress WHERE tenant_id=? AND learner_id=? AND course_id=?",
                (principal.tenant_id, principal.subject, intent["course_id"]),
            ).fetchone()
            if course is None:
                raise ServiceError(404, "not_found", "Resource not found")
            previous = connection.execute(
                "SELECT intent,result FROM tool_writes "
                "WHERE tenant_id=? AND owner_id=? AND action=? AND key=?",
                (principal.tenant_id, principal.subject, action, key),
            ).fetchone()
            if previous:
                if previous["intent"] != digest:
                    raise ServiceError(409, "idempotency_conflict", "Conflicting retry")
                result: dict[str, object] = json.loads(previous["result"])
            else:
                count = connection.execute(
                    "SELECT COUNT(*) FROM tool_writes WHERE tenant_id=? AND owner_id=?",
                    (principal.tenant_id, principal.subject),
                ).fetchone()[0]
                if count >= 100:
                    raise ServiceError(429, "write_budget_exceeded", "Write budget exceeded")
                record_id = uuid.uuid4().hex
                result = {"id": record_id, "status": "created"}
                if action == "assessment.create":
                    result["course_id"] = intent["course_id"]
                    prompts = (
                        "Synthetic practice: name one networking protocol.",
                        "Synthetic practice: describe a tenant boundary.",
                        "Synthetic practice: explain default-deny authorization.",
                    )
                    result["questions"] = list(prompts[: int(intent["question_count"])])
                else:
                    connection.execute(
                        "INSERT INTO evidence VALUES(?,?,?,?)",
                        (principal.tenant_id, principal.subject, record_id, intent["kind"]),
                    )
                connection.execute(
                    "INSERT INTO tool_writes VALUES(?,?,?,?,?,?)",
                    (
                        principal.tenant_id,
                        principal.subject,
                        action,
                        key,
                        digest,
                        json.dumps(result),
                    ),
                )
            if time.monotonic() >= deadline:
                raise ServiceError(504, "service_timeout", "Service deadline exceeded")
            return result

    def write_count(self) -> int:
        with self.lock:
            return int(
                self.connection.execute("SELECT COUNT(*) FROM tool_writes").fetchone()[0]
            )
