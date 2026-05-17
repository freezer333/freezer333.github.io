"""
Compaction — Lecture 7.3

Wires conversation compaction into the agent context-management hook.
Provides:

- COMPACTION_PROMPT       the engineering artifact that decides what survives
- should_compact()        threshold detection over input_tokens
- compact_messages()      the hybrid pattern: summary + last K verbatim

Reuses the alternating-roles pass from Lecture 7.1 (duplicated here so each
lecture's file runs standalone; Lab 5 consolidates into a shared module).

Usage: uv run compaction.py
"""

import os
from dotenv import load_dotenv
import anthropic

load_dotenv()
client = anthropic.Anthropic()

# Haiku for summarization — same input quality, ~4x lower cost than Sonnet.
SUMMARIZER_MODEL = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# The compaction prompt. This is the engineering artifact — almost all of
# the design effort in compaction goes into the preserve/discard lists and
# the format specification.
# ---------------------------------------------------------------------------

COMPACTION_PROMPT = """Summarize the conversation between a user and an AI coding assistant
that follows. This summary will REPLACE most of the conversation in the
assistant's context window, so it must contain everything the assistant
needs to continue working effectively.

PRESERVE (include in summary):
- Decisions made and actions taken — what was changed, what was committed
- Current state of the task — is it complete? what's left?
- Key facts about the project — languages, frameworks, file paths, schema details
- Unresolved issues or follow-up items the user mentioned
- User preferences and constraints established earlier in the session

DISCARD (omit from summary):
- Raw file contents that were read — note which files, not their bytes
- Full command outputs — note the result, not the bytes
- The assistant's chain-of-thought reasoning — keep conclusions, drop reasoning
- Intermediate tool calls — note the outcome, not the sequence
- Redundant or superseded information — the third version of a plan, not the first two

FORMAT: Plain text. Use the four sections below verbatim. Use short bullet
points within each section.

## Conversation Summary

Task: <one-line description of the original goal>
Key Findings: <bullets>
Actions Taken: <bullets>
Current State: <done | in-progress with what remains>

CONVERSATION TO SUMMARIZE:
"""


# ---------------------------------------------------------------------------
# Threshold detection
# ---------------------------------------------------------------------------

def should_compact(input_tokens, model_limit, threshold=0.8):
    """Return True when input usage crosses the configured threshold.

    Called between inner-loop iterations. The hook should also check that
    the previous response was not a tool_use — compacting mid-tool-call
    would leave an orphaned tool_use without its tool_result.
    """
    return input_tokens >= model_limit * threshold


# ---------------------------------------------------------------------------
# Alternating-roles pass — same helper as Lecture 7.1
# ---------------------------------------------------------------------------

def ensure_alternating_roles(messages):
    """Insert synthetic acks between consecutive same-role messages."""
    if not messages:
        return messages
    result = [messages[0]]
    for msg in messages[1:]:
        if msg["role"] == result[-1]["role"]:
            ack_role = "assistant" if msg["role"] == "user" else "user"
            ack_text = "Understood." if ack_role == "assistant" else "Continue."
            result.append({"role": ack_role, "content": ack_text})
        result.append(msg)
    return result


# ---------------------------------------------------------------------------
# Pair-integrity helper for the hybrid split
# ---------------------------------------------------------------------------

def safe_split_index(messages, candidate):
    """Move a candidate split index forward to the next safe boundary.

    A safe boundary is a user message whose content is not a tool_result —
    cutting before it does not orphan a tool_use in the older portion.
    """
    while candidate < len(messages):
        msg = messages[candidate]
        if msg["role"] == "user":
            content = msg["content"]
            if isinstance(content, str):
                return candidate
            if not any(isinstance(b, dict) and b.get("type") == "tool_result"
                       for b in content):
                return candidate
        candidate += 1
    return candidate


# ---------------------------------------------------------------------------
# Conversation rendering for the prompt
# ---------------------------------------------------------------------------

