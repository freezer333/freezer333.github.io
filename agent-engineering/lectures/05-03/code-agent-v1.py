"""
Lecture 5.3 — Code Agent v1: Full Agent Loop with Real Tools
Agent Engineering

A working coding agent. Real implementations of read_file, list_files, and
edit_file backed by the local filesystem. The agent loop runs until the user
quits — tool calls are handled automatically, results are fed back to the
model, and the loop continues until the model produces a text reply.

Usage:
    python code-agent-v1.py

    Type a request at the prompt. Press Enter twice (empty line) to quit.
"""
import os
from dotenv import load_dotenv
import anthropic

load_dotenv()
client = anthropic.Anthropic()

# ─────────────────────────────────────────────
# System prompt
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are a coding assistant. Your job is to help users read,
understand, and modify code files in their project directory.

## Available Tools

**list_files(path)**: List the files and directories at a given path.
Use this to understand the project structure before looking for
specific files. Returns file names and types.

**read_file(filename)**: Read the complete contents of a file. Use
this to understand existing code before making changes. Always read
a file before editing it.

**edit_file(path, old_str, new_str)**: Create or edit a file.
- To create: set old_str to empty string, new_str to file contents.
- To edit: set old_str to exact text to replace, new_str to replacement.
You must read the file first to know what text to use for old_str.

## How to Work

- Read before editing. Never modify a file you haven't read in this session.
- Be concise. Respond with what the user needs, not explanations of your
  process unless the user asks.
- When in doubt, ask. If a request is ambiguous, ask one clarifying question
  before acting.
- Report what you did. After completing a task, briefly confirm what was done.
  Example: "Added the multiply function to math_utils.py on line 12."

## Constraints

- Only access files within the current project directory. Do not
  attempt to read or modify files outside the project.
- Never delete files. If the user asks you to delete something,
  explain that you cannot and suggest alternatives.
- Do not execute code. You can read and write files, but not run them."""

# ─────────────────────────────────────────────
# Tool schemas
# ─────────────────────────────────────────────

TOOLS = [
    {
        "name": "list_files",
        "description": (
            "List the files and directories at a given path. "
            "Use this to understand the project structure before looking for "
            "specific files. Returns file names and types."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to list. Use '.' for the current directory."
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "read_file",
        "description": (
            "Read the complete contents of a file. "
            "Use this to understand existing code before making changes. "
            "Always read a file before editing it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Path to the file to read."
                }
            },
            "required": ["filename"]
        }
    },
    {
        "name": "edit_file",
        "description": (
            "Create or edit a file. "
            "To create: set old_str to empty string, new_str to file contents. "
            "To edit: set old_str to the exact text to replace, new_str to the replacement. "
            "You must read the file first to know what text to use for old_str."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to create or edit."
                },
                "old_str": {
                    "type": "string",
                    "description": "Text to replace. Empty string to create a new file."
                },
                "new_str": {
                    "type": "string",
                    "description": "Replacement text, or full file contents when creating."
                }
            },
            "required": ["path", "old_str", "new_str"]
        }
    }
]

# ─────────────────────────────────────────────
# Real tool implementations
# ─────────────────────────────────────────────

def list_files(path):
    """Return a directory listing with file names and types."""
    try:
        entries = os.listdir(path)
        lines = []
        for entry in sorted(entries):
            full = os.path.join(path, entry)
            kind = "dir" if os.path.isdir(full) else "file"
            lines.append(f"{entry}  [{kind}]")
        return "\n".join(lines) if lines else "(empty directory)"
    except FileNotFoundError:
        return f"Error: directory not found: {path}"
    except PermissionError:
        return f"Error: permission denied: {path}"


def read_file(filename):
    """Return the complete contents of a file."""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"Error: file not found: {filename}"
    except PermissionError:
        return f"Error: permission denied: {filename}"
    except UnicodeDecodeError:
        return f"Error: file is not readable as text: {filename}"


def edit_file(path, old_str, new_str):
    """Create a new file or replace the first occurrence of old_str in an existing file."""
    if old_str == "":
        # Create (or overwrite) the file
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_str)
            return f"Created {path}"
        except PermissionError:
            return f"Error: permission denied: {path}"
    else:
        # Edit: replace first occurrence
        try:
            with open(path, "r", encoding="utf-8") as f:
                contents = f.read()
        except FileNotFoundError:
            return f"Error: file not found: {path}. Read the file before editing it."
        if old_str not in contents:
            return f"Error: text not found in {path}:\n{old_str!r}"
        updated = contents.replace(old_str, new_str, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(updated)
        return f"Edited {path}"


def dispatch_tool(name, inputs):
    """Call the named tool and return its result as a string."""
    print(f"  [tool call] {name}({', '.join(f'{k}={v!r}' for k, v in inputs.items())})")
    if name == "list_files":
        result = list_files(**inputs)
    elif name == "read_file":
        result = read_file(**inputs)
    elif name == "edit_file":
        result = edit_file(**inputs)
    else:
        result = f"Error: unknown tool: {name}"
    print(f"  [tool result] {result[:120]}{'...' if len(result) > 120 else ''}")
    return result

# ─────────────────────────────────────────────
# Agent loop
# ─────────────────────────────────────────────

def run_agent():
    messages = []
    print("Coding Agent — type your request. Empty line to quit.\n")

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            print("Goodbye.")
            break

        messages.append({"role": "user", "content": user_input})

        # Inner loop: keep calling the API until the model produces a text reply
        while True:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages
            )

            # Append the full assistant response to history
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "tool_use":
                # Execute every tool the model requested, collect results
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = dispatch_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })

                # Feed all results back in a single user turn
                messages.append({"role": "user", "content": tool_results})

            else:
                print(response.stop_reason)
                # Model is done — print the text reply
                for block in response.content:
                    if block.type == "text":
                        print(f"\nAssistant: {block.text}\n")
                break  # Back to the outer loop for the next user message


if __name__ == "__main__":
    run_agent()
