"""
Lecture 3.1 — Multi-Turn Conversation
Agent Engineering

Demonstrates how the messages array maintains conversation context.
Each exchange adds to the array — this IS the context window.
"""

import anthropic

client = anthropic.Anthropic()

# The messages array starts empty — we build it as we go.
messages = []

def chat(user_message):
    """Send a message and get a response, maintaining conversation history."""
    messages.append({"role": "user", "content": user_message})

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system="You are a concise assistant. Keep answers to 1-2 sentences.",
        messages=messages
    )

    assistant_message = response.content[0].text
    messages.append({"role": "assistant", "content": assistant_message})

    return assistant_message, response.usage


# --- Multi-turn conversation ---
print("=== Turn 1 ===")
reply, usage = chat("What's the capital of France?")
print(f"Assistant: {reply}")
print(f"Tokens used: {usage.input_tokens} in, {usage.output_tokens} out")

print("\n=== Turn 2 ===")
reply, usage = chat("What's its population?")
print(f"Assistant: {reply}")
print(f"Tokens used: {usage.input_tokens} in, {usage.output_tokens} out")
# Note: "its" works because the full conversation history is in context.

print("\n=== Turn 3 ===")
reply, usage = chat("What's the most visited landmark there?")
print(f"Assistant: {reply}")
print(f"Tokens used: {usage.input_tokens} in, {usage.output_tokens} out")
# Notice: input tokens grow with each turn — the entire history is re-sent.

print("\n=== Messages Array (this is the context window) ===")
for i, msg in enumerate(messages):
    role = msg["role"].upper()
    content = msg["content"][:80] + "..." if len(msg["content"]) > 80 else msg["content"]
    print(f"  [{i}] {role}: {content}")
