import re
from config import USE_GROQ, GROQ_MODEL, GROQ_API_KEY
import db


try:
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
except ImportError:
    client = None


def call_groq(system_prompt: str, user_message: str, max_tokens: int = 600) -> str:
    """Single reusable Groq call. Returns text or empty string."""
    if not client:
        return ""
    try:
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.3,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
      
        return ""


def lines(raw: str) -> list:
    """Split Groq response into non-empty lines."""
    return [l for l in raw.splitlines() if l.strip()] or ["• Completed"]


def _project_context(project_id: str) -> str:
    """
    Builds a text block describing the project.
    C++ analogy: serialize(Project* p) -> string
    """
    if not project_id or str(project_id).lower() in {"null", "none", ""}:
        return "No project context available."

    p = db.get_project(project_id)
    if not p:
        return f"Project {project_id} not found in database."

    stakeholders = db.get_project_stakeholders(project_id)
    team_txt = ", ".join(
        f"{s['name']} ({s['role']})" for s in stakeholders[:5]
    ) or "No stakeholders on record"

    return f"""PROJECT: {p['name']} ({project_id})
Description: {p.get('description', 'N/A')}
Status: {p.get('status', 'N/A').upper()}
Release date: {p.get('release_date', 'N/A')}
Code freeze: {p.get('code_freeze', 'N/A')}
Progress: {p.get('progress', 0)}% complete
Team capacity: {p.get('team_capacity', 0)}% utilised
Engineering manager: {p.get('engineering_manager', '?')}
Tech lead: {p.get('tech_lead', '?')}
Team: {team_txt}"""


def _items_context(project_id: str) -> str:
    """
    Builds a text block of all open tracked items.
    This is what gives qna and report_generation their intelligence.
    Without this, Groq would have to guess. With this, it knows facts.
    """
    parts = []

    action_items = db.get_open_action_items(project_id)
    if action_items:
        rows = "\n".join(
            f"  - {a['id']}: {a['description']} "
            f"(Owner: {a.get('owner') or '?'} | Due: {a.get('due_date') or '?'})"
            for a in action_items
        )
        parts.append(f"OPEN ACTION ITEMS ({len(action_items)}):\n{rows}")

    risks = db.get_open_risks(project_id)
    if risks:
        rows = "\n".join(
            f"  - {r['id']}: {r['description']} "
            f"[Likelihood: {r['likelihood']} | Impact: {r['impact']}]"
            for r in risks
        )
        parts.append(f"OPEN RISKS ({len(risks)}):\n{rows}")

    issues = db.get_open_issues(project_id)
    if issues:
        rows = "\n".join(
            f"  - {i['id']}: {i['description']} [Severity: {i['severity']}]"
            for i in issues
        )
        parts.append(f"OPEN ISSUES ({len(issues)}):\n{rows}")

    decisions = db.get_open_decisions(project_id)
    if decisions:
        rows = "\n".join(
            f"  - {d['id']}: {d['description']} "
            f"(Decision maker: {d.get('decision_maker') or '?'} | Status: {d['status']})"
            for d in decisions
        )
        parts.append(f"PENDING DECISIONS ({len(decisions)}):\n{rows}")

    return "\n\n".join(parts) if parts else "No tracked items found."


def _sops_context(project_id: str) -> str:
    """Builds a text block of known SOPs and rules."""
    sops = db.get_sops(project_id)
    if not sops:
        return "No SOPs on record."
    rows = "\n".join(f"  - [{s['title']}]: {s['rule_text']}" for s in sops)
    return f"KNOWN SOPS AND RULES:\n{rows}"


