"""
Sliding Window — Lecture 7.1

Implements a pair-aware sliding window for the Anthropic Messages API.

The function satisfies two API constraints that a naive `messages[-n:]`
slice violates:

  1. Pair integrity. Every tool_use block must be followed by its matching
     tool_result. Cutting between them produces:

        400 Bad Request: messages: tool_use ids found without
        tool_result blocks immediately after

  2. Alternating roles. user/assistant must alternate. Anchor preservation
     prepends the first user message — which can land next to another user
     message at the cut point — and a synthetic ack is needed to repair the
     join.

The function walks forward from the candidate cut to find a safe boundary
(a user message that is not a tool_result), prepends the first user
message as a task anchor when it would otherwise be dropped, and runs an
alternating-roles pass.

Usage: uv run sliding_window.py
"""

# ---------------------------------------------------------------------------
# Sample conversation. Mirrors the structure of a real agent session: a user
# request, then alternating assistant tool_use / user tool_result pairs,
# punctuated by occasional plain assistant text and a follow-up user request.
# Constructed so that a naive last-N cut would orphan a tool_result block.
# ---------------------------------------------------------------------------

SAMPLE_CONVERSATION = [
    # [0]
    {"role": "user", "content": "Refactor the database layer to use connection pooling."},
    # [1]
    {"role": "assistant", "content": [
        {"type": "text", "text": "I'll start by reading the current database module."},
        {"type": "tool_use", "id": "tu_001", "name": "read_file", "input": {"filename": "db.py"}},
    ]},
    # [2]
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_001", "content": "import sqlite3\n\ndef get_connection():\n    return sqlite3.connect('app.db')\n"},
    ]},
    # [3]
    {"role": "assistant", "content": [
        {"type": "tool_use", "id": "tu_002", "name": "read_file", "input": {"filename": "models/user.py"}},
    ]},
    # [4]
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_002", "content": "from db import get_connection\n\nclass User:\n    ..."},
    ]},
    # [5]
    {"role": "assistant", "content": [
        {"type": "text", "text": "I see the pattern. I'll add a connection pool and update db.py."},
        {"type": "tool_use", "id": "tu_003", "name": "edit_file", "input": {"filename": "db.py", "old_str": "...", "new_str": "..."}},
    ]},
    # [6]
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_003", "content": "Edited db.py"},
    ]},
    # [7]
    {"role": "assistant", "content": [
        {"type": "text", "text": "Done. The pool is now used in db.py."},
    ]},
    # [8]
    {"role": "user", "content": "Now update models/user.py to use the new pool."},
    # [9]
    {"role": "assistant", "content": [
        {"type": "tool_use", "id": "tu_004", "name": "edit_file", "input": {"filename": "models/user.py", "old_str": "...", "new_str": "..."}},
    ]},
    # [10]
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_004", "content": "Edited models/user.py"},
    ]},
    # [11]
    {"role": "assistant", "content": [
        {"type": "text", "text": "Updated models/user.py to use the pool."},
    ]},
]


def is_safe_boundary(messages, index):
    """Return True if cutting at `index` would leave a valid messages array.

    A safe boundary is a user message whose content is not a tool_result.
    Cutting before such a message means the new first message is a real
    user input, which is always valid as the start of a conversation.
    """
    if index >= len(messages):
        return True
    msg = messages[index]
    if msg["role"] != "user":
        return False
    # Plain string content (a real user input) is always safe.
    if isinstance(msg["content"], str):
        return True
    # Block-list content is only safe if it contains no tool_result blocks.
    for block in msg["content"]:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            return False
    return True


def ensure_alternating_roles(messages):
    """Insert synthetic acks between consecutive same-role messages.

    The Anthropic API requires `user` and `assistant` roles to alternate.
    Anchor preservation can create two adjacent user messages (the prepended
    anchor and the user message at the cut point). This pass inserts a brief
    assistant acknowledgment between them.
    """
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


