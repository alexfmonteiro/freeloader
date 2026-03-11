"""
freeloader test suite — validates core functionality with synthetic data.

Run with:
    pip install pytest   # or: uv add --dev pytest
    pytest tests/ -v
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Load freeloader as a module ────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent
FREELOADER_SCRIPT = REPO_ROOT / "freeloader"
BINARY = Path.home() / ".local" / "bin" / "freeloader"

from importlib.machinery import SourceFileLoader
_loader = SourceFileLoader("freeloader", str(FREELOADER_SCRIPT))
spec = importlib.util.spec_from_loader("freeloader", _loader)
fl = importlib.util.module_from_spec(spec)
_loader.exec_module(fl)


# ── Synthetic fixture data ─────────────────────────────────────────────────────

# Realistic application log — mix of INFO/DEBUG/WARNING/ERROR lines
APP_LOG = """\
2024-01-15 03:12:01 INFO  JobScheduler: Starting batch job #4821
2024-01-15 03:12:03 DEBUG DataReader: Connecting to source database
2024-01-15 03:12:05 INFO  DataReader: Connection established
2024-01-15 03:12:07 ERROR DataReader: Failed to read table 'orders': timeout after 30s
2024-01-15 03:12:08 WARNING Retry: Attempt 1/3 for table 'orders'
2024-01-15 03:12:39 ERROR DataReader: Failed to read table 'orders': timeout after 30s
2024-01-15 03:12:40 WARNING Retry: Attempt 2/3 for table 'orders'
2024-01-15 03:13:11 ERROR DataReader: Failed to read table 'orders': timeout after 30s
2024-01-15 03:13:12 ERROR Retry: Max retries exceeded for table 'orders'
2024-01-15 03:13:13 INFO  JobScheduler: Job #4821 failed, sending alert
2024-01-15 03:13:15 INFO  AlertService: PagerDuty notification sent to on-call
2024-01-15 03:20:00 INFO  JobScheduler: Starting batch job #4822
2024-01-15 03:20:02 DEBUG DataReader: Connecting to source database
2024-01-15 03:20:04 INFO  DataReader: Connection established
2024-01-15 03:20:06 INFO  DataReader: Successfully read 84,312 rows from 'orders'
2024-01-15 03:20:07 INFO  JobScheduler: Job #4822 completed successfully
"""

# Realistic YAML config with multiple sections and nested keys
CONFIG_YAML = """\
database:
  primary:
    host: prod-db-01.internal
    port: 5432
    name: analytics_db
    user: svc_analytics
  replica:
    host: prod-db-02.internal
    port: 5432
    name: analytics_db
cache:
  host: redis-cluster-01.internal
  port: 6379
  ttl_seconds: 3600
api:
  endpoint: https://api.example.com/v2
  timeout_seconds: 30
  rate_limit: 1000
feature_flags:
  enable_new_pipeline: true
  enable_debug_logging: false
"""

# Realistic CSV with a mix of success/failed job runs
DATA_CSV = """\
id,job_name,status,started_at,finished_at,error_message
1001,ingest-orders,success,2024-01-15T03:00:00Z,2024-01-15T03:05:00Z,
1002,ingest-customers,failed,2024-01-15T03:05:00Z,2024-01-15T03:05:45Z,Connection timeout
1003,transform-orders,success,2024-01-15T03:06:00Z,2024-01-15T03:11:00Z,
1004,transform-customers,failed,2024-01-15T03:12:00Z,2024-01-15T03:12:10Z,Null constraint violation
1005,load-gold-orders,success,2024-01-15T03:13:00Z,2024-01-15T03:18:00Z,
1006,load-gold-customers,failed,2024-01-15T03:19:00Z,2024-01-15T03:19:05Z,Upstream job failed
1007,publish-report,success,2024-01-15T03:20:00Z,2024-01-15T03:22:00Z,
"""

# Realistic git log output
GIT_LOG = """\
a3f92c1 fix: handle null values in customer transform
b8e41d0 feat: add platinum layer for orders
c12f990 refactor: extract common DB utils into helpers module
d456abc chore: bump databricks-sdk to 0.18.0
e789def fix: correct partition key in bronze ingest
f012345 feat: add alerting for failed jobs
g678901 docs: update README with new job structure
h234567 fix: race condition in concurrent job runs
i890abc perf: switch orders ingest to streaming read
j123def chore: clean up deprecated Delta table options
"""

# Realistic test runner output (pytest-style with failures)
TEST_OUTPUT = """\
============================= test session starts ==============================
platform linux -- Python 3.11.0, pytest-7.4.0
collected 47 items