def render_for_summary(messages):
    """Render messages as plain text the summarizer can read."""
    lines = []
    for msg in messages:
        role = msg["role"].upper()
        content = msg["content"]
        if isinstance(content, str):
            lines.append(f"[{role}] {content}")
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                lines.append(f"[{role}] {block.get('text', '')}")
            elif btype == "tool_use":
                args = ", ".join(f"{k}={v!r}"
                                 for k, v in block.get("input", {}).items())
                lines.append(f"[{role}] tool_use {block.get('name')}({args})")
            elif btype == "tool_result":
                result = block.get("content", "")
                if isinstance(result, list):
                    result = " ".join(b.get("text", "") for b in result
                                      if isinstance(b, dict) and b.get("type") == "text")
                preview = result if len(result) <= 300 else result[:300] + "..."
                lines.append(f"[{role}] tool_result {preview}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The hybrid-pattern compaction
# ---------------------------------------------------------------------------

def compact_messages(messages, keep_last_k=6):
    """Compact a messages array using the hybrid pattern.

    Splits the conversation into (older, recent). Older is summarized via
    Haiku. Recent is kept verbatim. The result is:

        [summary as user] + [ack as assistant] + [recent verbatim]

    The split point is moved forward if necessary to land on a safe
    boundary (preserves pair integrity in the older portion). The final
    array is run through ensure_alternating_roles to repair any same-role
    adjacency at the join.

    Returns (rebuilt_messages, summary_text, usage).
    """
    if len(messages) <= keep_last_k:
        return list(messages), None, None

    candidate_split = len(messages) - keep_last_k
    split = safe_split_index(messages, candidate_split)

    older = messages[:split]
    recent = messages[split:]

    if not older:
        return list(messages), None, None

    response = client.messages.create(
        model=SUMMARIZER_MODEL,
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": COMPACTION_PROMPT + render_for_summary(older),
        }],
    )
    summary = response.content[0].text

    rebuilt = [
        {"role": "user", "content": f"[Prior conversation summary]\n{summary}"},
        {"role": "assistant", "content": "Understood. I have the prior context and will continue from here."},
    ] + recent

    return ensure_alternating_roles(rebuilt), summary, response.usage


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

# A long-ish sample conversation. Adapted from compaction_demo.py (Lecture
# 4.2) but expressed in the same content-block format the agent loop uses.
SAMPLE_CONVERSATION = [
    {"role": "user", "content": "The login page is broken — users get a 500 error. Investigate."},
    {"role": "assistant", "content": [
        {"type": "text", "text": "I'll start by reading the login route handler."},
        {"type": "tool_use", "id": "tu_001", "name": "read_file",
         "input": {"filename": "routes/auth.py"}},
    ]},
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_001",
         "content": "import bcrypt\n@app.route('/login')\ndef login():\n    cursor.execute('SELECT id, email, password_hash, role FROM users WHERE email = %s', (email,))\n    ..."},
    ]},
    {"role": "assistant", "content": [
        {"type": "tool_use", "id": "tu_002", "name": "run_command",
         "input": {"cmd": "tail -50 logs/app.log"}},
    ]},
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_002",
         "content": "ERROR: column 'password_hash' does not exist. HINT: Perhaps you meant the column 'users.password'."},
    ]},
    {"role": "assistant", "content": [
        {"type": "text", "text": "The column is named password, not password_hash. Confirming with the schema."},
        {"type": "tool_use", "id": "tu_003", "name": "run_command",
         "input": {"cmd": "psql -c '\\d users'"}},
    ]},
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_003",
         "content": "Table users: id integer, email varchar(255), password varchar(255), role varchar(50), created_at timestamp"},
    ]},
    {"role": "assistant", "content": [
        {"type": "tool_use", "id": "tu_004", "name": "run_command",
         "input": {"cmd": "grep -rn 'password_hash' routes/ models/"}},
    ]},
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_004",
         "content": "routes/auth.py:14: ... password_hash ...\nmodels/user.py:8: self.password_hash = ...\nmodels/user.py:22: INSERT INTO users (email, password_hash, role) ..."},
    ]},
    {"role": "assistant", "content": [
        {"type": "text", "text": "Three references to fix. Editing routes/auth.py first."},
        {"type": "tool_use", "id": "tu_005", "name": "edit_file",
         "input": {"filename": "routes/auth.py", "old_str": "password_hash", "new_str": "password"}},
    ]},
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_005",
         "content": "Edited routes/auth.py"},
    ]},
    {"role": "assistant", "content": [
        {"type": "tool_use", "id": "tu_006", "name": "edit_file",
         "input": {"filename": "models/user.py", "old_str": "password_hash", "new_str": "password"}},
    ]},
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_006",
         "content": "Edited models/user.py (2 occurrences)"},
    ]},
    {"role": "assistant", "content": [
        {"type": "tool_use", "id": "tu_007", "name": "run_command",
         "input": {"cmd": "python -m pytest tests/test_auth.py -v"}},
    ]},
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_007",
         "content": "5 passed in 0.42s — login_valid_user, login_invalid_password, login_nonexistent_user, login_missing_fields, session_set_on_login"},
    ]},
    {"role": "assistant", "content": [
        {"type": "text", "text": "All five auth tests pass. The fix is complete."},
    ]},
    # Recent K — kept verbatim
    {"role": "user", "content": "Are there any other places in the codebase that might have the same column-name issue?"},
    {"role": "assistant", "content": [
        {"type": "text", "text": "Let me check the migrations directory and any admin scripts."},
        {"type": "tool_use", "id": "tu_008", "name": "run_command",
         "input": {"cmd": "grep -rn 'password_hash' migrations/ scripts/"}},
    ]},
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_008",
         "content": "scripts/seed_users.py:15: 'password_hash': bcrypt.hashpw(...)"},
    ]},
    {"role": "assistant", "content": [
        {"type": "text", "text": "One more in scripts/seed_users.py. I'll fix it."},
    ]},
]