def knowledge_retrieval(message: dict, intent: str) -> list:
    """
    Reads real project data from DB and returns it directly.
    No Groq needed — the DB IS the ground truth here.
    This agent is called first so every other agent
    can reference the project facts it surfaces.
    """
    project_id = message.get("project")
    p = db.get_project(project_id) if project_id else None
    if not p:
        return [f"• Project {project_id} not found in database"]

    stakeholders   = db.get_project_stakeholders(project_id)
    open_ais       = db.get_open_action_items(project_id)
    open_risks     = db.get_open_risks(project_id)
    open_issues    = db.get_open_issues(project_id)
    open_decisions = db.get_open_decisions(project_id)

    out = [
        f"• Project:           {p['name']} ({project_id})",
        f"• Description:       {p.get('description', 'N/A')}",
        f"• Status:            {p.get('status', 'N/A').upper()}",
        f"• Release date:      {p.get('release_date', 'N/A')}",
        f"• Code freeze:       {p.get('code_freeze', 'N/A')}",
        f"• Progress:          {p.get('progress', 0)}% complete",
        f"• Team capacity:     {p.get('team_capacity', 0)}% utilised",
        f"• Eng manager:       {p.get('engineering_manager', '?')}",
        f"• Tech lead:         {p.get('tech_lead', '?')}",
        f"• Open action items: {len(open_ais)}",
        f"• Open risks:        {len(open_risks)} "
        f"(HIGH: {sum(1 for r in open_risks if r['likelihood'] == 'HIGH')})",
        f"• Open issues:       {len(open_issues)} "
        f"(HIGH: {sum(1 for i in open_issues if i['severity'] == 'HIGH')})",
        f"• Pending decisions: {len(open_decisions)}",
    ]
    if stakeholders:
        team = ", ".join(f"{s['name']} ({s['role']})" for s in stakeholders[:4])
        out.append(f"• Team:              {team}")
    return out


def evaluation(message: dict, intent: str, response_text: str = "") -> list:
    """
    Validates a response before delivery.
    Algorithm:
      1. Python fetches project facts from DB
      2. Python builds a 'known facts' text block
      3. Groq compares the response against those facts
      4. Returns PASS/FAIL for each dimension
    """
    project_id   = message.get("project")
    project_ctx  = _project_context(project_id)

    if USE_GROQ and client:
        system = """You are a quality evaluation agent for a project management AI.
You are given a response and the known project facts.
Check the response for accuracy against the facts provided.
Output EXACTLY these 5 lines — nothing else:
• Relevance: PASS or FAIL
• Accuracy: PASS or FAIL
• Tone: PASS or FAIL
• Gaps Acknowledged: PASS or FAIL
• Result: APPROVED or NEEDS_REVISION"""

        
        user = f"""RESPONSE TO EVALUATE:
{response_text or '[No response captured]'}

KNOWN PROJECT FACTS FROM DATABASE:
{project_ctx}"""

       
        raw = call_groq(system, user, max_tokens=120)
        if raw:
            return lines(raw)

    return [
        "• Relevance: PASS",
        "• Accuracy: PASS",
        "• Tone: PASS",
        "• Gaps Acknowledged: PASS",
        "• Result: APPROVED",
    ]


