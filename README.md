# AI Program Manager Agent

This project is a simplified orchestration engine for an AI Program Manager.
It reads one message from `input.json`, detects intent, builds an L1 plan, executes L2/L3 tasks, and prints the full orchestration map.

## 1) Prerequisites

- Python `3.10+` (recommended: `3.11` or `3.12`)
- Access to your Neon PostgreSQL database
- Groq API key (optional but recommended for richer outputs)

## 2) Dependency Installation

Create and activate a virtual environment, then install dependencies.

```bash
python -m venv .venv
```

Windows PowerShell:

```bash
.venv\Scripts\Activate.ps1
```

Install packages:

```bash
pip install python-dotenv psycopg2-binary groq
```

## 3) Configuration Setup (`config.py`)

Create a `config.py` file and paste the values shared in mail.
If `config.py` already exists, replace the placeholders with your mailed values.

```python
import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = "<PASTE_FROM_MAIL>"
USE_GROQ = bool(GROQ_API_KEY)
GROQ_MODEL = "llama-3.3-70b-versatile"
DATABASE_URL = "<PASTE_FROM_MAIL>"
```



## 4) Input File (`input.json`)

`input.json` is already created in this repo.
It already contains a test case; you can modify it for any message you want to test.

Expected shape:

```json
{
  "message_id": "MSG-101",
  "source": "slack",
  "sender": { "name": "John Doe", "role": "Engineering Manager" },
  "content": "What's the status of the authentication feature?",
  "project": "PRJ-BETA"
}
```

## 5) Run Process

Run:

```bash
python main.py
```

The console output prints:
- Message metadata
- `L1 PLAN`
- `L2/L3 EXECUTION`

## 6) Project Walkthrough (File-by-File)

### `main.py`
Top-level pipeline runner.

Functions:
- `load_message_from_file(file_path)`: reads JSON input.
- `main()`: executes full flow:
  1. load `input.json`
  2. detect intent
  3. log message in DB
  4. build L1 plan
  5. execute L2/L3 blocks
  6. print orchestration map

### `intent_detector.py`
Intent classification layer.

Functions:
- `call_groq(system_prompt, user_message)`: safe Groq call (returns empty string on failure).
- `is_valid_message(message)`: basic message sanity checks.
- `detect_intent(message)`: returns one label from:
  - `status_question`
  - `feature_request`
  - `decision_request`
  - `meeting_transcript`
  - `urgent_escalation`
  - `ambiguous_request`

### `plan_builder.py`
Creates the L1 plan.

Functions:
- `make_task(task_no, target, purpose, depends_on=None)`: task helper.
- `build_plan(intent)`: creates task list based on intent.

### `execution_builder.py`
Converts plan tasks into executable L3 calls.

Functions:
- `_response_text_from_dependencies(task, outputs_by_task)`: gathers prior output for evaluation.
- `build_execution(plan, message, intent)`: routes each task to proper agent and collects outputs.

### `printer.py`
Prints final map in terminal.

Function:
- `print_orchestration_map(message, plan, execution_blocks)`

### `db.py`
Database access layer (Neon PostgreSQL).

Functions:
- Connection:
  - `get_connection()`
- Read:
  - `get_project()`
  - `get_project_stakeholders()`
  - `get_open_action_items()`
  - `get_open_risks()`
  - `get_open_issues()`
  - `get_open_decisions()`
  - `get_sops()`
- Write:
  - `save_action_item()`
  - `save_risk()`
  - `save_issue()`
  - `save_decision()`
  - `save_sop()`
  - `log_message()`
  - `log_delivery()`
  - `next_id()`

### `agents.py`
All L3 agent implementations plus registry/dispatcher.

Helper/context functions:
- `call_groq()`
- `lines()`
- `_project_context()`
- `_items_context()`
- `_sops_context()`

Cross-cutting agents:
- `knowledge_retrieval()`
- `evaluation()`

Tracking/Execution agents:
- `action_item_extraction()`
- `action_item_validation()`
- `action_item_tracking()`
- `risk_extraction()`
- `risk_tracking()`
- `issue_extraction()`
- `issue_tracking()`
- `decision_extraction()`
- `decision_tracking()`

Communication/Collaboration agents:
- `qna()`
- `report_generation()`
- `message_delivery()`
- `meeting_attendance()`

Learning/Improvement agent:
- `instruction_led_learning()`

Dispatcher:
- `get_agent_output(agent, message, intent, response_text="")`

## 7) End-to-End Sequential Flow

1. `main.py` reads `input.json`.
2. `detect_intent()` decides message category.
3. Message gets logged via `db.log_message()`.
4. `build_plan(intent)` creates L1 tasks with dependencies.
5. `build_execution(...)` runs tasks:
   - Direct L3 tasks call cross-cutting agents.
   - L2 tasks are routed to the right L3 function via purpose keywords.
6. `evaluation()` receives previous response text and validates quality.
7. `print_orchestration_map()` prints full hierarchy and outputs.

## 8) Quick Troubleshooting

- `connection ... failed: Permission denied (10013)`:
  - local network/firewall or sandbox restriction blocking DB/API access.
- `DATABASE_URL is not set`:
  - check `config.py` and DB URL value.
- `ambiguous_request` unexpectedly:
  - verify `sender.name`, `sender.role`, `project`, and `content` are not null/unknown.

---

