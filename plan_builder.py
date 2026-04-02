def make_task(task_no: int, target: str, purpose: str, depends_on=None):
    task = {
        "task_id": f"TASK-{task_no:03d}",
        "target": target,
        "purpose": purpose
    }
    if depends_on:
        task["depends_on"] = depends_on
    return task


def build_plan(intent: str):
    plan = []

    if intent == "status_question":
        plan.append(make_task(1, "L3:knowledge_retrieval (Cross-Cutting)", "Retrieve project context and history"))
        plan.append(make_task(2, "L2:COMMUNICATION_COLLABORATION", "Formulate a status answer", ["TASK-001"]))
        plan.append(make_task(3, "L3:evaluation (Cross-Cutting)", "Check answer quality before delivery", ["TASK-002"]))
        plan.append(make_task(4, "L2:COMMUNICATION_COLLABORATION", "Send the final response", ["TASK-003"]))

    elif intent == "feature_request":
        plan.append(make_task(1, "L2:TRACKING_EXECUTION", "Extract action items from feature request"))
        plan.append(make_task(2, "L2:TRACKING_EXECUTION", "Extract risks from scope change"))
        plan.append(make_task(3, "L2:TRACKING_EXECUTION", "Extract decision needed"))
        plan.append(make_task(4, "L3:knowledge_retrieval (Cross-Cutting)", "Retrieve project context and timeline"))
        plan.append(make_task(5, "L2:COMMUNICATION_COLLABORATION", "Formulate gap-aware response",
                              ["TASK-001", "TASK-002", "TASK-003", "TASK-004"]))
        plan.append(make_task(6, "L3:evaluation (Cross-Cutting)", "Evaluate response before sending", ["TASK-005"]))
        plan.append(make_task(7, "L2:COMMUNICATION_COLLABORATION", "Send response to sender", ["TASK-006"]))

    elif intent == "decision_request":
        plan.append(make_task(1, "L3:knowledge_retrieval (Cross-Cutting)", "Retrieve project context"))
        plan.append(make_task(2, "L2:COMMUNICATION_COLLABORATION", "Prepare recommendation answer", ["TASK-001"]))
        plan.append(make_task(3, "L3:evaluation (Cross-Cutting)", "Validate tone and completeness", ["TASK-002"]))
        plan.append(make_task(4, "L2:COMMUNICATION_COLLABORATION", "Send response", ["TASK-003"]))

    elif intent == "meeting_transcript":
        plan.append(make_task(1, "L2:TRACKING_EXECUTION", "Extract action items from meeting transcript"))
        plan.append(make_task(2, "L2:TRACKING_EXECUTION", "Extract risks from meeting transcript"))
        plan.append(make_task(3, "L2:TRACKING_EXECUTION", "Extract issues from meeting transcript"))
        plan.append(make_task(4, "L2:TRACKING_EXECUTION", "Extract decisions from meeting transcript"))
        plan.append(make_task(5, "L2:COMMUNICATION_COLLABORATION", "Prepare meeting summary"))

    elif intent == "urgent_escalation":
        plan.append(make_task(1, "L2:TRACKING_EXECUTION", "Extract issue(s) from urgent message"))
        plan.append(make_task(2, "L2:TRACKING_EXECUTION", "Extract risk(s) from urgent message"))
        plan.append(make_task(3, "L3:knowledge_retrieval (Cross-Cutting)", "Retrieve current project status"))
        plan.append(make_task(4, "L2:COMMUNICATION_COLLABORATION", "Formulate escalation response",
                              ["TASK-001", "TASK-002", "TASK-003"]))
        plan.append(make_task(5, "L3:evaluation (Cross-Cutting)", "Check response before sending", ["TASK-004"]))
        plan.append(make_task(6, "L2:COMMUNICATION_COLLABORATION", "Send escalation response", ["TASK-005"]))

    else:
        plan.append(make_task(1, "L3:knowledge_retrieval (Cross-Cutting)", "Look up project context"))
        plan.append(make_task(2, "L2:COMMUNICATION_COLLABORATION", "Ask a clarifying question", ["TASK-001"]))
        plan.append(make_task(3, "L3:evaluation (Cross-Cutting)", "Check clarity of question", ["TASK-002"]))
        plan.append(make_task(4, "L2:COMMUNICATION_COLLABORATION", "Send clarification request", ["TASK-003"]))

    return plan