"""
Selective Preservation — Lecture 7.2

Keeps messages that matter regardless of age. Combines:

- Structural anchors        (the first user message)
- Heuristic tagging         (assistant turns calling state-mutating tools)
- Explicit tagging          (messages flagged with `important: True`)
- Recency                   (the last N exchanges)
- Pair integrity            (every kept tool_use brings its tool_result)
- Alternating roles         (synthetic acks between adjacent same-role messages)

Run alongside `sliding_window.py` (Lecture 7.1) to compare what each
strategy keeps from the same conversation.

Usage: uv run selective_preservation.py
"""

# Tools whose calls change state in the world. Read-only tools are not in
# this set because their results can be re-fetched cheaply if needed.
MUTATING_TOOLS = {"edit_file", "delete_file", "mkdir", "run_command", "write_file"}


# ---------------------------------------------------------------------------
# Sample conversation. Same shape as Lecture 7.1's sample, with two
# additions:
#   - message [3] is tagged `important: True` (a user constraint stated
#     after the agent asked a clarifying question)
#   - message [10] is tagged `important: True` (a follow-up constraint)
# These tags would have been set by the agent code at the moment the
# messages were appended.
# ---------------------------------------------------------------------------

SAMPLE_CONVERSATION = [
    # [0] anchor — the original task
    {"role": "user", "content": "Refactor the database layer to use connection pooling."},
    # [1] heuristic: assistant calling a read-only tool — not preserved
    {"role": "assistant", "content": [
        {"type": "text", "text": "I'll start by reading the current database module."},
        {"type": "tool_use", "id": "tu_001", "name": "read_file", "input": {"filename": "db.py"}},
    ]},
    # [2] tool_result for [1]
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_001", "content": "import sqlite3\n..."},
    ]},
    # [3] explicit: a user constraint that the sliding window would lose
    {"role": "user", "content": "Use psycopg2's pool — we don't want SQLAlchemy here.",
     "important": True},
    # [4] heuristic: read-only — not preserved
    {"role": "assistant", "content": [
        {"type": "tool_use", "id": "tu_002", "name": "read_file", "input": {"filename": "models/user.py"}},
    ]},
    # [5] tool_result for [4]
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_002", "content": "from db import get_connection\n..."},
    ]},
    # [6] heuristic: assistant calling edit_file — preserved as a decision
    {"role": "assistant", "content": [
        {"type": "text", "text": "Adding the pool now."},
        {"type": "tool_use", "id": "tu_003", "name": "edit_file", "input": {"filename": "db.py", "old_str": "...", "new_str": "..."}},
    ]},
    # [7] tool_result for [6] — pulled in by pair integrity
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_003", "content": "Edited db.py"},
    ]},
    # [8] plain assistant text — not preserved
    {"role": "assistant", "content": [
        {"type": "text", "text": "Done. Pool is wired into db.py."},
    ]},
    # [9] plain user follow-up
    {"role": "user", "content": "Now update models/user.py to use it."},
    # [10] explicit: a follow-up constraint
    {"role": "user", "content": "Make sure the pool is checked back in even on exception.",
     "important": True},
    # [11] heuristic: edit_file — preserved as a decision
    {"role": "assistant", "content": [
        {"type": "tool_use", "id": "tu_004", "name": "edit_file", "input": {"filename": "models/user.py", "old_str": "...", "new_str": "..."}},
    ]},
    # [12] tool_result for [11] — pulled in by pair integrity
    {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "tu_004", "content": "Edited models/user.py"},
    ]},
    # [13] recent — kept by the last-N rule
    {"role": "assistant", "content": [
        {"type": "text", "text": "Updated models/user.py to check connections back into the pool."},
    ]},
]


# ---------------------------------------------------------------------------
# Classifiers
# ---------------------------------------------------------------------------

def is_anchor(msg, index):
    """The first user message is the task description — always preserve."""
    return index == 0 and msg["role"] == "user"


def is_mutating_assistant(msg):
    """Assistant message that called a state-changing tool."""
    if msg["role"] != "assistant":
        return False
    content = msg.get("content")
    if not isinstance(content, list):
        return False
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            if block.get("name") in MUTATING_TOOLS:
                return True
    return False


def is_explicitly_tagged(msg):
    """Message flagged at creation time with `important: True`."""
    return msg.get("important") is True


# ---------------------------------------------------------------------------
# Pair-integrity helper
# ---------------------------------------------------------------------------

