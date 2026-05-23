import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INPUT_TEMPLATES = ROOT / "templates" / "workspace-inputs"


class WorkspaceInputTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)
        self.scripts = self.workspace / "scripts"
        self.scripts.mkdir(parents=True)
        for name in ("sms_ingest.py", "sms_receiver.py", "kakao_self_ingest.py"):
            shutil.copy2(INPUT_TEMPLATES / name, self.scripts / name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_script(self, script: str, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            [sys.executable, str(self.scripts / script), *args],
            cwd=self.workspace,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

    def test_sms_ingest_works_without_custom_rules_file(self):
        payload = {
            "source": "android_tasker_sms",
            "sender": "010-1234-5678",
            "body": "안녕하세요. 오늘 3시에 미팅 가능할까요?",
            "received_at": "2026-05-24 23.04",
        }
        result = self.run_script("sms_ingest.py", "--json", json.dumps(payload, ensure_ascii=False))
        events = json.loads(result.stdout)
        self.assertEqual(1, len(events))
        self.assertEqual("문의", events[0]["category"])
        self.assertIn("23:04", events[0]["received_at"])

        self.assertTrue((self.workspace / "inputs" / "sms").is_dir())
        self.assertTrue((self.workspace / "processed" / "tasks").is_dir())
        self.assertTrue((self.workspace / "ledger" / "sms" / "sms-events.sqlite").is_file())
        self.assertTrue(list((self.workspace / "inputs" / "sms").glob("*.md")))
        self.assertTrue(list((self.workspace / "processed" / "tasks").glob("*.md")))

    def test_kakao_init_db_uses_installed_workspace_layout(self):
        result = self.run_script("kakao_self_ingest.py", "--init-db")
        self.assertIn("ledger", result.stdout)
        self.assertTrue((self.workspace / "ledger" / "kakao" / "kakao-self-events.sqlite").is_file())


if __name__ == "__main__":
    unittest.main()
