"""
Lecture 3.3 — Temperature Demo
Agent Engineering

Same prompt sent multiple times at different temperatures.
Demonstrates how temperature affects output variation.
"""

import anthropic

client = anthropic.Anthropic()

PROMPT = "Name a color."
TEMPERATURES = [0.0, 0.3, 1.0]
RUNS_PER_TEMP = 5

print(f'Prompt: "{PROMPT}"')
print("=" * 50)

for temp in TEMPERATURES:
    print(f"\n--- Temperature {temp} ---")
    responses = []

    for i in range(RUNS_PER_TEMP):
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",  # Haiku — fast and cheap for demos
            max_tokens=50,
            temperature=temp,
            messages=[{"role": "user", "content": PROMPT}]
        )
        text = response.content[0].text.strip()
        responses.append(text)
        print(f"  Run {i+1}: {text}")

    unique = len(set(responses))
    print(f"  → {unique} unique responses out of {RUNS_PER_TEMP}")

print("\n" + "=" * 50)
print("\nKey takeaway:")
print("  Temperature 0.0 = same answer every time (deterministic)")
print("  Temperature 0.3 = mostly the same, occasional variation")
print("  Temperature 1.0 = different answers each time (creative)")
print("\n  For agents: use 0 to 0.3. Reliability > creativity.")
