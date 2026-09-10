"""Regression tests for the v2-upgrade notice in alive-session-new.sh.

The notice previously fired on already-migrated worlds: detection did not
prune ``01_Archive/`` or migration backups, and a leftover ``03_Inputs/``
alongside the v3 ``03_Inbox/`` counted as a v2 marker. It also injected a
long first-person "MESSAGE FROM THE DEVELOPER" block, which models read
as a prompt-injection attempt in hook output.

Pins: archived/backed-up v2 remnants stay silent, a genuine v2 world gets
a one-line factual notice naming its markers, and the developer-message
block never returns.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "alive"
HOOKS = PLUGIN / "hooks" / "scripts"


def run_session_new(world: Path, session_id: str) -> str:
    payload = {
        "session_id": session_id,
        "cwd": str(world),
        "hook_event_name": "SessionStart",
        "model": "test-model",
        "source": "startup",
        "transcript_path": str(world / "transcript.jsonl"),
    }
    env = os.environ.copy()
    env.update(
        {
            "ALIVE_WORLD_ROOT_OVERRIDE": str(world),
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN),
            "CLAUDE_ENV_FILE": str(world / ".claude-env"),
        }
    )
    result = subprocess.run(
        ["bash", str(HOOKS / "alive-session-new.sh")],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=world,
        env=env,
    )
    output = json.loads(result.stdout)
    return output["hookSpecificOutput"]["additionalContext"]


def make_base_world(base: Path) -> Path:
    world = base / "world"
    (world / ".alive" / "_squirrels").mkdir(parents=True)
    (world / ".alive" / "preferences.yaml").write_text(
        "github_star_ask: false\n", encoding="utf-8"
    )
    return world


class V2UpgradeNoticeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.world = make_base_world(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_genuine_v2_world_gets_one_line_notice(self) -> None:
        kernel = self.world / "04_Ventures" / "thing" / "_kernel"
        (kernel / "_generated").mkdir(parents=True)
        (kernel / "key.md").write_text("# key\n", encoding="utf-8")
        (kernel / "tasks.md").write_text("- task\n", encoding="utf-8")
        (self.world / "04_Ventures" / "thing" / "bundles").mkdir()
        (self.world / "03_Inputs").mkdir()

        context = run_session_new(self.world, "v2-notice-genuine")

        self.assertIn("Legacy world structure detected", context)
        self.assertIn("_kernel/tasks.md", context)
        self.assertIn("/alive:system-upgrade", context)
        self.assertNotIn("MESSAGE FROM THE DEVELOPER", context)
        self.assertNotIn("benslockedin", context)

    def test_migrated_world_with_remnants_stays_silent(self) -> None:
        # v3 world: 03_Inbox exists, walnut is flat-kernel
        (self.world / "03_Inbox").mkdir()
        kernel = self.world / "04_Ventures" / "lab" / "_kernel"
        kernel.mkdir(parents=True)
        (kernel / "key.md").write_text("# key\n", encoding="utf-8")
        # v2 remnants that must NOT trigger: archived walnut with bundles/,
        # a migration backup with bundles/, and a leftover 03_Inputs
        # alongside 03_Inbox.
        archived = self.world / "01_Archive" / "05_Experiments" / "old"
        (archived / "_kernel").mkdir(parents=True)
        (archived / "_kernel" / "key.md").write_text("# key\n", encoding="utf-8")
        (archived / "bundles").mkdir()
        (archived / "_kernel" / "tasks.md").write_text("- old\n", encoding="utf-8")
        backup = self.world / "04_Ventures" / "lab" / ".alive-migrate-backup" / "x"
        (backup / "bundles").mkdir(parents=True)
        (self.world / "03_Inputs" / "_queue").mkdir(parents=True)

        context = run_session_new(self.world, "v2-notice-remnants")

        self.assertNotIn("Legacy world structure detected", context)
        self.assertNotIn("MESSAGE FROM THE DEVELOPER", context)

    def test_clean_v3_world_stays_silent(self) -> None:
        (self.world / "03_Inbox").mkdir()
        kernel = self.world / "04_Ventures" / "thing" / "_kernel"
        kernel.mkdir(parents=True)
        (kernel / "key.md").write_text("# key\n", encoding="utf-8")

        context = run_session_new(self.world, "v2-notice-clean")

        self.assertNotIn("Legacy world structure detected", context)
        self.assertNotIn("MESSAGE FROM THE DEVELOPER", context)


if __name__ == "__main__":
    unittest.main()
