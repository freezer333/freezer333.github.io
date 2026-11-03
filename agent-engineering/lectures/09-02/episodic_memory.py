"""
episodic_memory.py — Episodic memory for a tutoring agent.

An episode is one event from a tutoring session: when it happened, which
session and topic it belongs to, what happened, and how it turned out.
Episodes are appended to a JSONL log on disk, so they outlive the session.

The agent finds episodes two ways:

  - Recency:   the most recent episodes ("What happened last session?")
  - Relevance: episodes whose meaning matches a question, found with
               embeddings in a ChromaDB collection (the vector database
               from Module 8)

The log is the source of truth. The ChromaDB collection is an index built
from the log; it can be thrown away and rebuilt at any time.

ChromaDB embeds text with a small local model by default, so no API key
is needed. The first run downloads that model.

Run it:  uv run --with chromadb episodic_memory.py
"""

import json
import os
from datetime import datetime, timezone

import chromadb

LOG = "episodes.jsonl"


# ---------------------------------------------------------------------------
# Storing episodes
# ---------------------------------------------------------------------------

def record(session, topic, event, outcome):
    """Append one episode to the log. The time is captured automatically."""
    episode = {
        "time": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "session": session,
        "topic": topic,
        "event": event,
        "outcome": outcome,
    }
    with open(LOG, "a") as f:
        f.write(json.dumps(episode) + "\n")


def load():
    """Read every episode from the log, oldest first."""
    if not os.path.exists(LOG):
        return []
    with open(LOG) as f:
        return [json.loads(line) for line in f]


# ---------------------------------------------------------------------------
# Finding episodes by recency
# ---------------------------------------------------------------------------

def recent(n=3):
    """The n most recent episodes. The log is append-only, so it is
    already in time order."""
    return load()[-n:]


# ---------------------------------------------------------------------------
# Finding episodes by relevance
# ---------------------------------------------------------------------------

def build_index(episodes):
    """Embed every episode into a ChromaDB collection.

    chromadb.Client() keeps the index in memory. Use
    chromadb.PersistentClient(path="memory") to keep it on disk instead.
    """
    client = chromadb.Client()
    index = client.get_or_create_collection("episodes")
    index.add(
        ids=[str(i) for i in range(len(episodes))],
        documents=[f"{e['event']} {e['outcome']}" for e in episodes],
        metadatas=[{"session": e["session"], "topic": e["topic"]} for e in episodes],
    )
    return index


def relevant(index, episodes, question, k=2):
    """The k episodes whose meaning is closest to the question."""
    result = index.query(query_texts=[question], n_results=k)
    return [episodes[int(i)] for i in result["ids"][0]]


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def show(episodes):
    for e in episodes:
        print(f"  [session {e['session']}, {e['topic']}] {e['event']} {e['outcome']}")
    print()


if __name__ == "__main__":
    if os.path.exists(LOG):
        os.remove(LOG)  # start the demo with an empty log

    # The agent records episodes as sessions happen.
    record(4, "loops", "Wrote range(1, n) and missed the last item.",
           "A hint that range stops before its end value fixed it.")
    record(4, "lists", "Used append() to add a list and got a nested list.",
           "Switched to extend() after comparing the two outputs.")
    record(5, "loops", "A while loop ran one time too many.",
           "Tracing the loop variable on paper found the bug.")
    record(5, "functions", "Printed a result instead of returning it.",
           "Rewrote it with return after seeing None in the output.")
    record(6, "functions", "Called a function before defining it.",
           "Moved the definition above the call.")
    record(6, "recursion", "Wrote factorial with no base case.",
           "Added the base case after seeing a RecursionError.")

    episodes = load()
    print(f"{len(episodes)} episodes in {LOG}\n")

    # Session 7 starts: pick up where the last session left off.
    print("Recency: the 2 most recent episodes")
    show(recent(2))

    # Mid-session, the student asks a question in new words.
    question = "Why does my for loop stop one number early?"
    print(f'Relevance: "{question}"')
    show(relevant(build_index(episodes), episodes, question))