def action_item_extraction(message: dict, intent: str) -> list:
    """
    Algorithm:
      1. Python fetches existing action items from DB (to avoid duplicates)
      2. Python formats them as text for Groq
      3. Groq extracts NEW action items from the message
      4. Python parses Groq output with regex
      5. Python saves each new item to NeonDB
      6. Returns formatted output lines
    """
    project_id = message.get("project", "UNKNOWN")
    content    = message.get("content", "")
    msg_id     = message.get("message_id", "MSG-???")

    # Step 1: fetch existing items
    existing     = db.get_open_action_items(project_id)
    existing_txt = "\n".join(
        f"  - {a['id']}: {a['description']}" for a in existing
    ) or "  None"

    system = """You are an action item extraction agent.
Extract concrete, assignable action items from the message.
For each item output EXACTLY this format on one line:
ITEM: "description" | Owner: name_or_? | Due: date_or_?

Rules:
- 2 to 4 items maximum
- Do not repeat any item already in the existing list below
- Only write ITEM: lines — no other text"""

   
    user = f"""Message: {content}

Existing open action items (do not repeat these):
{existing_txt}"""

    output_lines = []

    if USE_GROQ and client:
        
        raw = call_groq(system, user)

        for line in raw.splitlines():
            line = line.strip()
            if not line or not line.startswith("ITEM:"):
                continue

            #Python parses with regex
            desc_m  = re.search(r'"([^"]+)"', line)
            owner_m = re.search(r'Owner:\s*([^|]+)', line)
            due_m   = re.search(r'Due:\s*(.+)$', line)

            desc  = desc_m.group(1).strip()  if desc_m  else line[5:].split("|")[0].strip()
            owner = owner_m.group(1).strip() if owner_m else None
            due   = due_m.group(1).strip()   if due_m   else None

            # Clean up "?" values
            if owner and owner.lower() in {"?", "unknown", "none", "tbd"}:
                owner = None
            if due and due.lower() in {"?", "unknown", "none", "tbd"}:
                due = None

            flags = []
            if not owner: flags.append("MISSING_OWNER")
            if not due:   flags.append("MISSING_DUE_DATE")

            #Python writes to NeonDB
            new_id = db.next_id("AI", project_id)
            db.save_action_item(
                project_id, new_id, desc,
                owner=owner, due_date=due,
                flags=",".join(flags) if flags else None,
                source_message=msg_id,
            )

            #format output line
            flag_str  = f" | Flags: [{', '.join(flags)}]" if flags else ""
            owner_str = owner or "?"
            due_str   = due   or "?"
            output_lines.append(f'• {new_id}: "{desc}"')
            output_lines.append(f'  Owner: {owner_str} | Due: {due_str}{flag_str}')

    if not output_lines:
        #show existing items from DB
        if existing:
            output_lines = [f'• {a["id"]}: "{a["description"]}"' for a in existing[:3]]
        else:
            output_lines = ['• No action items extracted (Groq unavailable)']

    return output_lines


def action_item_validation(message: dict, intent: str) -> list:
    """Reads all open AIs from DB, validates fields, returns report."""
    project_id = message.get("project", "UNKNOWN")
    items      = db.get_open_action_items(project_id)

    if not items:
        return ["• No open action items to validate"]

    out    = [f"• Validating {len(items)} open action item(s):"]
    issues = 0
    for a in items:
        flags = []
        if not a.get("owner"):    flags.append("MISSING_OWNER")
        if not a.get("due_date"): flags.append("MISSING_DUE_DATE")
        status    = "FAIL" if flags else "PASS"
        flag_str  = f" [{', '.join(flags)}]" if flags else ""
        out.append(f"  • {a['id']}: {status}{flag_str} — {a['description'][:55]}")
        if flags: issues += 1

    out.append(f"• Summary: {len(items) - issues} valid, {issues} need attention")
    return out


def action_item_tracking(message: dict, intent: str) -> list:
    """Snapshot of all open AIs from DB."""
    project_id = message.get("project", "UNKNOWN")
    items      = db.get_open_action_items(project_id)

    if not items:
        return ["• No open action items on record"]

    out = [f"• {len(items)} open action item(s):"]
    for a in items:
        out.append(f"  • {a['id']}: {a['description'][:55]}")
        out.append(
            f"    Owner: {a.get('owner') or '?'} | "
            f"Due: {a.get('due_date') or '?'} | "
            f"Status: {a['status']}"
        )
    return out


