"""
Compaction Demo — Lecture 4.2

Demonstrates conversation compaction: taking a long multi-turn agent conversation
and summarizing it into a compact context that preserves essential information.

Shows before/after token counts to illustrate the savings.

Usage: uv run compaction_demo.py
"""

import anthropic

client = anthropic.Anthropic()
MODEL = "claude-haiku-4-5-20251001"  # Haiku for speed/cost in demos

# ---------------------------------------------------------------------------
# A realistic multi-turn agent conversation to compact.
# This simulates an agent helping debug a web application — the kind of
# conversation that generates thousands of tokens of tool results.
# ---------------------------------------------------------------------------

SAMPLE_CONVERSATION = [
    {"role": "user", "content": "The login page is broken. Users are getting a 500 error when they try to log in. Can you investigate?"},
    {"role": "assistant", "content": "I'll investigate the login issue. Let me start by reading the login route handler.\n\n[tool_use: read_file('routes/auth.py')]"},
    {"role": "user", "content": "[tool_result]\nimport bcrypt\nfrom flask import request, jsonify, session\nfrom models.user import User\nfrom db import get_db_connection\n\n@app.route('/login', methods=['POST'])\ndef login():\n    data = request.get_json()\n    email = data.get('email')\n    password = data.get('password')\n    \n    conn = get_db_connection()\n    cursor = conn.cursor()\n    cursor.execute('SELECT id, email, password_hash, role FROM users WHERE email = %s', (email,))\n    user = cursor.fetchone()\n    \n    if user and bcrypt.checkpw(password.encode('utf-8'), user[2].encode('utf-8')):\n        session['user_id'] = user[0]\n        session['role'] = user[3]\n        return jsonify({'status': 'ok', 'user_id': user[0]})\n    \n    return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401\n"},
    {"role": "assistant", "content": "The login route looks syntactically correct. Let me check the error logs to see what's actually failing.\n\n[tool_use: run_command('tail -50 logs/app.log')]"},
    {"role": "user", "content": "[tool_result]\n2024-03-10 14:22:01 ERROR: Exception on /login [POST]\nTraceback (most recent call last):\n  File \"routes/auth.py\", line 14, in login\n    cursor.execute('SELECT id, email, password_hash, role FROM users WHERE email = %s', (email,))\npsycopg2.errors.UndefinedColumn: column \"password_hash\" does not exist\nLINE 1: SELECT id, email, password_hash, role FROM users WHERE email...\n                           ^\nHINT: Perhaps you meant to reference the column \"users.password\".\n\n2024-03-10 14:22:15 ERROR: Exception on /login [POST]\n[same error repeated 12 more times]\n"},
    {"role": "assistant", "content": "Found it. The database column is named `password` but the code references `password_hash`. This is likely from a recent migration that renamed the column. Let me check the database schema to confirm.\n\n[tool_use: run_command('psql -c \"\\d users\"')]"},
    {"role": "user", "content": "[tool_result]\n                Table \"public.users\"\n  Column   |          Type          | Nullable | Default\n-----------+------------------------+----------+---------\n id        | integer                | not null | nextval\n email     | character varying(255) | not null |\n password  | character varying(255) | not null |\n role      | character varying(50)  |          | 'user'\n created_at| timestamp              |          | now()\n\nIndexes:\n    \"users_pkey\" PRIMARY KEY (id)\n    \"users_email_key\" UNIQUE (email)\n"},
    {"role": "assistant", "content": "Confirmed. The column is `password`, not `password_hash`. The fix is straightforward — update the SQL query in auth.py. Let me also check if this column name is used elsewhere.\n\n[tool_use: run_command('grep -rn \"password_hash\" routes/ models/')]"},
    {"role": "user", "content": "[tool_result]\nroutes/auth.py:14:    cursor.execute('SELECT id, email, password_hash, role FROM users WHERE email = %s', (email,))\nroutes/auth.py:16:    if user and bcrypt.checkpw(password.encode('utf-8'), user[2].encode('utf-8')):\nmodels/user.py:8:        self.password_hash = password_hash\nmodels/user.py:22:        cursor.execute('INSERT INTO users (email, password_hash, role) VALUES (%s, %s, %s)',\n"},
    {"role": "assistant", "content": "The incorrect column name appears in three places: the login query, the User model, and the insert statement. I'll fix all three.\n\n[tool_use: edit_file('routes/auth.py', line=14, new_content=\"    cursor.execute('SELECT id, email, password, role FROM users WHERE email = %s', (email,))\")]"},
    {"role": "user", "content": "[tool_result]\nFile routes/auth.py updated successfully."},
    {"role": "assistant", "content": "[tool_use: edit_file('models/user.py', line=8, new_content='        self.password = password')]"},
    {"role": "user", "content": "[tool_result]\nFile models/user.py updated successfully."},
    {"role": "assistant", "content": "[tool_use: edit_file('models/user.py', line=22, new_content=\"        cursor.execute('INSERT INTO users (email, password, role) VALUES (%s, %s, %s)',\")]"},
    {"role": "user", "content": "[tool_result]\nFile models/user.py updated successfully."},
    {"role": "assistant", "content": "All three references updated. Let me run the test suite to verify the fix.\n\n[tool_use: run_command('python -m pytest tests/test_auth.py -v')]"},
    {"role": "user", "content": "[tool_result]\ntests/test_auth.py::test_login_valid_user PASSED\ntests/test_auth.py::test_login_invalid_password PASSED\ntests/test_auth.py::test_login_nonexistent_user PASSED\ntests/test_auth.py::test_login_missing_fields PASSED\ntests/test_auth.py::test_session_set_on_login PASSED\n\n5 passed in 0.42s"},
    {"role": "assistant", "content": "All 5 auth tests pass. The fix is complete.\n\nThe issue was a column name mismatch: the code referenced `password_hash` but the database column is `password`. This affected the login query in `routes/auth.py` and the User model in `models/user.py`. Both files have been updated, and all tests pass."},
]

