"""
Context Growth Demo — Lecture 4.1

Simulates a multi-step agent task and tracks token usage after each step.
Watch the input token count climb as the conversation history grows.

Usage: uv run context_growth.py
"""

import anthropic

client = anthropic.Anthropic()
MODEL = "claude-haiku-4-5-20251001"  # Haiku for speed/cost in demos

# Simulate an agent task: "Fix the bug in parser.py"
# Each step adds to the conversation history, growing the context
messages = []
system_prompt = """You are a coding assistant. You help fix bugs in Python code.
When asked to fix code, read it carefully, identify the issue, and explain the fix.
Keep responses concise — focus on the problem and solution."""

steps = [
    "Here's a Python function with a bug:\n\ndef parse_csv(filename):\n    with open(filename) as f:\n        lines = f.readlines()\n    results = []\n    for line in lines:\n        fields = line.split(',')\n        results.append(fields)\n    return results\n\nThe function doesn't handle quoted fields correctly. What's wrong?",
    "Can you show me the fixed version?",
    "Now here's another function that uses parse_csv:\n\ndef get_column(filename, col_index):\n    data = parse_csv(filename)\n    return [row[col_index] for row in data]\n\nWhat happens if col_index is out of range?",
    "Add error handling for that case.",
    "Now write a test function that verifies both fixes work correctly.",
]

# Track cumulative tokens across the session
cumulative_input = 0
cumulative_output = 0

print(f"{'Step':<6} {'Input':>8} {'Output':>8} {'Cum Input':>12} {'Cum Output':>12}")
print("-" * 50)

for i, user_msg in enumerate(steps, 1):
    messages.append({"role": "user", "content": user_msg})

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )

    assistant_msg = response.content[0].text
    messages.append({"role": "assistant", "content": assistant_msg})

    # Track token usage
    # In a production agent, this becomes a proper TokenTracker class
    # with history, alerts, and budget enforcement (Modules 17-18)
    cumulative_input += response.usage.input_tokens
    cumulative_output += response.usage.output_tokens

    print(f"{i:<6} {response.usage.input_tokens:>8} {response.usage.output_tokens:>8} "
          f"{cumulative_input:>12} {cumulative_output:>12}")

print()
print(f"Total API calls: {len(steps)}")
print(f"Final input tokens (last call): {response.usage.input_tokens}")
print(f"  — This is the FULL conversation re-sent on the last call")
print(f"Cumulative input tokens (all calls): {cumulative_input}")
print(f"Cumulative output tokens (all calls): {cumulative_output}")
