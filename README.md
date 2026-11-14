# freeloader

**Offload Claude's parsing tasks to free LLMs. Save tokens, preserve context.**

When you ask Claude to read a log, summarize a file, or scrape a webpage, it burns expensive Opus tokens on work that a free model handles just as well. `freeloader` intercepts those tasks and routes them to free-tier LLMs — trying each in order until one succeeds.

```bash
freeloader 'summarize errors' /var/log/app.log
curl -s https://docs.example.com | freeloader 'extract all API endpoints'
git diff | freeloader 'what changed? any risks?'
bun test 2>&1 | freeloader 'did tests pass? list failures'
```

## How it works

1. A Claude Code [skill](https://code.claude.com/docs/en/skills) tells Claude to use `freeloader` instead of `Read`/`Grep`/`WebFetch` for parsing tasks
2. Optional [hooks](https://code.claude.com/docs/en/hooks) intercept Read (large files) and WebFetch before Claude uses them
3. A rule in `CLAUDE.md` enforces the pattern even mid-task (debugging, troubleshooting, etc.)
4. Responses are framed as input for a paid LLM — nudging the free model toward maximum conciseness

## Installation

```bash
git clone https://github.com/alexfmonteiro/freeloader.git
cd freeloader
./install.sh
```

The installer asks which hooks to install. To skip the prompt (CI, scripts, agents), pass `--hooks=<1-5>`, for example `./install.sh --hooks=3 /path/to/project`. Without a terminal and without the flag, it installs no hooks.

Then add your API keys to `~/.config/freeloader/config.json`:
- **Gemini**: [aistudio.google.com](https://aistudio.google.com) → Get API Key ([free-tier limits](https://aistudio.google.com/docs/rate-limits))
- **Groq**: [console.groq.com](https://console.groq.com) → API Keys ([free-tier limits](https://console.groq.com/docs/rate-limits))
- **Mistral**: [console.mistral.ai](https://console.mistral.ai) → API Keys ([free-tier limits](https://docs.mistral.ai/admin/billing-usage/usage-limits))
- **Cerebras**: [cloud.cerebras.ai](https://cloud.cerebras.ai) → API Keys ([free-tier limits](https://inference-docs.cerebras.ai/support/rate-limits))

Free-tier quotas change often. Check each provider's rate-limit page for the current numbers.

## Install as a Claude Code plugin

The repo is also a Claude Code [plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces). In your shell:

```bash
claude plugin marketplace add alexfmonteiro/freeloader
claude plugin install freeloader@freeloader
```

The plugin installs only the `freeloader` skill. It enables no hooks.

A plugin can't place files in your home directory, so you still run `./install.sh` for the `freeloader` CLI in `~/.local/bin` and the API-key config in `~/.config/freeloader/config.json`. The installer also copies the skill to `~/.claude/skills/freeloader`. Delete that copy if you use the plugin, so the skill doesn't load twice. The `CLAUDE.md` rule is still a manual step.

| | Plugin | `install.sh` |
|---|---|---|
| `freeloader` skill | yes | yes (`~/.claude/skills/freeloader`) |
| `freeloader` CLI in `~/.local/bin` | no | yes |
| API-key config | no | yes |
| Hooks | no | optional, per project |
| `CLAUDE.md` rule | no | prints the command |

### Turn on hooks

To turn on a hook, add it to `~/.claude/settings.json` (all projects) or to a project's `.claude/settings.local.json`. Point the command at the hook script in your clone of this repo. Use one WebFetch hook at most.

`suggest-webfetch`: WebFetch runs, and Claude gets a freeloader tip.

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "WebFetch", "hooks": [{ "type": "command", "command": "/path/to/freeloader/hooks/suggest-webfetch.sh" }] }
    ]
  }
}
```

`block-webfetch`: WebFetch is blocked, and Claude must use `curl | freeloader`.

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "WebFetch", "hooks": [{ "type": "command", "command": "/path/to/freeloader/hooks/block-webfetch.sh" }] }
    ]
  }
}
```

`intercept-read`: Read is blocked on files over 10KB (see `FREELOADER_MIN_SIZE_KB` below). Ranged reads (`offset`/`limit`), images, PDFs and notebooks pass through.

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Read", "hooks": [{ "type": "command", "command": "/path/to/freeloader/hooks/intercept-read.sh" }] }
    ]
  }
}
```

If the file already has a `PreToolUse` list, add the entry to it. You can also run `./install.sh` in a project and pick the hooks at the prompt. Bypass all hooks with `touch ~/.config/freeloader/disabled`.

## Usage

```bash
# Parse a file
freeloader '<instructions>' '<file_path>'

# Pipe from stdin
cat large.log | freeloader '<instructions>'