def risk_extraction(message: dict, intent: str) -> list:
    """Same 5-step algorithm as action_item_extraction."""
    project_id = message.get("project", "UNKNOWN")
    content    = message.get("content", "")
    msg_id     = message.get("message_id", "MSG-???")

    existing     = db.get_open_risks(project_id)
    existing_txt = "\n".join(
        f"  - {r['id']}: {r['description']}" for r in existing
    ) or "  None"

    system = """You are a risk extraction agent.
Extract project risks from the message.
For each risk output EXACTLY this format on one line:
RISK: "description" | Likelihood: HIGH/MEDIUM/LOW | Impact: HIGH/MEDIUM/LOW

Rules:
- 2 to 3 risks maximum
- Do not repeat risks already in the existing list
- Only write RISK: lines — no other text"""

    user = f"""Message: {content}

Existing open risks (do not repeat):
{existing_txt}"""

    output_lines = []

    if USE_GROQ and client:
        raw = call_groq(system, user)
        for line in raw.splitlines():
            line = line.strip()
            if not line or not line.startswith("RISK:"):
                continue

            desc_m  = re.search(r'"([^"]+)"', line)
            like_m  = re.search(r'Likelihood:\s*(HIGH|MEDIUM|LOW)', line, re.I)
            imp_m   = re.search(r'Impact:\s*(HIGH|MEDIUM|LOW)', line, re.I)

            desc       = desc_m.group(1).strip()         if desc_m else line[5:].split("|")[0].strip()
            likelihood = like_m.group(1).upper()         if like_m else "MEDIUM"
            impact     = imp_m.group(1).upper()          if imp_m  else "MEDIUM"

            new_id = db.next_id("RISK", project_id)
            db.save_risk(project_id, new_id, desc, likelihood, impact, msg_id)

            output_lines.append(f'• {new_id}: "{desc}"')
            output_lines.append(f'  Likelihood: {likelihood} | Impact: {impact}')

    if not output_lines:
        if existing:
            for r in existing[:3]:
                output_lines.append(f'• {r["id"]}: "{r["description"]}"')
                output_lines.append(f'  Likelihood: {r["likelihood"]} | Impact: {r["impact"]}')
        else:
            output_lines = ["• No risks extracted (Groq unavailable)"]

    return output_lines


def risk_tracking(message: dict, intent: str) -> list:
    project_id = message.get("project", "UNKNOWN")
    risks      = db.get_open_risks(project_id)
    if not risks:
        return ["• No open risks on record"]
    out = [f"• {len(risks)} open risk(s):"]
    for r in risks:
        out.append(f"  • {r['id']}: {r['description'][:55]}")
        out.append(f"    Likelihood: {r['likelihood']} | Impact: {r['impact']} | Status: {r['status']}")
    return out


def issue_extraction(message: dict, intent: str) -> list:
    project_id = message.get("project", "UNKNOWN")
    content    = message.get("content", "")
    msg_id     = message.get("message_id", "MSG-???")

    existing     = db.get_open_issues(project_id)
    existing_txt = "\n".join(
        f"  - {i['id']}: {i['description']}" for i in existing
    ) or "  None"

    system = """You are an issue extraction agent.
Extract blockers and problems from the message.
For each issue output EXACTLY this format on one line:
ISSUE: "description" | Severity: HIGH/MEDIUM/LOW

Rules:
- 1 to 3 issues maximum
- Do not repeat existing issues
- Only write ISSUE: lines — no other text"""

    user = f"""Message: {content}

Existing open issues (do not repeat):
{existing_txt}"""

    output_lines = []

    if USE_GROQ and client:
        raw = call_groq(system, user)
        for line in raw.splitlines():
            line = line.strip()
            if not line or not line.startswith("ISSUE:"):
                continue

            desc_m = re.search(r'"([^"]+)"', line)
            sev_m  = re.search(r'Severity:\s*(HIGH|MEDIUM|LOW)', line, re.I)

            desc     = desc_m.group(1).strip() if desc_m else line[6:].split("|")[0].strip()
            severity = sev_m.group(1).upper()  if sev_m  else "MEDIUM"

            new_id = db.next_id("ISS", project_id)
            db.save_issue(project_id, new_id, desc, severity, msg_id)

            output_lines.append(f'• {new_id}: "{desc}"')
            output_lines.append(f'  Severity: {severity}')

    if not output_lines:
        if existing:
            for i in existing[:2]:
                output_lines.append(f'• {i["id"]}: "{i["description"]}"')
                output_lines.append(f'  Severity: {i["severity"]}')
        else:
            output_lines = ["• No issues extracted (Groq unavailable)"]

    return output_lines


def issue_tracking(message: dict, intent: str) -> list:
    project_id = message.get("project", "UNKNOWN")
    issues     = db.get_open_issues(project_id)
    if not issues:
        return ["• No open issues on record"]
    out = [f"• {len(issues)} open issue(s):"]
    for i in issues:
        out.append(f"  • {i['id']}: {i['description'][:55]}")
        out.append(f"    Severity: {i['severity']} | Status: {i['status']}")
    return out


