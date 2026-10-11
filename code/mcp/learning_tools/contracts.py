from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Identifier = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")]


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SearchArguments(Arguments):
    query: Annotated[str, Field(min_length=1, max_length=128)]
    collection: Literal["approved"] = "approved"
    limit: Annotated[int, Field(ge=1, le=10)] = 5


class ProgressArguments(Arguments):
    learner_id: Identifier


class AssessmentArguments(Arguments):
    course_id: Identifier
    question_count: Annotated[int, Field(ge=1, le=3)] = 1
    idempotency_key: Identifier


class EvidenceArguments(Arguments):
    course_id: Identifier
    kind: Literal["practice_attempted", "content_read"]
    idempotency_key: Identifier


SCHEMAS: dict[str, type[Arguments]] = {
    "content.search": SearchArguments,
    "progress.read": ProgressArguments,
    "assessment.create": AssessmentArguments,
    "evidence.record": EvidenceArguments,
}
