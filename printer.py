def print_orchestration_map(message, plan, execution_blocks):
    message_id = message.get("message_id", "UNKNOWN")
    sender_name = message.get("sender", {}).get("name", "Unknown")
    sender_role = message.get("sender", {}).get("role", "Unknown")
    project = message.get("project", "N/A")

    print("=" * 75)
    print("NION ORCHESTRATION MAP")
    print("=" * 75)
    print(f"Message: {message_id}")
    print(f"From:    {sender_name} ({sender_role})")
    print(f"Project: {project}")
    print()

    print("=" * 75)
    print("L1 PLAN")
    print("=" * 75)
    for task in plan:
        # ASCII arrows keep output compatible with default Windows terminals.
        print(f'[{task["task_id"]}] -> {task["target"]}')
        print(f'  Purpose: {task["purpose"]}')
        if "depends_on" in task:
            print(f'  Depends On: {", ".join(task["depends_on"])}')
        print()

    print("=" * 75)
    print("L2/L3 EXECUTION")
    print("=" * 75)
    print()
    for item in execution_blocks:
        print(f'[{item["task_id"]}] {item["target"]}')
        if "l3_agent" in item:
            print(f'  |--> [{item["task_id"]}-A] L3:{item["l3_agent"]}')
        print(f'  Status: {item["status"]}')
        print("  Output:")
        for line in item["output"]:
            print(f"    {line}")
        print()

    print("=" * 75)
