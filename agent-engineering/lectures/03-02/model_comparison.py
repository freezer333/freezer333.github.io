"""
Lecture 3.2 — Model Comparison
Agent Engineering

Same prompt sent to different model tiers. Compare speed, output,
and token usage across Haiku, Sonnet, and Opus.
"""

import time
import anthropic

client = anthropic.Anthropic()

PROMPT = "Explain what a REST API is in 2-3 sentences."
MODELS = [
    ("claude-haiku-4-5-20251001", "Haiku (fast/cheap)"),
    ("claude-sonnet-4-6", "Sonnet (balanced)"),
    ("claude-opus-4-6", "Opus (frontier)"),
]

print(f'Prompt: "{PROMPT}"\n')
print("=" * 60)

for model_id, label in MODELS:
    start = time.time()

    response = client.messages.create(
        model=model_id,
        max_tokens=256,
        messages=[{"role": "user", "content": PROMPT}]
    )

    elapsed = time.time() - start

    print(f"\n--- {label} ({model_id}) ---")
    print(f"Response: {response.content[0].text}")
    print(f"Time:     {elapsed:.2f}s")
    print(f"Tokens:   {response.usage.input_tokens} in, {response.usage.output_tokens} out")

print("\n" + "=" * 60)
print("\nNotice:")
print("  - Haiku is fastest and cheapest — good for simple tasks and high volume")
print("  - Sonnet balances quality and speed — the default for most agent work")
print("  - Opus is the most capable but slowest and most expensive")
print("  - All three handle this simple task well — for harder tasks, the gap widens")
print("  - The model parameter is just a string — switching is trivial")
