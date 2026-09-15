---
name: ddg-search
description: Perform web searches using DuckDuckGo (free, no API key) via the bundled search.py script. Use when web search is needed and no API key is available or Brave Search is not preferred.
---

# DuckDuckGo Search

Search the public web through DuckDuckGo's no-JS lite interface. No API key,
no auth, no external dependencies — the bundled script is the source of truth.
Never invent or paraphrase results: run the script and report what it prints.

## Steps

1. Run the script on the query:

   ```bash
   python3 search.py "your search query"
   ```

   Options: `--max N` (results, default 8, cap 10), `--json` (machine-readable
   output with title/url/snippet objects).

2. Report the numbered results with their URLs. Cite the URL when using a
   result as a source.

## Honesty rules

- If the script errors, report the error verbatim rather than guessing what
  the results might have been.
- If it prints `No results.`, say so — do not substitute your own answer for
  a failed search.
- DuckDuckGo may rate-limit aggressive use. If you get an HTTP 403/429, wait
  before retrying; retry at most once per request.

## Implementation notes

- Hits `https://lite.duckduckgo.com/lite/` (HTML form, POST) with a
  15-second timeout; parses result links and snippets with the stdlib
  `html.parser` — no third-party packages required.
- Redirect-style result URLs (`duckduckgo.com/l/?uddg=...`) are decoded to
  the real destination URL before printing.
