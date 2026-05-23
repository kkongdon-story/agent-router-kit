import importlib.util
import os
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
DAEMON = ROOT / "templates" / "slack-agent-router" / "daemon.py"


def load_daemon():
    try:
        import slack_sdk  # noqa: F401
    except ImportError:
        raise unittest.SkipTest("slack_sdk is not installed")

    temp_dir = tempfile.TemporaryDirectory()
    base = Path(temp_dir.name)
    env_file = base / "slack-agent-router.env"
    env_file.write_text(
        "\n".join(
            [
                "SLACK_BOT_TOKEN=xoxb-test",
                "SLACK_APP_TOKEN=xapp-test",
                "SLACK_CHANNEL=C_TEST",
                "USER_SLACK_ID=U_TEST",
                "BOT_USER_ID=U_BOT",
                "DEFAULT_AGENT=codex",
                f"WORKSPACE_ROOT={base / 'workspace'}",
                f"AGENT_WORKDIR={base / 'workspace'}",
                f"PROJECT_ROOT={base / 'projects'}",
            ]
        ),
        encoding="utf-8",
    )

    old_env = {
        "AGENT_ROUTER_ENV": os.environ.get("AGENT_ROUTER_ENV"),
        "AGENT_ROUTER_HOME": os.environ.get("AGENT_ROUTER_HOME"),
    }
    os.environ["AGENT_ROUTER_ENV"] = str(env_file)
    os.environ["AGENT_ROUTER_HOME"] = str(base / "router-home")

    module_name = "agent_router_daemon_for_tests"
    spec = importlib.util.spec_from_file_location(module_name, DAEMON)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._test_temp_dir = temp_dir
    module._test_old_env = old_env
    return module


class RouterIntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.daemon = load_daemon()

    @classmethod
    def tearDownClass(cls):
        for key, value in cls.daemon._test_old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cls.daemon._test_temp_dir.cleanup()

    def test_capability_question_is_router_specific(self):
        intent = self.daemon.classify_router_intent("slack agent router app으로 뭐 할 수 있어?", "C_TEST")
        self.assertEqual("capability", intent["intent"])
        self.assertTrue(intent["clear_debate"])
        self.assertIn("Claude", self.daemon.router_capability_text())
        self.assertIn("Codex", self.daemon.router_capability_text())

    def test_kakao_command_does_not_become_debate(self):
        self.daemon.save_debate_state(
            "C_TEST",
            {
                "mode": "debate",
                "topic": "이전 토론",
                "next_round_topic": "이전 다음 라운드",
                "updated_epoch": __import__("time").time(),
            },
        )
        intent = self.daemon.classify_router_intent("코덱스, 카카오에서 나에게 보내는 방을 참조해 들어온 할 일 정리해줘", "C_TEST")
        self.assertEqual("workspace_action", intent["intent"])
        self.assertTrue(intent["clear_debate"])

    def test_official_names_and_aliases_route_to_expected_agents(self):
        self.assertEqual("codex", self.daemon.parse_route("코덱스 안녕")[0])
        self.assertEqual("claude", self.daemon.parse_route("클로드 안녕")[0])
        self.assertEqual("codex", self.daemon.parse_route("덱스 안녕")[0])
        self.assertEqual("claude", self.daemon.parse_route("클로 안녕")[0])

    def test_workspace_task_command_is_not_debate(self):
        intent = self.daemon.classify_router_intent("업무 할일 테스트 작업 추가", "C_TEST")
        self.assertEqual("workspace_task", intent["intent"])
        self.assertTrue(intent["clear_debate"])

    def test_debate_continuation_requires_active_debate(self):
        self.daemon.clear_debate_state("C_TEST")
        self.assertEqual("agent_chat", self.daemon.classify_router_intent("다음", "C_TEST")["intent"])

        self.daemon.save_debate_state(
            "C_TEST",
            {
                "mode": "debate",
                "topic": "현재 토론",
                "next_round_topic": "다음 라운드",
                "updated_epoch": __import__("time").time(),
            },
        )
        self.assertEqual("debate_continuation", self.daemon.classify_router_intent("다음", "C_TEST")["intent"])


if __name__ == "__main__":
    unittest.main()