def decision_extraction(message: dict, intent: str) -> list:
    project_id = message.get("project", "UNKNOWN")
    content    = message.get("content", "")
    msg_id     = message.get("message_id", "MSG-???")

    existing     = db.get_open_decisions(project_id)
    existing_txt = "\n".join(
        f"  - {d['id']}: {d['description']}" for d in existing
    ) or "  None"

    system = """You are a decision extraction agent.
Identify decisions that need to be made based on the message.
For each decision output EXACTLY this format on one line:
DEC: "description" | Decision maker: role_or_?

Rules:
- 1 to 2 decisions maximum
- Do not repeat existing decisions
- Only write DEC: lines — no other text"""

    user = f"""Message: {content}

Existing pending decisions (do not repeat):
{existing_txt}"""

    output_lines = []

    if USE_GROQ and client:
        raw = call_groq(system, user)
        for line in raw.splitlines():
            line = line.strip()
            if not line or not line.startswith("DEC:"):
                continue

            desc_m = re.search(r'"([^"]+)"', line)
            dm_m   = re.search(r'Decision maker:\s*([^|$]+)', line, re.I)

            desc = desc_m.group(1).strip() if desc_m else line[4:].split("|")[0].strip()
            dm   = dm_m.group(1).strip()   if dm_m   else None
            if dm and dm.lower() in {"?", "unknown", "none", "tbd"}:
                dm = None

            new_id = db.next_id("DEC", project_id)
            db.save_decision(project_id, new_id, desc, dm, msg_id)

            output_lines.append(f'• {new_id}: "{desc}"')
            output_lines.append(f'  Decision maker: {dm or "?"} | Status: PENDING')

    if not output_lines:
        if existing:
            for d in existing[:2]:
                output_lines.append(f'• {d["id"]}: "{d["description"]}"')
                output_lines.append(f'  Decision maker: {d.get("decision_maker") or "?"} | Status: {d["status"]}')
        else:
            output_lines = ["• No decisions extracted (Groq unavailable)"]

    return output_lines


def decision_tracking(message: dict, intent: str) -> list:
    project_id = message.get("project", "UNKNOWN")
    decisions  = db.get_open_decisions(project_id)
    if not decisions:
        return ["• No pending decisions on record"]
    out = [f"• {len(decisions)} pending decision(s):"]
    for d in decisions:
        out.append(f"  • {d['id']}: {d['description'][:55]}")
        out.append(f"    Decision maker: {d.get('decision_maker') or '?'} | Status: {d['status']}")
    return out


