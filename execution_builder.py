from agents import get_agent_output


def _response_text_from_dependencies(task: dict, outputs_by_task: dict) -> str:
    """
    Build evaluation input text from dependent task outputs.
    Most plans set evaluation to depend on the response-generation task.
    """
    for dep_task_id in task.get("depends_on", []):
        dep_output = outputs_by_task.get(dep_task_id, [])
        if dep_output:
            return "\n".join(dep_output)
    return ""


def build_execution(plan, message, intent):
    execution_blocks = []
    outputs_by_task = {}

    for task in plan:
        task_id = task["task_id"]
        target = task["target"]

        if target.startswith("L3:"):
            agent_name = target.split("L3:")[1].split(" ")[0].strip()
            response_text = ""
            if agent_name == "evaluation":
                response_text = _response_text_from_dependencies(task, outputs_by_task)

            output = get_agent_output(
                agent_name, message, intent, response_text=response_text
            )
            execution_blocks.append({
                "task_id": task_id,
                "target": target,
                "status": "COMPLETED",
                "output": output
            })
            outputs_by_task[task_id] = output
        else:
            purpose = task["purpose"].lower()
            # Keep routing simple and readable:
            # 1) extraction tasks first
            # 2) send/delivery before generic "response" so send steps map correctly
            # 3) meeting summary/minutes use meeting_attendance
            if "action items" in purpose:
                agent_name = "action_item_extraction"
            elif "risk" in purpose:
                agent_name = "risk_extraction"
            elif "issue" in purpose:
                agent_name = "issue_extraction"
            elif "decision" in purpose:
                agent_name = "decision_extraction"
            elif "send" in purpose or "delivery" in purpose:
                agent_name = "message_delivery"
            elif "meeting" in purpose or "transcript" in purpose or "minutes" in purpose:
                agent_name = "meeting_attendance"
            elif "summary" in purpose or "answer" in purpose or "response" in purpose:
                agent_name = "qna"
            else:
                agent_name = "qna"

            response_text = ""
            if agent_name == "evaluation":
                response_text = _response_text_from_dependencies(task, outputs_by_task)

            output = get_agent_output(
                agent_name, message, intent, response_text=response_text
            )
            execution_blocks.append({
                "task_id": task_id,
                "target": target,
                "l3_agent": agent_name,
                "status": "COMPLETED",
                "output": output
            })
            outputs_by_task[task_id] = output

    return execution_blocks
