from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", ".venv", "venv", "__pycache__"}
TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".ps1",
    ".sh",
    ".txt",
    ".example",
    ".env",
    ".gitignore",
    "",
}


def iter_text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {"LICENSE", "NOTICE"}:
            yield path


class PublicSafetyTests(unittest.TestCase):
    def test_no_personal_identity_strings(self):
        forbidden = [
            "js" + "480",
            "kk" + "ongdon",
            "\uaf41\ub3c8",
            r"C:\Users\js" + "480",
            "OneDrive" + "\\" + "\ubc14\ud0d5",
        ]
        hits = []
        for path in iter_text_files():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in forbidden:
                if needle in text:
                    hits.append(f"{path.relative_to(ROOT)} contains {needle}")
        self.assertEqual([], hits)

    def test_no_real_slack_tokens(self):
        token_pattern = re.compile(r"x(?:oxb|app)-[A-Za-z0-9-]{20,}")
        hits = []
        for path in iter_text_files():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in token_pattern.findall(text):
                if "your" not in match.lower():
                    hits.append(f"{path.relative_to(ROOT)} contains token-like value {match[:8]}...")
        self.assertEqual([], hits)

    def test_env_example_has_public_contract(self):
        env_text = (ROOT / ".env.example").read_text(encoding="utf-8")
        required = [
            "SLACK_BOT_TOKEN",
            "SLACK_APP_TOKEN",
            "SLACK_CHANNEL",
            "USER_SLACK_ID",
            "DEFAULT_AGENT",
            "CLAUDE_EXE",
            "CODEX_EXE",
            "WORKSPACE_ROOT",
            "PROJECT_ROOT",
            "ENABLE_KMS",
            "ENABLE_SMS",
            "ENABLE_KAKAO",
        ]
        missing = [key for key in required if key not in env_text]
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
