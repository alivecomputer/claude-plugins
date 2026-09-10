"""Regression tests for issue #86.

Issue #86: ``alive-context-watch.sh`` injected "Context is at NN%" plus a
rules refresh into the model's context at 20/40/60/80% usage thresholds
(reading ``.alive/.context_pct`` written by the statusline), and at 60%+
also injected the full world key and index. Surfacing a context-budget
countdown makes the model manage its own context instead of the task, and
repeating instructions on a cadence breaks preserved-thinking's
history-editing check. The external-change message also ended with "Ask
the human if they want you to refresh." — a permission-ask for a
read-only action.

These tests pin the removal: a high context percentage must produce no
injection, and the external-change notification must carry neither a
percentage nor a permission-ask.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "alive"
HOOKS = PLUGIN / "hooks" / "scripts"


def make_world(base: Path) -> Path:
    world = base / "world"
    (world / ".alive" / "_squirrels").mkdir(parents=True)
    (world / ".alive" / "preferences.yaml").write_text(
        "github_star_ask: false\n", encoding="utf-8"
    )
    for domain in ("01_Archive", "02_Life", "03_Inbox", "04_Ventures", "05_Experiments"):
        (world / domain).mkdir()
    return world


def run_context_watch(world: Path, session_id: str) -> subprocess.CompletedProcess[str]:
    payload = {
        "session_id": session_id,
        "cwd": str(world),
        "hook_event_name": "UserPromptSubmit",
    }
    env = os.environ.copy()
    env.update(
        {
            "ALIVE_WORLD_ROOT_OVERRIDE": str(world),
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN),
        }
    )
    return subprocess.run(
        ["bash", str(HOOKS / "alive-context-watch.sh")],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=world,
        env=env,
    )


class ContextPercentInjectionRemovedTest(unittest.TestCase):
    """A high .context_pct must not inject anything into model context."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.world = make_world(Path(self._tmp.name))
        self.session_id = f"issue86-pct-{uuid.uuid4().hex[:12]}"
        self._write_session_entry(walnut="null")

    def tearDown(self) -> None:
        Path(f"/tmp/alive-lastcheck-{self.session_id}").unlink(missing_ok=True)
        self._tmp.cleanup()

    def _write_session_entry(self, walnut: str) -> None:
        entry = self.world / ".alive" / "_squirrels" / f"{self.session_id}.yaml"
        entry.write_text(
            f"session_id: {self.session_id}\n"
            f"walnut: {walnut}\n"
            "saves: 0\n"
            "ended: null\n",
            encoding="utf-8",
        )

    def test_high_context_pct_produces_no_injection(self) -> None:
        (self.world / ".alive" / ".context_pct").write_text("85\n", encoding="utf-8")
        (self.world / ".alive" / "key.md").write_text("# world key\n", encoding="utf-8")
        (self.world / ".alive" / "_index.yaml").write_text(
            "walnuts: {}\n", encoding="utf-8"
        )

        result = run_context_watch(self.world, self.session_id)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("ALIVE_REFRESH", result.stdout)
        self.assertNotIn("Context is at", result.stdout)
        self.assertNotIn("world key", result.stdout)

    def test_no_threshold_markers_written(self) -> None:
        (self.world / ".alive" / ".context_pct").write_text("85\n", encoding="utf-8")

        run_context_watch(self.world, self.session_id)

        for threshold in (20, 40, 60, 80):
            marker = Path(f"/tmp/alive-ctx-{self.session_id}-{threshold}")
            self.assertFalse(
                marker.exists(), f"threshold marker {marker} should not be written"
            )
            marker.unlink(missing_ok=True)


class ExternalChangeMessageTest(unittest.TestCase):
    """The change notification names files and does not ask permission."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.world = make_world(Path(self._tmp.name))
        self.session_id = f"issue86-chg-{uuid.uuid4().hex[:12]}"
        self.walnut_dir = self.world / "05_Experiments" / "test-walnut"
        kernel = self.walnut_dir / "_kernel"
        kernel.mkdir(parents=True)
        (kernel / "now.json").write_text(
            json.dumps({"phase": "testing", "squirrel": "another-session"}),
            encoding="utf-8",
        )
        entry = self.world / ".alive" / "_squirrels" / f"{self.session_id}.yaml"
        entry.write_text(
            f"session_id: {self.session_id}\n"
            "walnut: test-walnut\n"
            "saves: 0\n"
            "ended: null\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        Path(f"/tmp/alive-lastcheck-{self.session_id}").unlink(missing_ok=True)
        self._tmp.cleanup()

    def test_change_message_has_no_percentage_and_no_permission_ask(self) -> None:
        # First run establishes the last-checked timestamp.
        first = run_context_watch(self.world, self.session_id)
        self.assertEqual(first.returncode, 0, first.stderr)

        # Simulate another session's save by pushing the mtime forward.
        now_json = self.walnut_dir / "_kernel" / "now.json"
        future = now_json.stat().st_mtime + 5
        os.utime(now_json, (future, future))

        second = run_context_watch(self.world, self.session_id)
        self.assertEqual(second.returncode, 0, second.stderr)

        output = json.loads(second.stdout)
        message = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Another session just saved", message)
        self.assertIn("now.json", message)
        self.assertNotIn("Ask the human", message)
        self.assertNotIn("%", message)


if __name__ == "__main__":
    unittest.main()