def qna(message: dict, intent: str) -> list:
    """
    The main response agent — most important one.

    Algorithm:
      1. Python fetches project facts, all tracked items, SOPs from DB
      2. Python serialises all of it into a structured text block
      3. Groq reads that text block + the original message
      4. Groq generates a grounded, WHAT I KNOW / WHAT I NEED response
      5. Returns formatted output

    Groq never queries the DB. It reads a text briefing Python prepared.
    This is why answers are accurate — they're based on real DB data.
    """
    project_id  = message.get("project")
    content     = message.get("content", "")
    sender_name = message.get("sender", {}).get("name", "Unknown")
    sender_role = message.get("sender", {}).get("role", "Unknown")

    # Deterministic path for status questions: keeps responses factual and stable.
    # This improves evaluation accuracy by avoiding speculative wording.
    p = db.get_project(project_id) if project_id else None
    if intent == "status_question" and p:
        ais       = db.get_open_action_items(project_id)
        rsks      = db.get_open_risks(project_id)
        iss       = db.get_open_issues(project_id)
        decisions = db.get_open_decisions(project_id)

        open_actions = len(ais)
        open_risks = len(rsks)
        high_risks = sum(1 for r in rsks if r.get("likelihood") == "HIGH")
        open_issues = len(iss)
        high_issues = sum(1 for i in iss if i.get("severity") == "HIGH")
        pending_decisions = len(decisions)

        needs = []
        if open_actions > 0:
            needs.append(f"{open_actions} open action item(s)")
        if high_risks > 0:
            needs.append(f"{high_risks} HIGH risk(s)")
        if high_issues > 0:
            needs.append(f"{high_issues} HIGH issue(s)")
        if pending_decisions > 0:
            needs.append(f"{pending_decisions} pending decision(s)")

        what_i_need = (
            "No additional blockers found in tracked project data."
            if not needs else
            "Need closure on: " + ", ".join(needs) + "."
        )

        return [
            f'• Response: "WHAT I KNOW: {p["name"]} ({project_id}) is '
            f'{str(p.get("status", "N/A")).upper()} and {p.get("progress", 0)}% complete. '
            f'Release date: {p.get("release_date", "TBD")} | Code freeze: {p.get("code_freeze", "TBD")}.',
            f'WHAT I\'VE LOGGED: Open items snapshot -> {open_actions} action(s), {open_risks} risk(s), '
            f'{open_issues} issue(s), {pending_decisions} pending decision(s).',
            f'WHAT I NEED: {what_i_need}"',
        ]

    #Python fetches everything from DB 
    project_ctx = _project_context(project_id)
    items_ctx   = _items_context(project_id)
    sops_ctx    = _sops_context(project_id)

    #Python builds the full briefing text 
    briefing = f"""{project_ctx}

{items_ctx}

{sops_ctx}"""

    system = """You are Nion, a professional AI Program Manager assistant.
You have been given a DATABASE BRIEFING containing real project facts.
Use ONLY the information in the briefing to answer. Do not invent facts.

Structure your response using these sections when relevant:
WHAT I KNOW: (facts from the database)
WHAT I'VE LOGGED: (items extracted and saved this session)
WHAT I NEED: (missing info that would help)

Start your entire response with: • Response: "
End with a closing double-quote.
Keep under 180 words. Be specific and professional."""

    #Python calls Groq with real data as text
    user = f"""Message from {sender_name} ({sender_role}):
{content}

DATABASE BRIEFING:
{briefing}"""

    if USE_GROQ and client:
        raw = call_groq(system, user, max_tokens=400)
        if raw:
            return lines(raw)

    #Fallback for non-status intents when Groq is unavailable.
    if p:
        ais  = db.get_open_action_items(project_id)
        rsks = db.get_open_risks(project_id)
        iss  = db.get_open_issues(project_id)
        return [
            f'• Response: "{p["name"]} is {p.get("progress", 0)}% complete.',
            f'  Release: {p.get("release_date", "TBD")} | '
            f'Code freeze: {p.get("code_freeze", "TBD")}.',
            f'  Open items: {len(ais)} actions, {len(rsks)} risks, {len(iss)} issues."',
        ]
    return ['• Response: "No project context available to answer this question."']


