"""
Lecture 3.4 — Zero-Shot vs Few-Shot Prompting
Agent Engineering

Demonstrates how including examples in the prompt (few-shot)
dramatically improves output consistency compared to zero-shot.
"""

import anthropic

client = anthropic.Anthropic()

REVIEWS = [
    "The food was decent but the service was painfully slow.",
    "Best pizza I've ever had. Will definitely come back!",
    "It was fine. Nothing special, nothing terrible.",
    "Waited 45 minutes for cold pasta. Never again.",
    "The ambiance was lovely and the dessert was incredible.",
]


def classify_zero_shot(review):
    """Classify sentiment with no examples — just the instruction."""
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=50,
        temperature=0,
        messages=[{
            "role": "user",
            "content": f'Classify the sentiment of this review as positive, negative, or neutral:\n\n"{review}"'
        }]
    )
    return response.content[0].text.strip()


def classify_few_shot(review):
    """Classify sentiment with examples — the model learns the format."""
    prompt = f"""Classify the sentiment of each review as exactly one word: positive, negative, or neutral.

Review: "Absolutely loved it, best meal I've had in years!"
Sentiment: positive

Review: "It was fine. Nothing special."
Sentiment: neutral

Review: "Terrible experience, found a hair in my soup."
Sentiment: negative

Review: "{review}"
Sentiment:"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        temperature=0,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip()


# --- Compare both approaches ---
print("=" * 70)
print(f"{'Review':<55} {'Zero-Shot':<12} {'Few-Shot'}")
print("=" * 70)

for review in REVIEWS:
    zero = classify_zero_shot(review)
    few = classify_few_shot(review)

    # Truncate review for display
    short_review = review[:52] + "..." if len(review) > 55 else review
    print(f"{short_review:<55} {zero:<12} {few}")

print("\n" + "=" * 70)
print("\nNotice:")
print("  - Zero-shot responses may vary in format (full sentences, explanations)")
print("  - Few-shot responses are consistently just the label — exactly one word")
print("  - The few-shot examples taught the model your exact format")
print("  - No training, no fine-tuning — just examples in the prompt")
