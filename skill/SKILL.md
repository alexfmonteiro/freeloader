---
name: freeloader
description: >
  Use proactively for ALL file parsing, log analysis, web content extraction, data searching, and summarization tasks.
  Triggers: reading/summarizing ANY file for extraction purposes, parsing logs of any size, scraping/summarizing a webpage,
  extracting fields from configs or API responses, searching for patterns in file content, grep-like operations on text.
  Do NOT trigger when the task requires code changes, writing code, or reasoning about code structure/logic.
version: 1.0.0
---

# Freeloader Skill

Use this skill when the task is primarily **reading, searching, or transforming content** — not writing or modifying code.
Delegate to a free cloud LLM so you only see a concise result, saving Claude tokens.

## When to delegate (ALWAYS for these)

- Reading a file to extract, summarize, or search it — **any size**
- Searching for patterns, keywords, or specific data in file content
- Parsing logs, raw API responses, data exports, HTML dumps, configs
- Fetching and summarizing web content
- Extracting fields, counting occurrences, classifying content
- Any task where you would otherwise Read a file just to grep/filter/summarize it

## When NOT to delegate

- The task requires code changes — reason about it yourself
- You need to understand code structure, logic, or architecture (use Read/Grep directly)
- The user explicitly asks you to read and reason about the file yourself
- You need structured output that feeds directly into another tool call

## How to use

Run `freeloader` via Bash:

```bash
# From a file
freeloader '<instructions>' '<file_path>'

# From piped output / web content
curl -s https://example.com/page | freeloader '<instructions>'

# Explicit stdin marker
cat file.log | freeloader '<instructions>' -

# See configured providers and key status
freeloader --list-providers
```

## Provider fallback

Tries Gemini 2.5 Flash first, falls back to Groq Llama 4 Scout on error/rate-limit.
Config at `~/.config/freeloader/config.json`.

## Examples

```bash
# Search a log file for errors
freeloader "Find all ERROR-level entries with timestamps and messages. Format as a numbered list." /var/log/app.log

# Extract from a web page
curl -s https://example.com/docs | freeloader "Extract all API endpoint URLs and their HTTP methods."

# Parse a config
freeloader "List all database connection strings and port numbers with their key names." config.yaml

# Search a data file
freeloader "Find all rows where status is 'failed' and list the associated IDs." data.csv
```