def estimate_tokens(messages):
    """Cheap character-based token estimate (~4 chars/token)."""
    total = 0
    for msg in messages:
        content = msg["content"]
        if isinstance(content, str):
            total += len(content)
            continue
        for block in content:
            if isinstance(block, dict):
                for value in block.values():
                    if isinstance(value, str):
                        total += len(value)
                    elif isinstance(value, dict):
                        for v in value.values():
                            if isinstance(v, str):
                                total += len(v)
    return total // 4


def main():
    print("=" * 72)
    print("Compaction — Lecture 7.3")
    print("=" * 72)

    original_tokens = estimate_tokens(SAMPLE_CONVERSATION)
    print(f"\nOriginal conversation: {len(SAMPLE_CONVERSATION)} messages")
    print(f"Estimated tokens: ~{original_tokens}")

    # Threshold demo. With model_limit=200_000 and threshold=0.8, the demo
    # never triggers. Lower the limit so the threshold fires on this small
    # sample.
    demo_limit = 4000
    fired = should_compact(original_tokens, demo_limit, threshold=0.8)
    print(f"\nshould_compact({original_tokens}, model_limit={demo_limit}, "
          f"threshold=0.8) = {fired}")

    print("\nCompacting (keeping last 4 messages verbatim)...")
    compacted, summary, usage = compact_messages(SAMPLE_CONVERSATION, keep_last_k=4)

    print(f"\nSummarizer call: {usage.input_tokens} in / {usage.output_tokens} out")
    print()
    print("-" * 72)
    print("SUMMARY PRODUCED:")
    print("-" * 72)
    print(summary)
    print("-" * 72)

    compacted_tokens = estimate_tokens(compacted)
    reduction = (1 - compacted_tokens / original_tokens) * 100
    print()
    print(f"Compacted conversation: {len(compacted)} messages")
    print(f"Estimated tokens: ~{compacted_tokens}")
    print(f"Reduction: ~{reduction:.0f}%")

    print()
    print("=" * 72)
    print("CONTINUING FROM COMPACTED CONTEXT")
    print("=" * 72)

    follow_up = {
        "role": "user",
        "content": "What was the original error and how many places did we fix?",
    }
    compacted.append(follow_up)
    compacted = ensure_alternating_roles(compacted)

    response = client.messages.create(
        model=SUMMARIZER_MODEL,
        max_tokens=512,
        messages=compacted,
    )
    print(f"\nFollow-up: {follow_up['content']}")
    print(f"\nAgent response from compacted context:")
    print(response.content[0].text)
    print(f"\n[Tokens: {response.usage.input_tokens} in / "
          f"{response.usage.output_tokens} out]")


if __name__ == "__main__":
    main()
