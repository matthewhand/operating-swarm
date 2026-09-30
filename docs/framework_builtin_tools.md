# Operating Swarm Framework Built-in Tools

This document lists and describes the built-in tools available to agents and blueprints in the Operating Swarm framework. These tools are accessible via LLM tool-calling or Python code, and are registered in each blueprint's `ToolRegistry`.

## Tool Types
- **LLM Tools**: Tools that are exposed to the LLM via OpenAI function-calling or similar APIs.
- **Python Tools**: Tools registered for direct use by agent Python code (not always exposed to LLMs).

## Example (Codey Blueprint)

### Tool Registration Pattern
Tools are registered in each blueprint using methods like:
- `tool_registry.register_llm_tool(name, description, parameters, handler)`
- `tool_registry.register_python_tool(name, handler, description)`

### Built-in Tools (Typical)

#### 1. `read_file`
- **Type**: LLM Tool
- **Description**: Reads and returns the contents of a file.
- **Parameters**: `{ "path": "string", "encoding": "string (optional)" }`
- **Handler**: Reads file at `path` and returns its contents.

#### 2. `write_file`
- **Type**: LLM Tool
- **Description**: Writes content to a file, overwriting if it exists.
- **Parameters**: `{ "path": "string", "content": "string", "encoding": "string (optional)" }`
- **Handler**: Writes `content` to file at `path`.

#### 3. `semantic_code_search` (or `semantic_search`)
- **Type**: LLM Tool
- **Description**: Performs a semantic (meaning-based) search over code or filesystem contents. Returns relevant files/snippets based on intent, not just keyword.
- **Parameters**: `{ "query": "string", "path": "string (optional)", "max_results": "int (optional)" }`
- **Handler**: Uses embedding or LLM-powered similarity search to find relevant code/files.

#### 4. `code_search` (not semantic)
- **Type**: LLM Tool
- **Description**: Performs a keyword or regex-based search over code/filesystem contents. Returns files/snippets matching the literal query.
- **Parameters**: `{ "keyword": "string", "path": "string (optional)", "max_results": "int (optional)" }`
- **Handler**: Scans files for exact matches to the keyword or pattern.

#### 5. `execute_shell_command`
- **Type**: LLM Tool
- **Description**: Executes a shell command and returns its stdout and stderr.
- **Parameters**: `{ "command": "string" }`
- **Handler**: Runs the command in a shell, returns output and error.

#### 6. `execute_python_code`
- **Type**: LLM Tool
- **Description**: Executes the provided Python code in a sandboxed subprocess and returns stdout, stderr, and exit code.
- **Parameters**: `{ "code": "string" }`
- **Handler**: Runs the code using `python3 -c` in a subprocess, captures output/errors.

#### 7. `execute_nodejs_code`
- **Type**: LLM Tool
- **Description**: Executes the provided Node.js (JavaScript) code in a sandboxed subprocess and returns stdout, stderr, and exit code.
- **Parameters**: `{ "code": "string" }`
- **Handler**: Runs the code using `node -e` in a subprocess, captures output/errors.

---

## How to List All Tools
- Each blueprint's `ToolRegistry` contains all available tools for that blueprint.
- To see the full list, inspect the `register_llm_tool` and `register_python_tool` calls in the blueprint's source code.
- Some blueprints may add custom tools for their specific domain (e.g., Fly.io CLI, git operations, code analysis, etc).

## Extending Tools
- You can add new tools by calling the registration methods in your blueprint's `__init__`.
- Tools can be made available to LLMs (for function-calling) or only to Python code.

---

## Example: Registering a New Tool
```python
# In your blueprint's __init__
def hello_tool(name: str) -> str:
    return f"Hello, {name}!"
self.tool_registry.register_llm_tool(
    name="say_hello",
    description="Say hello to a user by name.",
    parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    handler=hello_tool
)
```

---

## Review and Feedback
Please review this list and the blueprint source code to see if the built-in tools meet your needs. To add or modify tools, edit the appropriate blueprint's `ToolRegistry` setup.

---

# Progressive Tools & Unified Operation Box UX

## Progressive Tool Pattern

For any tool that may take time (e.g., search, analysis), implement it as a generator that **yields progress updates**. Each yield should be a dictionary with at least:

- `matches`: List of results found so far.
- `progress`: Number of files/items processed.
- `total`: Total number of files/items to process (if known).
- `truncated`: Boolean, True if results were cut off due to a limit.
- `done`: Boolean, True if this is the final result.

This enables live, incremental feedback for long-running operations.

**Example (Python):**
```python
def grep_search(pattern, path=".", ...):
    ...
    yield {
        "matches": matches,
        "progress": scanned_files,
        "total": total_files,
        "truncated": False,
        "done": False,
    }
    ...
    yield {
        "matches": matches,
        "progress": scanned_files,
        "total": total_files,
        "truncated": False,
        "done": True,
    }
```

## Enhanced Operation Box UX

Use a rich/ANSI operation box to display live feedback for progressive tools. Each box should include:

- **Title:** e.g., "Searched filesystem", "Analyzed codebase"
- **Result count:** Number of results so far
- **Parameters:** Search/analysis parameters used
- **Progress:** e.g., "123/500 files"
- **Spinner state:** Rotates through `Generating.`, `Generating..`, `Generating...`, `Running...`
- **Emoji (optional):** To visually distinguish the operation

**If an operation takes longer than expected,** update the spinner to say `Generating... Taking longer than expected`.

**Example (Python):**
```python
SPINNER_STATES = ['Generating.', 'Generating..', 'Generating...', 'Running...']

def display_operation_box(
    title, content, style="blue", result_count=None, params=None,
    progress_line=None, total_lines=None, spinner_state=None, emoji=None
):
    # Compose box content...
    console.print(Panel(box_content, title=title, style=style, box=rich_box.ROUNDED))
```

## Search and Analysis UX

- **Always summarize**: Use operation boxes for all search/analysis operations.
- **Show result counts** and parameters.
- **Update line numbers/progress** periodically during long operations.
- **Semantic vs. Code Search**: Clearly label and distinguish outputs for semantic/code search.

## Minimal Example

```python
for update in grep_search(...):
    display_operation_box(
        title="Searching Filesystem",
        content=f"Matches so far: {len(update['matches'])}",
        result_count=len(update['matches']),
        params={k: v for k, v in update.items() if k not in {'matches', 'progress', 'total', 'truncated', 'done'}},
        progress_line=update.get('progress'),
        total_lines=update.get('total'),
        spinner_state=SPINNER_STATES[(update.get('progress', 0) // 10) % len(SPINNER_STATES)],
    )
```

## Best Practices & Troubleshooting

- **Always yield progress** for long-running tools to keep the user informed.
- **Handle exceptions** in progressive tools: yield a final dict with `done: True` and an `error` key if an error occurs, so the UX can display a user-friendly error box.
- **Spinner/operation box**: Always include spinner states, and switch to `Generating... Taking longer than expected` if a threshold (e.g., 10 seconds) is exceeded.
- **Semantic/code search**: Clearly label output type in operation boxes for clarity.
- **Test progressive tools**: Add/maintain tests that assert progressive output and live operation box updates (see `test_progressive_grep_search` in Geese tests for a pattern).

## Implementation Notes

- All built-in blueprints (Geese, Jeeves, Codey) now support this pattern.
- For new tools, follow this structure for seamless CLI/agent UX.
- For semantic/code search, ensure output is clearly labeled and visually distinguished.

---
