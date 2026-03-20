"""
Lecture 3.1 — Your First API Call
Agent Engineering

This script makes a basic API call to Claude and examines
the response object. Run it to see what comes back.
"""

import anthropic

client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY from environment

# --- A simple API call ---
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    system="You are a helpful coding assistant.",
    messages=[
        {"role": "user", "content": "What does the map() function do in Python?"}
    ]
)

# --- Examine the response ---
print("=== Response Content ===")
print(response.content[0].text)

print("\n=== Stop Reason ===")
print(response.stop_reason)  # "end_turn" means the model finished naturally

print("\n=== Token Usage ===")
print(f"Input tokens:  {response.usage.input_tokens}")
print(f"Output tokens: {response.usage.output_tokens}")
print(f"Total tokens:  {response.usage.input_tokens + response.usage.output_tokens}")