# Pass raw text directly
freeloader --text '<raw_text>' '<instructions>'

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
| **suggest-webfetch** | `hooks/suggest-webfetch.sh` | Lets WebFetch through the normal permission flow and adds a token-savings hint to Claude's context |
| **intercept-read** | `hooks/intercept-read.sh` | Blocks Read on files >10KB, redirects to freeloader. Allows ranged reads (`offset`/`limit`), images, PDFs and notebooks |

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

| Task | Avg Claude tokens saved | At $5/M input |
|------|------------------------|---------------|
| Feed config parse (78KB) | ~20K tokens | ~$0.10 |
| Log file search | ~5–15K tokens | ~$0.03–$0.08 |
| Web page extraction | ~3–10K tokens | ~$0.02–$0.05 |
| Test output analysis | ~2–8K tokens | ~$0.01–$0.04 |
| Git diff summary | ~1–5K tokens | ~$0.01–$0.03 |

$5/M is the input price of current Opus models on [Anthropic's pricing page](https://platform.claude.com/docs/en/about-claude/pricing). Set `claude_input_cost_per_m` in the config to match your model.

Beyond cost: saved tokens stay out of your context window, keeping Claude sharp longer in long sessions.

Track your savings with `freeloader --stats`. Find past missed savings with `freeloader --discover`.

## Providers

| Provider | Model | Input freeloader sends | Free tier |
|----------|-------|------------------------|-----------|
| Gemini (primary) | gemini-2.5-flash | ~1M tokens | [rate limits](https://aistudio.google.com/docs/rate-limits) |
| Groq | meta-llama/llama-4-scout-17b-16e-instruct | ~100K tokens | [rate limits](https://console.groq.com/docs/rate-limits) |
| Mistral | mistral-small-latest | ~128K tokens | [rate limits](https://docs.mistral.ai/admin/billing-usage/usage-limits) |
| Cerebras | qwen-3-235b-a22b-instruct-2507 | ~6K tokens (8K default context) | [rate limits](https://inference-docs.cerebras.ai/support/rate-limits) |
| local | any OpenAI-compatible server (LM Studio by default) | ~50K tokens | none |

Providers are tried in order. Any error (rate limit, 5xx, timeout) immediately moves to the next provider — no retries on the same provider. If a response looks unhelpful (refusal phrases, suspiciously short), the next provider is also tried automatically. If all providers fail, the raw input is saved to `~/.local/share/freeloader/tee/` for recovery.

## Configuration

`~/.config/freeloader/config.json`:

```json
{
  "claude_input_cost_per_m": 5.0,
  "providers": [
    {
      "name": "gemini",
      "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
      "model": "gemini-2.5-flash",
      "api_key": "YOUR_GEMINI_API_KEY",
      "max_tokens": 4000
    },
    {
      "name": "groq",
      "base_url": "https://api.groq.com/openai/v1",
      "model": "meta-llama/llama-4-scout-17b-16e-instruct",
      "api_key": "YOUR_GROQ_API_KEY",
      "max_tokens": 4000
    },
    {
      "name": "mistral",
      "base_url": "https://api.mistral.ai/v1",
      "model": "mistral-small-latest",
      "api_key": "YOUR_MISTRAL_API_KEY",
      "max_tokens": 4000
    },
    {
      "name": "cerebras",
      "base_url": "https://api.cerebras.ai/v1",
      "model": "qwen-3-235b-a22b-instruct-2507",
      "api_key": "YOUR_CEREBRAS_API_KEY",
      "max_tokens": 4000
    },
    {
      "name": "local",
      "base_url": "http://127.0.0.1:1234/v1",
      "model": "",
      "api_key": "lm-studio",
      "max_tokens": 4000
    }
  ]
}
```

`max_tokens` caps the response length per provider — forcing brevity and reducing the tokens that do land in Claude's context. Increase it if you need longer summaries.

Add more providers by appending to the array. Any OpenAI-compatible API works.

`claude_input_cost_per_m` is optional. It sets the Claude input price in $/M tokens that `--stats` and `--discover` use for dollar estimates. The default is `5.0`.

## Testing

```bash
uv run --with pytest --with requests pytest tests/ -v
```

Tests cover: bad-distillation guard, interactive passthrough, content truncation, provider fallback (HTTP 503, timeout), tee recovery, stats tracking, session JSONL scanning, missing/directory/unreadable path handling, and end-to-end scenarios with synthetic log/config/CSV/git data.

## Requirements

- [`uv`](https://github.com/astral-sh/uv) — Python script runner (`brew install uv`)
- `jq` — for hooks (`brew install jq`)
- Claude Code with skills support

## License

MIT