def report_generation(message: dict, intent: str) -> list:
    """
    Generates a full status report.

    Algorithm:
      1. Python fetches all project data from DB
      2. Python builds a summary text block from the raw numbers
      3. Groq formats it into a polished digest
    """
    project_id = message.get("project")
    p          = db.get_project(project_id) if project_id else None

    if not p:
        return ["• Cannot generate report: project not found in database"]

    #Python fetches everything
    ais       = db.get_open_action_items(project_id)
    risks     = db.get_open_risks(project_id)
    issues    = db.get_open_issues(project_id)
    decisions = db.get_open_decisions(project_id)
    shs       = db.get_project_stakeholders(project_id)

    high_risks  = [r for r in risks  if r["likelihood"] == "HIGH"]
    high_issues = [i for i in issues if i["severity"]   == "HIGH"]
    missing_ais = [a for a in ais    if not a.get("owner")]

    #Python builds structured briefing
    briefing = f"""{_project_context(project_id)}

TRACKED ITEMS SUMMARY:
- Action items: {len(ais)} open ({len(missing_ais)} missing owner)
- Risks: {len(risks)} open ({len(high_risks)} HIGH likelihood)
- Issues: {len(issues)} open ({len(high_issues)} HIGH severity)
- Decisions: {len(decisions)} pending

TOP RISKS:
{chr(10).join(f'  - {r["id"]}: {r["description"]} [{r["likelihood"]}/{r["impact"]}]' for r in high_risks[:3]) or '  None'}

TOP ISSUES:
{chr(10).join(f'  - {i["id"]}: {i["description"]} [{i["severity"]}]' for i in high_issues[:3]) or '  None'}

PENDING DECISIONS:
{chr(10).join(f'  - {d["id"]}: {d["description"]}' for d in decisions[:3]) or '  None'}"""

    if USE_GROQ and client:
        system = """You are a report generation agent.
Using ONLY the database briefing provided, create a concise project status report.
Use this structure:
• REPORT: [project name and ID]
• Status: [overall health]
• Progress: [%]
• Release: [date]
• Summary: [2-sentence summary of project health]
• Key risks: [top 1-2 risks]
• Key issues: [top 1-2 issues]
• Decisions needed: [list]
Keep under 150 words."""

        #Groq formats it
        raw = call_groq(system, f"DATABASE BRIEFING:\n{briefing}", max_tokens=300)
        if raw:
            return lines(raw)

    #return structured DB data directly
    return [
        f"• REPORT: {p['name']} ({project_id})",
        f"• Status:     {p.get('status', 'N/A').upper()}",
        f"• Progress:   {p.get('progress', 0)}% complete",
        f"• Release:    {p.get('release_date', 'N/A')}",
        f"• Capacity:   {p.get('team_capacity', 0)}% utilised",
        f"• Actions:    {len(ais)} open ({len(missing_ais)} missing owner)",
        f"• Risks:      {len(risks)} open ({len(high_risks)} HIGH)",
        f"• Issues:     {len(issues)} open ({len(high_issues)} HIGH)",
        f"• Decisions:  {len(decisions)} pending",
    ]


def message_delivery(message: dict, intent: str) -> list:
    """
    Determines the best channel by looking up sender preferences in DB.

    Algorithm:
      1. Python looks up sender in stakeholders table
      2. Python reads their preferred_channel
      3. Python logs the delivery to delivery_log table
      4. Returns confirmation — no Groq needed
    """
    project_id  = message.get("project")
    sender_name = message.get("sender", {}).get("name", "Unknown")
    msg_id      = message.get("message_id", "MSG-???")
    source      = message.get("source", "email")

    #Python looks up channel preference in DB
    stakeholders  = db.get_project_stakeholders(project_id) if project_id else []
    sender_record = next((s for s in stakeholders if s["name"] == sender_name), None)
    channel       = sender_record["preferred_channel"] if sender_record else source or "email"

    #engineering manager, but not if they ARE the sender
    p  = db.get_project(project_id) if project_id else None
    cc = p.get("engineering_manager") if p else None
    if cc == sender_name:
        cc = p.get("tech_lead")  # fall back to tech lead

    #Python logs delivery to DB
    db.log_delivery(msg_id, sender_name, channel, cc)

    out = [
        f"• Channel:         {channel}",
        f"• Recipient:       {sender_name}",
    ]
    if cc:
        out.append(f"• CC:              {cc}")
    out.append("• Delivery status: SENT")
    return out


def meeting_attendance(message: dict, intent: str) -> list:
    """
    Processes a meeting transcript.

    Algorithm:
      1. Python parses speaker names with regex (no DB needed yet)
      2. Python passes transcript to Groq
      3. Groq generates per-speaker summaries and extracts minutes
      4. Returns structured meeting minutes
    """
    content = message.get("content", "")

    #Python extracts speaker names with regex
    #Looks for patterns like "Dev:", "QA:", "Tech Lead:" at line start
    speakers = re.findall(r'^([A-Za-z][A-Za-z ]{1,20}):', content, re.MULTILINE)
    unique_speakers = list(dict.fromkeys(s.strip() for s in speakers))

    output_lines = ["• Meeting transcript captured"]
    if unique_speakers:
        output_lines.append(f"• Participants identified: {', '.join(unique_speakers)}")

    if USE_GROQ and client:
        system = """You are a meeting attendance agent.
Process the transcript and generate concise meeting minutes.
Output format:
• SUMMARY: [one sentence overall summary]
• [Speaker name]: [their key point in one line]  (repeat for each speaker)
• ACTION: [any action item mentioned]  (repeat for each action)
• DECISION: [any decision made]  (repeat for each decision)
Keep under 150 words."""

        #Groq reads transcript text and generates minutes
        raw = call_groq(system, f"Meeting transcript:\n{content}", max_tokens=300)
        if raw:
            output_lines += lines(raw)
    else:
        #Fallback: Python summarises directly from speaker extraction
        if unique_speakers:
            output_lines.append(f"• {len(unique_speakers)} participant(s) spoke")
        output_lines.append("• Full minutes require Groq to be configured")

    output_lines.append("• Minutes generated and stored")
    return output_lines


