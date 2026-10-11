package learning.tools_test

import rego.v1

write_input := {
    "schema_version": "1.0",
    "principal": {"id": "learner-red-1", "tenant_id": "tenant-red", "type": "human"},
    "workload": {"id": "learning-api"},
    "action": "evidence.record",
    "resource": {"id": "progress-learner-red-1", "type": "learner-progress",
        "tenant_id": "tenant-red", "owner_id": "learner-red-1"},
    "tenant": {"id": "tenant-red"}, "request": {"id": "test-04"},
}

test_evidence_allowed if {
    decision := data.learning.tools.decision with input as write_input
    decision.allow
    decision.policy_version == "1.1.0"
}

test_assessment_allowed if {
    data.learning.tools.allow with input as object.union(write_input, {"action": "assessment.create"})
}

test_prior_policy_still_denies_writes if {
    not data.learning.authz.allow with input as write_input
}

test_unknown_action_denied if {
    not data.learning.tools.allow with input as object.union(write_input, {"action": "shell.execute"})
}

test_wrong_owner_denied if {
    changed := object.union(write_input, {"resource": {"owner_id": "learner-red-2"}})
    not data.learning.tools.allow with input as changed
}

test_wrong_tenant_denied if {
    changed := object.union(write_input, {"resource": {"tenant_id": "tenant-blue"}})
    not data.learning.tools.allow with input as changed
}

test_missing_owner_denied if {
    resource := object.remove(write_input.resource, ["owner_id"])
    changed := object.union(object.remove(write_input, ["resource"]), {"resource": resource})
    not data.learning.tools.allow with input as changed
}

test_wrong_workload_denied if {
    changed := object.union(write_input, {"workload": {"id": "untrusted-agent"}})
    not data.learning.tools.allow with input as changed
}

test_wrong_resource_denied if {
    changed := object.union(write_input, {"resource": {"id": "progress-learner-blue-1"}})
    not data.learning.tools.allow with input as changed
}