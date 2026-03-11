# freeloader

**Offload Claude's parsing tasks to free LLMs. Save tokens, preserve context.**

When you ask Claude to read a log, summarize a file, or scrape a webpage, it burns expensive Opus tokens on work that a free model handles just as well. `freeloader` intercepts those tasks and routes them to Gemini 2.5 Flash (primary) or Groq Llama 4 Scout (fallback) — both free-tier APIs.

```bash
freeloader 'summarize errors' /var/log/app.log
curl -s https://docs.example.com | freeloader 'extract all API endpoints'
git diff | freeloader 'what changed? any risks?'
bun test 2>&1 | freeloader 'did tests pass? list failures'
```

## How it works

1. A Claude Code [skill](https://docs.anthropic.com/en/docs/claude-code/skills) tells Claude to use `freeloader` instead of `Read`/`Grep`/`WebFetch` for parsing tasks
2. Optional [hooks](https://docs.anthropic.com/en/docs/claude-code/hooks) intercept Read (large files) and WebFetch before Claude uses them
3. A rule in `CLAUDE.md` enforces the pattern even mid-task (debugging, troubleshooting, etc.)
4. Responses are framed as input for a paid LLM — nudging the free model toward maximum conciseness

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/freeloader.git
cd freeloader
./install.sh
```

Then add your API keys to `~/.config/freeloader/config.json`:
- **Gemini**: [aistudio.google.com](https://aistudio.google.com) → Get API Key (free, 1500 req/day)
- **Groq**: [console.groq.com](https://console.groq.com) → API Keys (free, 14.4K req/day)

## Usage

```bash
# Parse a file
freeloader '<instructions>' '<file_path>'

# Pipe from stdin
cat large.log | freeloader '<instructions>'

# Web content
curl -s https://example.com | freeloader 'extract the main content'

# Command output
git diff | freeloader 'summarize changes'
bun test 2>&1 | freeloader 'did tests pass?'

# Check providers and key status
freeloader --list-providers

# Show token savings over time
freeloader --stats

# Find missed savings in Claude Code session history
freeloader --discover
```

## Claude Code integration

### 1. Skill (automatic delegation)

The installer places the skill at `~/.claude/skills/freeloader/SKILL.md`. Claude Code loads it automatically and will proactively use `freeloader` for parsing tasks — including command output like test results and git diffs.

### 2. CLAUDE.md rule (enforce mid-task)

Add the Token Savings Rule to any project's `CLAUDE.md`:

```bash
cat CLAUDE.md.snippet >> /path/to/your/project/CLAUDE.md
```

### 3. Hooks

The installer offers three hook options:

| Hook | File | Behavior |
|------|------|----------|
| **block-webfetch** | `hooks/block-webfetch.sh` | Hard-blocks WebFetch, Claude must use `curl \| freeloader` |
| **suggest-webfetch** | `hooks/suggest-webfetch.sh` | Allows WebFetch but adds a token-savings hint to Claude |
| **intercept-read** | `hooks/intercept-read.sh` | Blocks Read on files >10KB, redirects to freeloader |

Add to `.claude/settings.local.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "WebFetch",
        "hooks": [{ "type": "command", "command": ".claude/hooks/block-webfetch.sh" }]
      },
      {
        "matcher": "Read",
        "hooks": [{ "type": "command", "command": ".claude/hooks/intercept-read.sh" }]
      }
    ]
  }
}
```

Set a custom size threshold for the Read hook (default: 10KB):
```bash
export FREELOADER_MIN_SIZE_KB=20
```

## Token savings

| Task | Avg Claude tokens saved | At Opus pricing (~$15/M input) |
|------|------------------------|-------------------------------|
| Feed config parse (78KB) | ~20K tokens | ~$0.30 |
| Log file search | ~5–15K tokens | ~$0.08–$0.23 |
| Web page extraction | ~3–10K tokens | ~$0.05–$0.15 |
| Test output analysis | ~2–8K tokens | ~$0.03–$0.12 |
| Git diff summary | ~1–5K tokens | ~$0.02–$0.08 |

Beyond cost: saved tokens stay out of your context window, keeping Claude sharp longer in long sessions.

Track your savings with `freeloader --stats`. Find past missed savings with `freeloader --discover`.

## Providers

| Provider | Model | Context | Free tier |
|----------|-------|---------|-----------|
| Gemini (primary) | gemini-2.5-flash | 1M tokens | 1,500 req/day |
| Groq (fallback) | llama-4-scout-17b-16e-instruct | 512K tokens | 14,400 req/day |

Providers are tried in order. Transient errors (503, 429, 500) are retried with exponential backoff. If a response looks unhelpful (refusal phrases, suspiciously short), the next provider is tried automatically. If all providers fail, the raw input is saved to `~/.local/share/freeloader/tee/` for recovery.

## Configuration

`~/.config/freeloader/config.json`:

```json
{
  "providers": [
    {
      "name": "gemini",
      "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
      "model": "gemini-2.5-flash",
      "api_key": "YOUR_GEMINI_API_KEY",
      "max_tokens": 1000
    },
    {
      "name": "groq",
      "base_url": "https://api.groq.com/openai/v1",
      "model": "llama-4-scout-17b-16e-instruct",
      "api_key": "YOUR_GROQ_API_KEY",
      "max_tokens": 1000
    }
  ]
}
```

`max_tokens` caps the response length per provider — forcing brevity and reducing the tokens that do land in Claude's context. Increase it if you need longer summaries.

Add more providers by appending to the array. Any OpenAI-compatible API works.

## Testing

```bash
uv run --with pytest --with requests pytest tests/ -v
```

74 tests covering: bad-distillation guard, interactive passthrough, content truncation, provider fallback (HTTP 503, timeout), tee recovery, stats tracking, session JSONL scanning, and end-to-end scenarios with synthetic log/config/CSV/git data.

## Requirements

- [`uv`](https://github.com/astral-sh/uv) — Python script runner (`brew install uv`)
- `jq` — for hooks (`brew install jq`)
- Claude Code with skills support

## License

MIT