tests/test_ingest.py::test_orders_ingest_basic PASSED                   [  2%]
tests/test_ingest.py::test_orders_ingest_null_handling PASSED            [  4%]
tests/test_ingest.py::test_customers_ingest_basic FAILED                 [  6%]
tests/test_transform.py::test_orders_transform PASSED                    [ 10%]
tests/test_transform.py::test_customers_transform FAILED                 [ 12%]
tests/test_transform.py::test_gold_aggregation PASSED                    [ 14%]

=================================== FAILURES ===================================
__________________ test_customers_ingest_basic ________________________
tests/test_ingest.py:42: in test_customers_ingest_basic
    assert result.count() == 1000
AssertionError: assert 0 == 1000
__________________ test_customers_transform __________________________
tests/test_transform.py:88: in test_customers_transform
    df = transform_customers(spark, bronze_df)
  transform/customers.py:23: in transform_customers
    raise ValueError("Schema mismatch: expected 'email' column not found")
ValueError: Schema mismatch: expected 'email' column not found
============================== 2 failed, 45 passed in 14.32s ==============================
"""

# Synthetic Claude Code session JSONL (tool use calls that bypassed freeloader)
SESSION_JSONL_LINES = [
    json.dumps({
        "type": "message", "role": "assistant",
        "content": [{"type": "tool_use", "id": "tu_01", "name": "Read",
                     "input": {"file_path": "/var/log/large-app.log"}}],
    }),
    json.dumps({
        "type": "message", "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "tu_01", "content": APP_LOG}],
    }),
    json.dumps({
        "type": "message", "role": "assistant",
        "content": [{"type": "tool_use", "id": "tu_02", "name": "WebFetch",
                     "input": {"url": "https://docs.databricks.com/api/reference"}}],
    }),
    json.dumps({
        "type": "message", "role": "assistant",
        "content": [{"type": "tool_use", "id": "tu_03", "name": "Grep",
                     "input": {"pattern": "ERROR", "path": "/var/log/"}}],
    }),
]
SESSION_JSONL = "\n".join(SESSION_JSONL_LINES)


# ── Helpers ────────────────────────────────────────────────────────────────────

def mock_response(content: str):
    """Build a mock requests.Response that looks like a successful LLM API response."""
    m = MagicMock()
    m.json.return_value = {"choices": [{"message": {"content": content}}]}
    m.raise_for_status = MagicMock()
    return m


def make_providers(*names):
    return [
        {"name": n, "api_key": "test-key", "base_url": "http://fake",
         "model": "test-model", "max_tokens": 500}
        for n in names
    ]


# ══════════════════════════════════════════════════════════════════════════════
# UNIT TESTS — pure functions, no I/O
# ══════════════════════════════════════════════════════════════════════════════

class TestBadDistillation:
    """is_bad_distillation() detects useless LLM responses and triggers fallback."""

    def test_please_provide(self):
        assert fl.is_bad_distillation("Please provide more context about what you need.", "x" * 2000)

    def test_i_cannot(self):
        assert fl.is_bad_distillation("I cannot process this input as it appears to be empty.", "x" * 2000)

    def test_as_an_ai(self):
        assert fl.is_bad_distillation("As an AI language model, I need more information.", "x" * 2000)

    def test_im_unable(self):
        assert fl.is_bad_distillation("I'm unable to extract data from this content.", "x" * 2000)

    def test_without_more_context(self):
        assert fl.is_bad_distillation("Without more context I cannot answer that.", "x" * 2000)

    def test_suspiciously_short_for_large_input(self):
        # 5 chars response for 5KB input is suspicious
        assert fl.is_bad_distillation("ok.", "x" * 5000)

    def test_case_insensitive_matching(self):
        assert fl.is_bad_distillation("PLEASE PROVIDE more details about your request.", "x" * 2000)

    def test_good_response_passes_through(self):
        assert not fl.is_bad_distillation("Error at 03:12:07: timeout reading 'orders' table", "x" * 2000)

    def test_nothing_found_is_valid_answer(self):
        # [nothing found] is a legitimate answer — not a refusal
        assert not fl.is_bad_distillation("[nothing found]", "x" * 2000)

    def test_short_response_ok_for_short_input(self):
        # Short response is fine if the input was also short
        assert not fl.is_bad_distillation("ok", "hello world")

    def test_realistic_good_log_response(self):
        good = (
            "1. 03:12:07 ERROR DataReader: timeout reading 'orders'\n"
            "2. 03:12:39 ERROR DataReader: timeout reading 'orders'\n"
            "3. 03:13:12 ERROR Retry: max retries exceeded"
        )
        assert not fl.is_bad_distillation(good, APP_LOG)

    def test_realistic_good_csv_response(self):
        good = "1002: Connection timeout\n1004: Null constraint violation\n1006: Upstream job failed"
        assert not fl.is_bad_distillation(good, DATA_CSV)


class TestInteractiveInput:
    """is_interactive_input() detects prompts requiring human keystrokes."""

    def test_yn_bracket_prompt(self):
        assert fl.is_interactive_input("Continue with install? [Y/n]")

    def test_yn_uppercase_prompt(self):
        assert fl.is_interactive_input("Delete all data? [Y/N]")

    def test_yes_no_parens_prompt(self):
        assert fl.is_interactive_input("Accept terms? (yes/no)")

    def test_password_prompt(self):
        assert fl.is_interactive_input("Enter your sudo password:")

    def test_app_log_is_not_interactive(self):
        assert not fl.is_interactive_input(APP_LOG)

    def test_config_is_not_interactive(self):
        assert not fl.is_interactive_input(CONFIG_YAML)

    def test_csv_is_not_interactive(self):
        assert not fl.is_interactive_input(DATA_CSV)

    def test_test_output_is_not_interactive(self):
        assert not fl.is_interactive_input(TEST_OUTPUT)

    def test_prompt_buried_in_middle_does_not_trigger(self):
        # [Y/n] not in the last 500 chars → no trigger
        content = "output line\n" * 100 + "[Y/n] here\n" + "more output\n" * 60
        assert not fl.is_interactive_input(content)

    def test_prompt_in_tail_triggers(self):
        content = "some long preamble\n" * 10 + "Are you sure you want to proceed? [Y/n]"
        assert fl.is_interactive_input(content)


class TestTruncateContent:
    """truncate_content() respects per-provider context limits."""

    def test_short_content_not_truncated(self):
        content, truncated = fl.truncate_content("hello world", "gemini")
        assert content == "hello world"
        assert not truncated

    def test_gemini_limit_enforced(self):
        big = "x" * (fl.MAX_CONTENT_CHARS["gemini"] + 500)
        result, truncated = fl.truncate_content(big, "gemini")
        assert truncated
        assert len(result) == fl.MAX_CONTENT_CHARS["gemini"]

    def test_groq_limit_enforced(self):
        big = "x" * (fl.MAX_CONTENT_CHARS["groq"] + 500)
        result, truncated = fl.truncate_content(big, "groq")
        assert truncated
        assert len(result) == fl.MAX_CONTENT_CHARS["groq"]

    def test_groq_limit_smaller_than_gemini(self):
        # Groq has a smaller effective context
        assert fl.MAX_CONTENT_CHARS["groq"] < fl.MAX_CONTENT_CHARS["gemini"]

    def test_mistral_limit_enforced(self):
        big = "x" * (fl.MAX_CONTENT_CHARS["mistral"] + 500)
        result, truncated = fl.truncate_content(big, "mistral")
        assert truncated
        assert len(result) == fl.MAX_CONTENT_CHARS["mistral"]

    def test_cerebras_limit_enforced(self):
        big = "x" * (fl.MAX_CONTENT_CHARS["cerebras"] + 500)
        result, truncated = fl.truncate_content(big, "cerebras")
        assert truncated
        assert len(result) == fl.MAX_CONTENT_CHARS["cerebras"]

    def test_cerebras_limit_smaller_than_groq(self):
        # Cerebras default context (8K) is much smaller than Groq
        assert fl.MAX_CONTENT_CHARS["cerebras"] < fl.MAX_CONTENT_CHARS["groq"]

    def test_unknown_provider_uses_default(self):
        big = "x" * (fl.DEFAULT_MAX_CHARS + 500)
        result, truncated = fl.truncate_content(big, "unknown_provider_xyz")
        assert truncated
        assert len(result) == fl.DEFAULT_MAX_CHARS


class TestFindToolUses:
    """_find_tool_uses() recursively extracts tool_use blocks from session JSONL objects."""

    def test_top_level_tool_use(self):
        obj = {"type": "tool_use", "name": "Read", "input": {"file_path": "/foo"}}
        result = fl._find_tool_uses(obj)
        assert len(result) == 1
        assert result[0]["name"] == "Read"

    def test_nested_in_content_array(self):
        obj = {"message": {"content": [{"type": "tool_use", "name": "WebFetch", "input": {}}]}}
        result = fl._find_tool_uses(obj)
        assert len(result) == 1
        assert result[0]["name"] == "WebFetch"

    def test_multiple_tool_uses_in_content(self):
        obj = {"content": [
            {"type": "tool_use", "name": "Read", "input": {}},
            {"type": "tool_use", "name": "Grep", "input": {}},
        ]}
        result = fl._find_tool_uses(obj)
        names = [r["name"] for r in result]
        assert "Read" in names
        assert "Grep" in names

    def test_realistic_session_line(self):
        line = json.loads(SESSION_JSONL_LINES[0])
        result = fl._find_tool_uses(line)
        assert len(result) == 1
        assert result[0]["name"] == "Read"

    def test_non_tool_use_types_ignored(self):
        obj = {"type": "text", "text": "hello"}
        assert fl._find_tool_uses(obj) == []

    def test_empty_object(self):
        assert fl._find_tool_uses({}) == []

    def test_empty_list(self):
        assert fl._find_tool_uses([]) == []

    def test_all_session_lines_parsed(self):
        tool_names = []
        for line in SESSION_JSONL_LINES:
            obj = json.loads(line)
            tool_names += [t["name"] for t in fl._find_tool_uses(obj)]
        assert "Read" in tool_names
        assert "WebFetch" in tool_names
        assert "Grep" in tool_names


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS — mocked HTTP, real logic
# ══════════════════════════════════════════════════════════════════════════════

class TestCallWithFallback:
    """call_with_fallback() orchestrates provider selection, retries, and guards."""

    @patch("requests.post")
    def test_happy_path_returns_result(self, mock_post):
        mock_post.return_value = mock_response("3 errors found: timeout, retry exceeded, alert sent")
        result, provider = fl.call_with_fallback(make_providers("gemini"), "list errors", APP_LOG)
        assert "timeout" in result
        assert provider == "gemini"

    @patch("requests.post")
    def test_fallback_on_http_503(self, mock_post):
        """First provider returns 503 → immediately tries second provider."""
        import requests as req
        err_resp = MagicMock()
        err_resp.status_code = 503
        http_err = req.exceptions.HTTPError(response=err_resp)
        mock_post.side_effect = [http_err, mock_response("1002, 1004, 1006")]
        result, provider = fl.call_with_fallback(
            make_providers("gemini", "groq"), "list failed IDs", DATA_CSV
        )
        assert "1002" in result
        assert provider == "groq"
        assert mock_post.call_count == 2  # exactly 1 fail + 1 success, no retries

    @patch("requests.post")
    def test_fallback_on_http_429(self, mock_post):
        """Rate-limit (429) on first provider → immediately tries second, no sleep."""
        import requests as req
        err_resp = MagicMock()
        err_resp.status_code = 429
        http_err = req.exceptions.HTTPError(response=err_resp)
        mock_post.side_effect = [http_err, mock_response("prod-db-01, prod-db-02")]
        result, provider = fl.call_with_fallback(
            make_providers("gemini", "groq"), "list DB hosts", CONFIG_YAML
        )
        assert "prod-db-01" in result
        assert provider == "groq"
        assert mock_post.call_count == 2  # no retries on same provider

    @patch("requests.post")
    def test_fallback_on_timeout(self, mock_post):
        """First provider times out → second provider used."""
        import requests as req
        mock_post.side_effect = [req.exceptions.Timeout(), mock_response("prod-db-01, prod-db-02")]
        result, provider = fl.call_with_fallback(
            make_providers("gemini", "groq"), "list DB hosts", CONFIG_YAML
        )
        assert "prod-db-01" in result
        assert provider == "groq"

    @patch("requests.post")
    def test_bad_distillation_triggers_fallback(self, mock_post):
        """First provider returns a refusal → second provider used."""
        mock_post.side_effect = [
            mock_response("I cannot process this input without additional context."),
            mock_response("1002: Connection timeout\n1004: Null constraint violation"),
        ]
        result, provider = fl.call_with_fallback(
            make_providers("gemini", "groq"), "list failed jobs", DATA_CSV
        )
        assert "1002" in result
        assert provider == "groq"

    @patch("requests.post")
    def test_all_providers_fail_writes_tee(self, mock_post):
        """When every provider fails, raw input is saved to a tee file."""
        import requests as req
        mock_post.side_effect = req.exceptions.RequestException("connection refused")
        with tempfile.TemporaryDirectory() as tmpdir:
            tee_dir = Path(tmpdir)
            with patch.object(fl, "TEE_DIR", tee_dir):
                with pytest.raises(SystemExit) as exc:
                    fl.call_with_fallback(make_providers("gemini"), "list errors", APP_LOG)
                assert exc.value.code == 1
                tee_files = list(tee_dir.glob("freeloader-*.txt"))
                assert len(tee_files) == 1
                saved = tee_files[0].read_text()
                assert "ERROR" in saved  # raw input preserved

    @patch("requests.post")
    def test_unconfigured_provider_skipped(self, mock_post):
        """Providers with placeholder API keys are not called."""
        mock_post.return_value = mock_response("done")
        providers = [
            {"name": "unconfigured", "api_key": "YOUR_KEY_HERE", "base_url": "http://fake",
             "model": "m", "max_tokens": 100},
            {"name": "gemini", "api_key": "real-key", "base_url": "http://fake",
             "model": "m", "max_tokens": 100},
        ]
        _, provider = fl.call_with_fallback(providers, "test", "content")
        assert provider == "gemini"
        assert mock_post.call_count == 1  # unconfigured provider was never called

    GOOD_RESPONSE = "3 errors found between 03:12 and 03:13, all 'orders' table read timeouts."

    @patch("requests.post")
    def test_max_tokens_sent_in_payload(self, mock_post):
        """max_tokens from provider config is passed to the API."""
        mock_post.return_value = mock_response(self.GOOD_RESPONSE)
        providers = [{"name": "g", "api_key": "k", "base_url": "http://fake",
                      "model": "m", "max_tokens": 250}]
        fl.call_with_fallback(providers, "summarize", APP_LOG)
        payload = mock_post.call_args[1]["json"]
        assert payload["max_tokens"] == 250

    @patch("requests.post")
    def test_default_max_tokens_used_when_not_set(self, mock_post):
        """If max_tokens not in provider config, DEFAULT_MAX_TOKENS is used."""
        mock_post.return_value = mock_response(self.GOOD_RESPONSE)
        providers = [{"name": "g", "api_key": "k", "base_url": "http://fake", "model": "m"}]
        fl.call_with_fallback(providers, "summarize", APP_LOG)
        payload = mock_post.call_args[1]["json"]
        assert payload["max_tokens"] == fl.DEFAULT_MAX_TOKENS

    @patch("requests.post")
    def test_system_prompt_frames_output_for_paid_ai(self, mock_post):
        """System prompt must tell the free LLM its output goes to a paid AI assistant."""
        mock_post.return_value = mock_response("Result: no issues found in this content.")
        providers = [{"name": "g", "api_key": "k", "base_url": "http://fake",
                      "model": "m", "max_tokens": 100}]
        fl.call_with_fallback(providers, "summarize", "content")
        messages = mock_post.call_args[1]["json"]["messages"]
        system_msg = next(m for m in messages if m["role"] == "system")
        assert "paid" in system_msg["content"].lower()

    @patch("requests.post")
    def test_temperature_is_low(self, mock_post):
        """Temperature must be low (<=0.2) for deterministic, factual extraction."""
        mock_post.return_value = mock_response("Result: no issues found in this content.")
        providers = [{"name": "g", "api_key": "k", "base_url": "http://fake",
                      "model": "m", "max_tokens": 100}]
        fl.call_with_fallback(providers, "summarize", "content")
        payload = mock_post.call_args[1]["json"]
        assert payload["temperature"] <= 0.2

    @patch("requests.post")
    def test_instructions_embedded_in_system_prompt(self, mock_post):
        """User instructions must appear in the system prompt, not as a separate user message."""
        mock_post.return_value = mock_response(self.GOOD_RESPONSE)
        providers = [{"name": "g", "api_key": "k", "base_url": "http://fake",
                      "model": "m", "max_tokens": 100}]
        fl.call_with_fallback(providers, "find all ERROR lines", APP_LOG)
        messages = mock_post.call_args[1]["json"]["messages"]
        system_msg = next(m for m in messages if m["role"] == "system")
        assert "find all ERROR lines" in system_msg["content"]

    @patch("requests.post")
    def test_large_input_truncated_with_note(self, mock_post):
        """Inputs exceeding provider limit are truncated with a note in instructions."""
        mock_post.return_value = mock_response(self.GOOD_RESPONSE)
        huge_content = "log line\n" * 100_000
        providers = [{"name": "groq", "api_key": "k", "base_url": "http://fake",
                      "model": "m", "max_tokens": 100}]
        fl.call_with_fallback(providers, "summarize", huge_content)
        payload = mock_post.call_args[1]["json"]
        system_msg = next(m for m in payload["messages"] if m["role"] == "system")
        assert "truncated" in system_msg["content"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# STATS TRACKING
# ══════════════════════════════════════════════════════════════════════════════

class TestStatsTracking:

    def test_creates_stats_file_on_first_call(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats_file = Path(tmpdir) / "stats.json"
            with patch.object(fl, "STATS_FILE", stats_file):
                fl.track_stats(10_000, 200, "gemini")
            assert stats_file.exists()

    def test_entry_fields_correct(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats_file = Path(tmpdir) / "stats.json"
            with patch.object(fl, "STATS_FILE", stats_file):
                fl.track_stats(10_000, 200, "gemini")
            entry = json.loads(stats_file.read_text())[0]
            assert entry["provider"] == "gemini"
            assert entry["input_chars"] == 10_000
            assert entry["output_chars"] == 200
            assert entry["tokens_consumed"] == 10_000 // fl.CHARS_PER_TOKEN
            assert entry["tokens_saved"] > 0

    def test_tokens_saved_is_input_minus_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats_file = Path(tmpdir) / "stats.json"
            with patch.object(fl, "STATS_FILE", stats_file):
                fl.track_stats(4_000, 400, "gemini")
            entry = json.loads(stats_file.read_text())[0]
            # (4000 - 400) / 4 = 900 tokens saved
            assert entry["tokens_saved"] == 900

    def test_multiple_calls_accumulate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats_file = Path(tmpdir) / "stats.json"
            with patch.object(fl, "STATS_FILE", stats_file):
                fl.track_stats(5_000, 100, "gemini")
                fl.track_stats(8_000, 150, "groq")
                fl.track_stats(3_000, 80, "gemini")
            data = json.loads(stats_file.read_text())
            assert len(data) == 3
            providers = [e["provider"] for e in data]
            assert providers.count("gemini") == 2
            assert providers.count("groq") == 1

    def test_capped_at_1000_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stats_file = Path(tmpdir) / "stats.json"
            existing = [{"ts": "t", "provider": "g", "input_chars": 1, "output_chars": 1,
                         "tokens_consumed": 1, "tokens_saved": 0}] * 1_005
            stats_file.write_text(json.dumps(existing))
            with patch.object(fl, "STATS_FILE", stats_file):
                fl.track_stats(1_000, 50, "gemini")
            data = json.loads(stats_file.read_text())
            assert len(data) == 1_000

    def test_never_raises_on_unwritable_path(self):
        """Stats failure must never crash freeloader — it's best-effort."""
        with patch.object(fl, "STATS_FILE", Path("/nonexistent/dir/stats.json")):
            fl.track_stats(1_000, 50, "gemini")  # must not raise