# ---------------------------------------------------------------------------
# The compaction prompt — this is the key engineering artifact.
# A good compaction prompt is specific about what to preserve and discard.
# ---------------------------------------------------------------------------

COMPACTION_PROMPT = """Summarize the following conversation between a user and an AI coding assistant.
This summary will REPLACE the full conversation in the assistant's context window,
so it must contain everything the assistant needs to continue working effectively.

PRESERVE (include in summary):
- Decisions made and actions taken (what was changed, what was committed)
- Current state of the task (is it complete? what's left?)
- Key facts about the project (languages, frameworks, file paths, database schema details)
- Any unresolved issues or follow-up items the user mentioned
- The user's preferences or constraints that were established

DISCARD (omit from summary):
- Raw file contents that were read (just note which files were examined)
- Full command outputs (just note the result — e.g., "all tests passed")
- The assistant's reasoning process (keep conclusions, drop the chain of thought)
- Intermediate tool calls (just note the outcome)
- Redundant or superseded information

FORMAT: Write a concise summary in plain text. Use bullet points for clarity.
Start with "## Conversation Summary" and organize by: Task, Key Findings, Actions Taken, Current State.

CONVERSATION TO SUMMARIZE:
"""


def format_conversation(messages):
    """Format messages into a readable string for the compaction prompt."""
    lines = []
    for msg in messages:
        role = msg["role"].upper()
        content = msg["content"]
        # Truncate very long tool results for display
        if len(content) > 500:
            content = content[:500] + "..."
        lines.append(f"[{role}]: {content}")
    return "\n\n".join(lines)


def count_tokens_estimate(messages):
    """Rough token estimate: ~4 chars per token for English text."""
    total_chars = sum(len(m["content"]) for m in messages)
    return total_chars // 4


def compact_conversation(messages):
    """Compact a conversation using LLM summarization."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": COMPACTION_PROMPT + format_conversation(messages)
        }]
    )

    summary = response.content[0].text

    # The compacted conversation: summary as context, then acknowledgment
    compacted = [
        {"role": "user", "content": f"[Prior conversation summary]\n{summary}"},
        {"role": "assistant", "content": "Understood. I have the context from the prior conversation and I'm ready to continue."}
    ]

    return compacted, summary, response.usage


def main():
    print("=" * 60)
    print("COMPACTION DEMO — Lecture 4.2")
    print("=" * 60)

    # Before compaction
    original_estimate = count_tokens_estimate(SAMPLE_CONVERSATION)
    print(f"\nOriginal conversation: {len(SAMPLE_CONVERSATION)} messages")
    print(f"Estimated tokens: ~{original_estimate}")
    print()

    # Run compaction
    print("Compacting conversation...")
    compacted_messages, summary, usage = compact_conversation(SAMPLE_CONVERSATION)

    compacted_estimate = count_tokens_estimate(compacted_messages)
    reduction = (1 - compacted_estimate / original_estimate) * 100

    print(f"\nCompaction API call cost: {usage.input_tokens} in, {usage.output_tokens} out")
    print()
    print("-" * 60)
    print("SUMMARY PRODUCED:")
    print("-" * 60)
    print(summary)
    print("-" * 60)
    print()
    print(f"After compaction: {len(compacted_messages)} messages")
    print(f"Estimated tokens: ~{compacted_estimate}")
    print(f"Reduction: ~{reduction:.0f}%")
    print()

    # Demonstrate that the agent can continue from the compacted context
    print("=" * 60)
    print("CONTINUING FROM COMPACTED CONTEXT...")
    print("=" * 60)

    # Add a follow-up question to the compacted conversation
    follow_up = {"role": "user", "content": "Are there any other places in the codebase that might have the same column name issue?"}
    compacted_messages.append(follow_up)

    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        messages=compacted_messages
    )

    print(f"\nFollow-up question: {follow_up['content']}")
    print(f"\nAgent response (from compacted context):")
    print(response.content[0].text)
    print(f"\n[Tokens: {response.usage.input_tokens} in, {response.usage.output_tokens} out]")


if __name__ == "__main__":
    main()
