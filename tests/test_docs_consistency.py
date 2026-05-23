from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DocsConsistencyTests(unittest.TestCase):
    def test_expected_release_docs_exist(self):
        required = [
            "README.md",
            "INSTALL_WITH_AI.md",
            "SKILL.md",
            "docs/beginner-tutorial.md",
            "docs/feature-reference.md",
            "docs/e2e-checklist.md",
        ]
        missing = [rel for rel in required if not (ROOT / rel).is_file()]
        self.assertEqual([], missing)

    def test_public_terms_are_consistent(self):
        docs = [
            ROOT / "README.md",
            ROOT / "INSTALL_WITH_AI.md",
            ROOT / "SKILL.md",
            ROOT / "docs" / "beginner-tutorial.md",
            ROOT / "docs" / "feature-reference.md",
            ROOT / "docs" / "e2e-checklist.md",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in docs)
        required_terms = [
            "Claude Code",
            "Codex",
            "local workspace",
            "코덱스",
            "클로드",
            "DEFAULT_AGENT",
            "ENABLE_WORKSPACE",
            "CLAUDE_ALIASES",
            "CODEX_ALIASES",
        ]
        missing = [term for term in required_terms if term not in combined]
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
