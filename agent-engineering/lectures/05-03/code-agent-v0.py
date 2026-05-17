"""
Lecture 5.3 — Code Agent v0: System Prompt + Stub Tools
Agent Engineering

Demonstrates the complete system prompt from the lecture wired to real tool
definitions. Tools are stubs — they print that they were called but do nothing.

One prompt in, one response out. Clearly shows whether the model returned a
tool call or a reply to the user.
"""
from dotenv import load_dotenv
import anthropic

load_dotenv()
client = anthropic.Anthropic()

# ─────────────────────────────────────────────
# System prompt (built slide by slide in 5.3)
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are a coding assistant. Your job is to help users read,
understand, and modify code files in their project directory.

## Available Tools

**read_file(filename)**: Read the complete contents of a file. Use
this to understand existing code before making changes. Always read
a file before editing it.

**list_files(path)**: List the files and directories at a given path.
Use this to understand the project structure before looking for
specific files. Returns file names and types.

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
# Tool schemas (passed to the API)
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
# Stub tool implementations
# ─────────────────────────────────────────────

def list_files(path):
    print(f"  [list_files called] path={path!r}")

def read_file(filename):
    print(f"  [read_file called] filename={filename!r}")

def edit_file(path, old_str, new_str):
    action = "CREATE" if old_str == "" else "EDIT"
    print(f"  [edit_file called] action={action}, path={path!r}")
    print(f"    old_str={old_str!r}")
    print(f"    new_str={new_str!r}")

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

user_input = input("You: ").strip()
if not user_input:
    print("No input provided.")
    exit()

response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    system=SYSTEM_PROMPT,
    tools=TOOLS,
    messages=[{"role": "user", "content": user_input}]
)

print(f"\nStop reason: {response.stop_reason}")
print("-" * 50)

for block in response.content:
    if block.type == "tool_use":
        print(f"\n[TOOL CALL] → {block.name}")
        print(f"  Arguments: {block.input}")
        # Dispatch to the appropriate stub
        if block.name == "list_files":
            list_files(**block.input)
        elif block.name == "read_file":
            read_file(**block.input)
        elif block.name == "edit_file":
            edit_file(**block.input)
    elif block.type == "text":
        print(f"\n[REPLY TO USER]\n{block.text}")