# ══════════════════════════════════════════════════════════════════════════════
# TEE FILE (raw output recovery)
# ══════════════════════════════════════════════════════════════════════════════

class TestTeeRecovery:

    def test_creates_timestamped_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tee_dir = Path(tmpdir)
            with patch.object(fl, "TEE_DIR", tee_dir):
                path = fl.save_tee("raw content preserved here")
            assert path.exists()
            assert path.name.startswith("freeloader-")
            assert path.suffix == ".txt"
            assert path.read_text() == "raw content preserved here"

    def test_preserves_original_content_exactly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(fl, "TEE_DIR", Path(tmpdir)):
                path = fl.save_tee(APP_LOG)
            assert path.read_text() == APP_LOG

    def test_rotates_old_files_at_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tee_dir = Path(tmpdir)
            # Pre-create TEE_MAX_FILES + 5 old files
            for i in range(fl.TEE_MAX_FILES + 5):
                (tee_dir / f"freeloader-20240101T{i:06d}Z.txt").write_text(f"old-{i}")
            with patch.object(fl, "TEE_DIR", tee_dir):
                fl.save_tee("newest content")
            remaining = list(tee_dir.glob("freeloader-*.txt"))
            assert len(remaining) == fl.TEE_MAX_FILES

    def test_newest_file_survives_rotation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tee_dir = Path(tmpdir)
            for i in range(fl.TEE_MAX_FILES + 3):
                (tee_dir / f"freeloader-20240101T{i:06d}Z.txt").write_text("old")
            with patch.object(fl, "TEE_DIR", tee_dir):
                new_path = fl.save_tee("newest")
            assert new_path.exists()
            assert new_path.read_text() == "newest"