def sliding_window(messages, keep_last_n, preserve_anchor=True):
    """Keep the last N messages, walking forward to a safe cut point.

    If preserve_anchor is True, the first user message is prepended to the
    window when it would otherwise be dropped. This protects against goal
    loss when the window slides past the original task description.

    The returned list satisfies both Anthropic API constraints:
    - Every tool_use is followed by its tool_result (pair integrity)
    - Roles alternate between user and assistant
    """
    if len(messages) <= keep_last_n:
        return list(messages)

    # Candidate cut: keep the last N messages.
    cut = len(messages) - keep_last_n

    # Walk forward to the first safe boundary. The kept window may end up
    # smaller than keep_last_n, but it will always be a valid messages array.
    while cut < len(messages) and not is_safe_boundary(messages, cut):
        cut += 1

    kept = messages[cut:]

    # Prepend the first user message as a task anchor if it isn't already
    # in the window. This can introduce two adjacent user messages, which
    # the alternating-roles pass below repairs.
    if preserve_anchor and messages and messages[0]["role"] == "user":
        if cut > 0:
            kept = [messages[0]] + kept

    return ensure_alternating_roles(kept)


# ---------------------------------------------------------------------------
# Display helpers — render the messages array in a compact form so the
# before/after difference is easy to read in the terminal.
# ---------------------------------------------------------------------------

def summarize_message(msg):
    """One-line description of a message for terminal display."""
    role = msg["role"]
    content = msg["content"]
    if isinstance(content, str):
        preview = content if len(content) <= 60 else content[:57] + "..."
        return f"{role:9s} | text: {preview!r}"
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "?")
        if btype == "text":
            text = block.get("text", "")
            preview = text if len(text) <= 40 else text[:37] + "..."
            parts.append(f"text({preview!r})")
        elif btype == "tool_use":
            parts.append(f"tool_use({block.get('name')}, id={block.get('id')})")
        elif btype == "tool_result":
            parts.append(f"tool_result(id={block.get('tool_use_id')})")
        else:
            parts.append(btype)
    return f"{role:9s} | {' + '.join(parts)}"


def print_conversation(messages, label):
    print(f"\n{label} ({len(messages)} messages)")
    print("-" * 72)
    for i, msg in enumerate(messages):
        print(f"  [{i:2d}] {summarize_message(msg)}")


def main():
    print("=" * 72)
    print("Sliding Window — Lecture 7.1")
    print("=" * 72)

    print_conversation(SAMPLE_CONVERSATION, "Original conversation")

    # Ask to keep the last 6 messages. The naive cut lands at index 6, which
    # is a user message containing a tool_result — orphaning the matching
    # tool_use at index 5. The API would reject the next request.
    keep = 6
    cut_index = len(SAMPLE_CONVERSATION) - keep
    naive = SAMPLE_CONVERSATION[cut_index:]
    print(f"\nNaive cut: messages[-{keep}:] starts at index {cut_index}")
    print(f"  Message at [{cut_index}] contains a tool_result with no preceding")
    print(f"  tool_use — the API rejects this with a 400 error.")
    print(f"  Naive window length: {len(naive)} messages (broken)")

    # Pair-aware sliding window without anchor.
    truncated_no_anchor = sliding_window(SAMPLE_CONVERSATION, keep_last_n=keep,
                                         preserve_anchor=False)
    print_conversation(truncated_no_anchor,
                       f"Pair-aware sliding window (keep_last_n={keep}, no anchor)")
    print(f"\n  Asked for {keep}, got {len(truncated_no_anchor)} — the function walked")
    print(f"  forward from index {cut_index} to the next safe boundary at index 8.")

    # Pair-aware sliding window with anchor preservation.
    truncated = sliding_window(SAMPLE_CONVERSATION, keep_last_n=keep,
                               preserve_anchor=True)
    print_conversation(truncated,
                       f"Pair-aware sliding window (keep_last_n={keep}, anchor preserved)")

    print()
    print("Notice that the anchored version begins with the original task")
    print("description — the agent will not lose its goal as the window slides.")


if __name__ == "__main__":
    main()