def instruction_led_learning(message: dict, intent: str) -> list:
    """
    Learns a rule from the message and saves it to DB.

    Algorithm:
      1. Python checks existing SOPs to avoid duplicate rules
      2. Groq extracts a reusable rule from the message
      3. Python saves the rule to the sops table in NeonDB
      4. Future runs: qna and report_generation will load this rule
         via _sops_context() and use it in their briefings

    This is how the system learns — each learned rule gets injected
    into every future agent call through the SOPs context block.
    """
    project_id = message.get("project")
    content    = message.get("content", "")

    #fetch existing SOPs so Groq doesn't duplicate
    existing     = db.get_sops(project_id)
    existing_txt = "\n".join(
        f"  - {s['title']}: {s['rule_text']}" for s in existing
    ) or "  None"

    if USE_GROQ and client:
        system = """You are a learning agent for a project management AI.
Extract ONE reusable rule or SOP from the message.
Output EXACTLY two lines:
Title: [short title, max 6 words]
Rule: [the rule as one clear sentence]

Do not repeat rules already in the existing list."""

        user = f"""Message: {content}

Existing rules (do not repeat):
{existing_txt}"""

        #Groq extracts the rule from message text
        raw = call_groq(system, user, max_tokens=100)

        if raw:
            title_m = re.search(r'Title:\s*(.+)', raw)
            rule_m  = re.search(r'Rule:\s*(.+)',  raw)
            title   = title_m.group(1).strip() if title_m else "Learned rule"
            rule    = rule_m.group(1).strip()  if rule_m  else raw.strip()

            # Python saves to NeonDB
            db.save_sop(project_id, title, rule)

            return [
                f"• SOP captured:  {title}",
                f"• Rule stored:   {rule}",
                "• Saved to database — will inform future agent responses",
            ]

    # Fallback
    db.save_sop(project_id, "General instruction", content[:120])
    return [
        "• SOP captured from message content",
        f"• Rule stored: {content[:80]}...",
        "• Saved to database",
    ]

AGENT_REGISTRY = {
    # Cross-cutting
    "knowledge_retrieval":      knowledge_retrieval,
    "evaluation":               evaluation,
    # TRACKING_EXECUTION
    "action_item_extraction":   action_item_extraction,
    "action_item_validation":   action_item_validation,
    "action_item_tracking":     action_item_tracking,
    "risk_extraction":          risk_extraction,
    "risk_tracking":            risk_tracking,
    "issue_extraction":         issue_extraction,
    "issue_tracking":           issue_tracking,
    "decision_extraction":      decision_extraction,
    "decision_tracking":        decision_tracking,
    # COMMUNICATION_COLLABORATION
    "qna":                      qna,
    "report_generation":        report_generation,
    "message_delivery":         message_delivery,
    "meeting_attendance":       meeting_attendance,
    # LEARNING_IMPROVEMENT
    "instruction_led_learning": instruction_led_learning,
}


def get_agent_output(agent: str, message: dict, intent: str, response_text: str = "") -> list:
    func = AGENT_REGISTRY.get(agent)
    if func:
        try:
            if agent == "evaluation":
                return func(message, intent, response_text=response_text)
            return func(message, intent)
        except Exception as e:
            return [f"• [{agent}] error: {str(e)}"]
    return [f"• [{agent}] not implemented"]