# ══════════════════════════════════════════════════════════════════════════════
# REALISTIC SCENARIO TESTS — synthetic data, mocked HTTP
# ══════════════════════════════════════════════════════════════════════════════

class TestScenarios:
    """End-to-end scenarios simulating real Claude Code delegation tasks."""

    def _providers(self):
        return [{"name": "gemini", "api_key": "key", "base_url": "http://fake",
                 "model": "gemini-2.5-flash", "max_tokens": 1000}]

    @patch("requests.post")
    def test_log_error_extraction(self, mock_post):
        """Parse app.log → extract only ERROR lines, excluding INFO/DEBUG/WARNING."""
        expected = (
            "1. 03:12:07 ERROR DataReader: Failed to read table 'orders': timeout after 30s\n"
            "2. 03:12:39 ERROR DataReader: Failed to read table 'orders': timeout after 30s\n"
            "3. 03:13:11 ERROR DataReader: Failed to read table 'orders': timeout after 30s\n"
            "4. 03:13:12 ERROR Retry: Max retries exceeded for table 'orders'"
        )
        mock_post.return_value = mock_response(expected)
        result, _ = fl.call_with_fallback(
            self._providers(),
            "List only ERROR lines with timestamps. Numbered list.",
            APP_LOG,
        )
        assert "Max retries exceeded" in result
        assert "INFO" not in result
        assert "DEBUG" not in result

    @patch("requests.post")
    def test_config_host_extraction(self, mock_post):
        """Parse config.yaml → extract all database hosts and ports."""
        expected = "prod-db-01.internal:5432 (primary), prod-db-02.internal:5432 (replica)"
        mock_post.return_value = mock_response(expected)
        result, _ = fl.call_with_fallback(
            self._providers(),
            "List all database hostnames and ports.",
            CONFIG_YAML,
        )
        assert "prod-db-01" in result
        assert "prod-db-02" in result
        assert "5432" in result

    @patch("requests.post")
    def test_csv_failure_search(self, mock_post):
        """Parse data.csv → find failed rows with IDs and error messages."""
        expected = (
            "1002 ingest-customers: Connection timeout\n"
            "1004 transform-customers: Null constraint violation\n"
            "1006 load-gold-customers: Upstream job failed"
        )
        mock_post.return_value = mock_response(expected)
        result, _ = fl.call_with_fallback(
            self._providers(),
            "List all rows where status='failed'. Include ID, job_name, error_message.",
            DATA_CSV,
        )
        assert "1002" in result
        assert "1004" in result
        assert "1006" in result
        assert "1001" not in result  # success row must not appear

    @patch("requests.post")
    def test_git_log_summary(self, mock_post):
        """Summarize git log output into bullet points."""
        expected = (
            "- Fixed null handling and race condition\n"
            "- Added platinum layer and alerting\n"
            "- Performance: switched to streaming read\n"
            "- Bumped databricks-sdk, cleaned up deprecated options"
        )
        mock_post.return_value = mock_response(expected)
        result, _ = fl.call_with_fallback(
            self._providers(),
            "Summarize recent changes in 3-5 bullet points.",
            GIT_LOG,
        )
        assert len(result) < len(GIT_LOG)  # must compress
        assert "-" in result  # bullet format

    @patch("requests.post")
    def test_test_output_failure_extraction(self, mock_post):
        """Parse pytest output → extract failing tests and their error messages."""
        expected = (
            "2 failures:\n"
            "1. test_customers_ingest_basic — assert 0 == 1000\n"
            "2. test_customers_transform — ValueError: Schema mismatch: 'email' column not found"
        )
        mock_post.return_value = mock_response(expected)
        result, _ = fl.call_with_fallback(
            self._providers(),
            "Did tests pass? List any failures with test names and error messages.",
            TEST_OUTPUT,
        )
        assert "2" in result
        assert "customers" in result.lower()
        assert "email" in result.lower()

    @patch("requests.post")
    def test_compression_ratio(self, mock_post):
        """Freeloader must produce meaningfully compressed output (core value prop)."""
        compressed = (
            "4 errors 03:12–03:13, all 'orders' table read timeouts. "
            "Max retries exceeded. Job #4821 failed; #4822 succeeded."
        )
        mock_post.return_value = mock_response(compressed)
        result, _ = fl.call_with_fallback(
            self._providers(), "Summarize errors concisely.", APP_LOG
        )
        ratio = len(result) / len(APP_LOG)
        assert ratio < 0.30, f"Expected <30% of input size, got {ratio:.0%}"

    @patch("requests.post")
    def test_nothing_found_signal(self, mock_post):
        """[nothing found] is returned as-is when input has nothing matching."""
        mock_post.return_value = mock_response("[nothing found]")
        result, _ = fl.call_with_fallback(
            self._providers(),
            "Find all CRITICAL-level entries.",
            APP_LOG,  # has no CRITICAL lines
        )
        assert result == "[nothing found]"


