"""
Lecture 3.3 — Well-Configured Agent API Call
Agent Engineering

Shows the recommended generation settings for agent development:
low temperature, reasonable max_tokens, clear system prompt.
"""

import anthropic

client = anthropic.Anthropic()

# --- Agent-optimized configuration ---
AGENT_CONFIG = {
    "model": "claude-sonnet-4-5-20250929",
    "max_tokens": 4096,
    "temperature": 0,  # Deterministic — reliable tool decisions
}

SYSTEM_PROMPT = """You are a code analysis assistant. When asked about code,
explain clearly and concisely. If you identify a bug, state the line,
the problem, and the fix."""

# --- Example: analyze some code ---
code_to_analyze = '''
def average(numbers):
    total = 0
    for n in numbers:
        total += n
    return total / len(numbers)
'''

response = client.messages.create(
    **AGENT_CONFIG,
    system=SYSTEM_PROMPT,
    messages=[{
        "role": "user",
        "content": f"What happens if I call this function with an empty list?\n\n```python{code_to_analyze}```"
    }]
)

print("=== Agent Response ===")
print(response.content[0].text)

print("\n=== Configuration Used ===")
print(f"Model:       {AGENT_CONFIG['model']}")
print(f"Temperature: {AGENT_CONFIG['temperature']}")
print(f"Max tokens:  {AGENT_CONFIG['max_tokens']}")
print(f"Stop reason: {response.stop_reason}")
print(f"Tokens:      {response.usage.input_tokens} in, {response.usage.output_tokens} out")

print("\n=== Why These Settings ===")
print("  temperature=0  → Same analysis every time (reliable)")
print("  max_tokens=4096 → Enough room for detailed responses")
print("  Sonnet         → Balanced: good reasoning, reasonable cost")
