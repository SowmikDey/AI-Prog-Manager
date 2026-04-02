import json
import sys

from intent_detector import detect_intent
from plan_builder import build_plan
from execution_builder import build_execution
from printer import print_orchestration_map
import db


def load_message_from_file(file_path: str) -> dict:
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    file_path = "input.json"

    try:
        message = load_message_from_file(file_path)
    except FileNotFoundError:
        print(f"[ERROR] File not found: {file_path}")
        return
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON: {e}")
        return

    print("\n[Nion] Detecting intent...")
    intent = detect_intent(message)
    print(f"[Nion] Intent: {intent}")
    print("[Nion] Building plan and executing agents...\n")

    # Ensure message exists in DB before any delivery logging.
    # (delivery_log has a foreign key to messages)
    try:
        db.log_message(message, intent)
    except Exception:
        # Keep orchestration running even if DB logging is unavailable.
        pass

    plan = build_plan(intent)
    execution_blocks = build_execution(plan, message, intent)
    print_orchestration_map(message, plan, execution_blocks)


if __name__ == "__main__":
    main()
