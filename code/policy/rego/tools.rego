package learning.tools

import rego.v1

default allow := false
default reason_code := "ACCESS_DENIED"

allow if {
    data.learning.authz.valid_context
    input.action in {"assessment.create", "evidence.record"}
    input.resource.type == "learner-progress"
    input.resource.id == concat("", ["progress-", input.principal.id])
    data.learning.authz.nonempty_string(input.resource.owner_id)
    input.principal.id == input.resource.owner_id
}

reason_code := "OWNER_AND_TENANT_MATCH" if allow

decision := {"allow": allow, "reason_code": reason_code, "policy_version": "1.1.0"}