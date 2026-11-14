"""
Tests for the Claude Code PreToolUse hooks in hooks/.

Each hook runs as a subprocess with sample PreToolUse JSON on stdin and a temp HOME.

Run with:
    pytest tests/test_hooks.py -v
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).parent.parent / "hooks"

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="hooks need jq")


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return home


def disable(home):
    kill_switch = home / ".config" / "freeloader" / "disabled"
    kill_switch.parent.mkdir(parents=True)
    kill_switch.touch()


def run_hook(name, payload, home, **extra_env):
    env = {k: v for k, v in os.environ.items() if k != "FREELOADER_MIN_SIZE_KB"}
    env.update(HOME=str(home), **extra_env)
    r = subprocess.run(
        ["bash", str(HOOKS_DIR / name)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 0, r.stderr
    # No output means no decision: the tool goes through the normal permission flow.
    return json.loads(r.stdout)["hookSpecificOutput"] if r.stdout else None


def read_payload(file_path):
    return {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": str(file_path)}}


def webfetch_payload(url="https://example.com/docs"):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "WebFetch",
        "tool_input": {"url": url, "prompt": "summarize"},
    }


class TestInterceptRead:

    def test_large_file_denied(self, home, tmp_path):
        big = tmp_path / "big.log"
        big.write_text("x" * (11 * 1024))
        out = run_hook("intercept-read.sh", read_payload(big), home)
        assert out["hookEventName"] == "PreToolUse"
        assert out["permissionDecision"] == "deny"
        assert "11KB" in out["permissionDecisionReason"]
        assert str(big) in out["permissionDecisionReason"]

    def test_small_file_passes_through(self, home, tmp_path):
        small = tmp_path / "small.txt"
        small.write_text("hello")
        assert run_hook("intercept-read.sh", read_payload(small), home) is None

    def test_missing_file_passes_through(self, home, tmp_path):
        assert run_hook("intercept-read.sh", read_payload(tmp_path / "nope.txt"), home) is None

    def test_no_file_path_passes_through(self, home):
        assert run_hook("intercept-read.sh", {"tool_name": "Read", "tool_input": {}}, home) is None

    def test_threshold_env_var(self, home, tmp_path):
        big = tmp_path / "big.log"
        big.write_text("x" * (11 * 1024))
        assert run_hook("intercept-read.sh", read_payload(big), home, FREELOADER_MIN_SIZE_KB="20") is None

    def test_kill_switch_passes_large_file_through(self, home, tmp_path):
        disable(home)
        big = tmp_path / "big.log"
        big.write_text("x" * (11 * 1024))
        assert run_hook("intercept-read.sh", read_payload(big), home) is None


class TestBlockWebFetch:

    def test_denied(self, home):
        out = run_hook("block-webfetch.sh", webfetch_payload(), home)
        assert out["hookEventName"] == "PreToolUse"
        assert out["permissionDecision"] == "deny"
        assert "freeloader" in out["permissionDecisionReason"]

    def test_kill_switch_passes_through(self, home):
        disable(home)
        assert run_hook("block-webfetch.sh", webfetch_payload(), home) is None


class TestSuggestWebFetch:

    def test_tip_without_permission_decision(self, home):
        out = run_hook("suggest-webfetch.sh", webfetch_payload("https://example.com/a"), home)
        assert out["hookEventName"] == "PreToolUse"
        assert "curl -s https://example.com/a | freeloader" in out["additionalContext"]
        assert "permissionDecision" not in out
        assert "permissionDecisionReason" not in out

    def test_no_url_passes_through(self, home):
        assert run_hook("suggest-webfetch.sh", {"tool_name": "WebFetch", "tool_input": {}}, home) is None

    def test_kill_switch_passes_through(self, home):
        disable(home)
        assert run_hook("suggest-webfetch.sh", webfetch_payload(), home) is None