# ══════════════════════════════════════════════════════════════════════════════
# CLI TESTS — subprocess calls against installed binary
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not BINARY.exists(), reason="freeloader not installed (~/.local/bin/freeloader)")
class TestCLI:

    def run(self, *args, input_text=None):
        return subprocess.run(
            [str(BINARY), *args],
            input=input_text,
            capture_output=True,
            text=True,
        )

    def test_list_providers_exits_zero(self):
        r = self.run("--list-providers")
        assert r.returncode == 0

    def test_list_providers_shows_gemini(self):
        r = self.run("--list-providers")
        assert "gemini" in r.stdout

    def test_list_providers_shows_max_tokens(self):
        r = self.run("--list-providers")
        assert "max_tokens" in r.stdout

    def test_no_instructions_exits_nonzero(self):
        r = self.run()
        assert r.returncode != 0

    def test_empty_input_exits_nonzero(self):
        r = self.run("summarize", input_text="   \n")
        assert r.returncode != 0
        assert "empty" in r.stderr.lower()

    def test_stats_subcommand_exits_zero(self):
        r = self.run("--stats")
        assert r.returncode == 0

    def test_discover_subcommand_exits_zero(self):
        r = self.run("--discover")
        assert r.returncode == 0

    def test_interactive_passthrough(self):
        """Input ending with [Y/n] must be passed through raw without calling any LLM."""
        r = self.run("process this", input_text="Install package foo? [Y/n]")
        assert r.returncode == 0
        assert "Install package" in r.stdout
        # Must not have hit an LLM (no provider in stderr)
        assert "querying" not in r.stderr

    def test_provider_shown_in_stderr_on_success(self):
        """On success, [via <provider>] must appear in stderr."""
        r = self.run("repeat this back", input_text="hello world")
        if r.returncode == 0:
            assert "via" in r.stderr

    def test_file_input(self):
        """Parse a real file and get a result."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            f.write(APP_LOG)
            f.flush()
            r = self.run("list only ERROR lines as a numbered list", f.name)
        os.unlink(f.name)
        if r.returncode == 0:
            assert r.stdout.strip() != ""
