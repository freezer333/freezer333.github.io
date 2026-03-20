"""
Lecture 3.1 — Retry Pattern with Exponential Backoff
Agent Engineering

Every production agent needs error handling. This script demonstrates
the retry pattern you'll use in every project.
"""

import time
import anthropic

client = anthropic.Anthropic()


def call_with_retry(messages, system="", max_retries=5):
    """Make an API call with exponential backoff on transient errors."""
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=system,
                messages=messages
            )
            return response

        except anthropic.RateLimitError:
            wait_time = 2 ** attempt  # 1s, 2s, 4s, 8s, 16s
            print(f"  Rate limited. Waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
            time.sleep(wait_time)

        except anthropic.APIStatusError as e:
            if e.status_code == 529:  # Overloaded
                wait_time = 2 ** attempt
                print(f"  API overloaded. Waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                raise  # Don't retry on other errors (400, 401, etc.)

        except anthropic.APIConnectionError:
            wait_time = 2 ** attempt
            print(f"  Connection error. Waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
            time.sleep(wait_time)

    raise Exception(f"Max retries ({max_retries}) exceeded")


# --- Use it ---
print("Making API call with retry handling...")
response = call_with_retry(
    messages=[{"role": "user", "content": "Say hello in three languages."}],
    system="You are a helpful assistant."
)

print(f"\nResponse: {response.content[0].text}")
print(f"Stop reason: {response.stop_reason}")
print(f"Tokens: {response.usage.input_tokens} in, {response.usage.output_tokens} out")
