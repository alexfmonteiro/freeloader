# freeloader

**Offload Claude's parsing tasks to free LLMs. Save tokens, preserve context.**

When you ask Claude to read a log, summarize a file, or scrape a webpage, it burns expensive Opus tokens on work that a free model handles just as well. `freeloader` intercepts those tasks and routes them to Gemini 2.5 Flash (primary) or Groq Llama 4 Scout (fallback) — both free-tier APIs.

```bash
freeloader 'summarize errors' /var/log/app.log
curl -s https://docs.example.com | freeloader 'extract all API endpoints'
cat big_config.yaml | freeloader 'find all database hostnames and ports'
```

## How it works

1. A Claude Code [skill](https://docs.anthropic.com/en/docs/claude-code/skills) tells Claude to use `freeloader` instead of `Read`/`Grep`/`WebFetch` for parsing tasks
2. An optional [hook](https://docs.anthropic.com/en/docs/claude-code/hooks) hard-blocks `WebFetch` and redirects to `freeloader` so Claude can't bypass it
3. A rule in `CLAUDE.md` enforces the pattern even mid-task (debugging, troubleshooting, etc.)

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

# Check providers
freeloader --list-providers
```

## Claude Code integration

### 1. Skill (automatic delegation)

The installer places the skill at `~/.claude/skills/freeloader/SKILL.md`. Claude Code loads it automatically and will proactively use `freeloader` for parsing tasks.

### 2. CLAUDE.md rule (enforce mid-task)

Add the Token Savings Rule to any project's `CLAUDE.md`:

```bash
cat CLAUDE.md.snippet >> /path/to/your/project/CLAUDE.md
```

### 3. WebFetch hook (hard block)

To prevent Claude from using `WebFetch` at all and force `curl | freeloader`:

```bash
# Copy the hook to your project
cp hooks/block-webfetch.sh /path/to/your/project/.claude/hooks/
chmod +x /path/to/your/project/.claude/hooks/block-webfetch.sh
```

Then add to `.claude/settings.local.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "WebFetch",
        "hooks": [{ "type": "command", "command": ".claude/hooks/block-webfetch.sh" }]
      }
    ]
  }
}
```

## Token savings

| Task | Avg Claude tokens saved | At Opus pricing (~$15/M input) |
|------|------------------------|-------------------------------|
| Feed config parse (78KB) | ~20K tokens | ~$0.30 |
| Log file search | ~5–15K tokens | ~$0.08–$0.23 |
| Web page extraction | ~3–10K tokens | ~$0.05–$0.15 |

Beyond cost: saved tokens stay out of your context window, keeping Claude sharp longer in long sessions.

## Providers

| Provider | Model | Context | Free tier |
|----------|-------|---------|-----------|
| Gemini (primary) | gemini-2.5-flash | 1M tokens | 1,500 req/day |
| Groq (fallback) | llama-4-scout-17b-16e-instruct | 512K tokens | 14,400 req/day |

Providers are tried in order. Transient errors (503, 429, 500) are retried with exponential backoff. Large inputs are auto-truncated per provider limits before sending.

## Configuration

`~/.config/freeloader/config.json`:

```json
{
  "providers": [
    {
      "name": "gemini",
      "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
      "model": "gemini-2.5-flash",
      "api_key": "YOUR_GEMINI_API_KEY"
    },
    {
      "name": "groq",
      "base_url": "https://api.groq.com/openai/v1",
      "model": "llama-4-scout-17b-16e-instruct",
      "api_key": "YOUR_GROQ_API_KEY"
    }
  ]
}
```

Add more providers by appending to the array. Any OpenAI-compatible API works.

## Requirements

- [`uv`](https://github.com/astral-sh/uv) — Python script runner (`brew install uv`)
- `jq` — for the WebFetch hook (`brew install jq`)
- Claude Code with skills support

## License

MIT