def find_pair_partner(messages, index):
    """If `messages[index]` is half of a tool_use / tool_result pair,
    return the index of the matching message. Otherwise return None.

    Pair direction:
      assistant tool_use  -> next user tool_result
      user tool_result    -> previous assistant tool_use
    """
    msg = messages[index]
    content = msg.get("content")
    if not isinstance(content, list):
        return None

    has_tool_use = any(
        isinstance(b, dict) and b.get("type") == "tool_use" for b in content
    )
    has_tool_result = any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content
    )

    if has_tool_use and msg["role"] == "assistant" and index + 1 < len(messages):
        nxt = messages[index + 1]
        if nxt["role"] == "user" and isinstance(nxt.get("content"), list):
            if any(b.get("type") == "tool_result" for b in nxt["content"]
                   if isinstance(b, dict)):
                return index + 1

    if has_tool_result and msg["role"] == "user" and index - 1 >= 0:
        prev = messages[index - 1]
        if prev["role"] == "assistant" and isinstance(prev.get("content"), list):
            if any(b.get("type") == "tool_use" for b in prev["content"]
                   if isinstance(b, dict)):
                return index - 1

    return None


# ---------------------------------------------------------------------------
# Main strategy
# ---------------------------------------------------------------------------

def ensure_alternating_roles(messages):
    """Insert synthetic acks between consecutive same-role messages.

    Identical to the helper in `sliding_window.py` (Lecture 7.1). Lab 5
    will pull both this function and `find_pair_partner` into a shared
    `context_management.py` module so all strategies import them.

    The Anthropic API requires roles to alternate. Selective preservation
    pulls a non-contiguous subset out of the conversation, so two
    important messages of the same role often end up adjacent. This pass
    inserts a brief acknowledgment of the opposite role between them.
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


def selective_preserve(messages, keep_last_n=4):
    """Keep anchors, decisions, explicit tags, recent N, and all pair partners.

    Order is preserved. Returns a new list; does not modify the input.
    Synthetic acks are inserted between any consecutive same-role messages
    that survive selection, so the result is always a valid messages array.
    """
    keep = set()

    # Recent N messages.
    start_recent = max(0, len(messages) - keep_last_n)
    for i in range(start_recent, len(messages)):
        keep.add(i)

    # Anchors, mutating decisions, explicit tags.
    for i, msg in enumerate(messages):
        if (is_anchor(msg, i)
                or is_mutating_assistant(msg)
                or is_explicitly_tagged(msg)):
            keep.add(i)

    # Pair integrity: any kept tool_use must keep its tool_result and vice
    # versa. Iterate over a snapshot of `keep` because we mutate it.
    for i in list(keep):
        partner = find_pair_partner(messages, i)
        if partner is not None:
            keep.add(partner)

    selected = [messages[i] for i in sorted(keep)]
    return ensure_alternating_roles(selected)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def summarize_message(msg):
    role = msg["role"]
    content = msg["content"]
    flag = " *important*" if msg.get("important") else ""
    if isinstance(content, str):
        preview = content if len(content) <= 60 else content[:57] + "..."
        return f"{role:9s} | text: {preview!r}{flag}"
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
    return f"{role:9s} | {' + '.join(parts)}{flag}"


def print_conversation(messages, label, original=None):
    print(f"\n{label} ({len(messages)} messages)")
    print("-" * 72)
    for msg in messages:
        # Look up the original index. Synthetic ack messages won't be found
        # in the original — mark those as "[ack]".
        if original is not None:
            try:
                orig_index = original.index(msg)
                prefix = f"[orig {orig_index:2d}]"
            except ValueError:
                prefix = "[ack   ]"
        else:
            prefix = ""
        print(f"  {prefix} {summarize_message(msg)}")


def main():
    print("=" * 72)
    print("Selective Preservation — Lecture 7.2")
    print("=" * 72)

    print_conversation(SAMPLE_CONVERSATION, "Original conversation")

    kept = selective_preserve(SAMPLE_CONVERSATION, keep_last_n=4)
    print_conversation(kept,
                       "Selective preservation (keep_last_n=4)",
                       original=SAMPLE_CONVERSATION)

    print()
    print("Kept set composition:")
    print("  - [0]       anchor (first user message)")
    print("  - [3]       explicit tag (psycopg2 constraint)")
    print("  - [6, 7]    mutating edit_file + its tool_result (pair)")
    print("  - [10]      explicit tag (exception-safe pool)")
    print("  - [11, 12]  mutating edit_file + its tool_result (pair)")
    print("  - [13]      recent (within last 4)")
    print()
    print("Synthetic [ack] messages are inserted between consecutive same-role")
    print("messages so the result satisfies the API's alternating-roles rule.")
    print()
    print("A sliding window of size 4 would have started at index 10 — losing")
    print("the original task description AND the psycopg2 constraint at [3].")


if __name__ == "__main__":
    main()
