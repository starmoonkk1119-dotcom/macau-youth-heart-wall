"""Offline phase 2 tests: real SDK, mocked HTTP, temporary SQLite."""

import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI as RealOpenAI
from streamlit.testing.v1 import AppTest


PROJECT = Path(__file__).resolve().parents[1] / "outputs"
sys.path.insert(0, str(PROJECT))
import ai
import db


VALID = {
    "category": "学业",
    "intensity": 2,
    "ai_reply": "这不是诊断，听起来你有些累了。愿意的话，可以找信任的大人聊聊。",
    "moderation": "safe",
}


class OfflineCase(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.content = json.dumps(VALID, ensure_ascii=False)
        self.finish_reason = "stop"
        self.status_code = 200
        self.network_error = False
        self.no_choices = False
        self.env_patch = patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-fake"})
        self.env_patch.start()
        self.client_patch = patch.object(ai, "OpenAI", side_effect=self.make_client)
        self.constructor = self.client_patch.start()

    def tearDown(self):
        self.client_patch.stop()
        self.env_patch.stop()

    def make_client(self, *args, **kwargs):
        return RealOpenAI(
            *args,
            http_client=httpx.Client(transport=httpx.MockTransport(self.handle)),
            **kwargs,
        )

    def handle(self, request):
        self.requests.append(request)
        if self.network_error:
            raise httpx.ReadTimeout("fake provider failure", request=request)
        if self.status_code != 200:
            return httpx.Response(
                self.status_code,
                json={"error": {"message": "fake provider error"}},
            )
        return httpx.Response(
            200,
            json={
                "id": "fake",
                "object": "chat.completion",
                "created": 0,
                "model": "deepseek-chat",
                "choices": [] if self.no_choices else [{
                    "index": 0,
                    "message": {"role": "assistant", "content": self.content},
                    "finish_reason": self.finish_reason,
                }],
            },
        )

    def result(self, updates=None):
        self.content = json.dumps({**VALID, **(updates or {})}, ensure_ascii=False)
        return ai.analyze_post("这周作业有点多")


class AITests(OfflineCase):
    def test_nfkc_zero_width_and_combining_decorations(self):
        text = "　ＡＢＣ１２３\u200b\u200c\u200d\ufeff自\u0336伤\u20dd\ufe0f　"
        self.assertEqual(ai.normalize_text(text), "ABC123自伤")
        self.assertEqual(ai.normalize_text("z\u0301i\u0308sha"), "zisha")

    def test_valid_result_and_single_normalized_request(self):
        result = ai.analyze_post("ＡＢＣ\u200b\u0336 今天有点累")
        self.assertEqual(result, VALID)
        self.assertEqual(len(self.requests), 1)
        request = self.requests[0]
        self.assertEqual(str(request.url), "https://api.deepseek.com/chat/completions")
        payload = json.loads(request.content)
        self.assertEqual(payload["model"], "deepseek-chat")
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(
            json.loads(payload["messages"][1]["content"])["normalized_text"],
            "ABC 今天有点累",
        )
        self.constructor.assert_called_once_with(
            api_key="test-fake", base_url="https://api.deepseek.com"
        )
        self.assertEqual(request.extensions["timeout"]["read"], 30)

    def test_bad_fields_fail_closed(self):
        bad_updates = [
            {"category": "其他"}, {"category": []}, {"intensity": True},
            {"intensity": "3"}, {"intensity": 0}, {"intensity": 6},
            {"intensity": 2.5}, {"moderation": "approved"},
            {"moderation": ["safe"]}, {"ai_reply": None},
            {"ai_reply": "只有一句话。"},
            {"ai_reply": "听起来你累了。找大人聊聊吧。"},
            {"ai_reply": "这不是诊断。" + "字" * 401 + "。"},
            {"extra_field": "not allowed"},
        ]
        for update in bad_updates:
            with self.subTest(update=update):
                result = self.result(update)
                self.assertEqual(result["moderation"], "need_review")
                self.assertEqual(result["category"], "情绪")
                self.assertEqual(result["intensity"], 3)
                self.assertEqual(result["ai_reply"], ai.FALLBACK_REPLY)

    def test_strict_json_and_missing_fields(self):
        examples = [
            "", "not json", "```json\n{}\n```", "[]", "null", "{}", "true",
            '{"moderation":"crisis","moderation":"safe"}',
            '{"intensity":NaN}', '{"intensity":Infinity}',
            json.dumps({key: value for key, value in VALID.items() if key != "category"}),
        ]
        for content in examples:
            with self.subTest(content=content):
                self.content = content
                self.assertEqual(
                    ai.analyze_post("普通测试")["moderation"], "need_review"
                )

    def test_truncated_safe_response_falls_back(self):
        self.finish_reason = "length"
        self.assertEqual(self.result()["moderation"], "need_review")

    def test_valid_crisis_not_downgraded_by_pinyin(self):
        self.content = json.dumps({**VALID, "moderation": "crisis"})
        self.assertEqual(ai.analyze_post("自伤")["moderation"], "crisis")

    def test_crisis_preserved_despite_bad_other_fields(self):
        for updates in ({"intensity": "5"}, {"ai_reply": None}, {"extra": 1}):
            with self.subTest(updates=updates):
                result = self.result({"moderation": "crisis", **updates})
                self.assertEqual(result["moderation"], "crisis")
                self.assertEqual(result["intensity"], 5)
                self.assertEqual(result["ai_reply"], ai.CRISIS_REPLY)

    def test_truncated_parsed_crisis_not_downgraded(self):
        self.finish_reason = "length"
        self.assertEqual(self.result({"moderation": "crisis"})["moderation"], "crisis")

    def test_pinyin_homophones_ascii_and_traditional(self):
        for text in (
            "紫砂", "自\u200b杀", "自殺", "ｚｉ ｓｈａ",
            "z1i3-sha1", "z\u0301i\u0308sha", "𝕫𝕚𝕤𝕙𝕒",
        ):
            with self.subTest(text=text):
                self.assertEqual(ai.analyze_post(text)["moderation"], "need_review")
        self.assertEqual(len(self.requests), 7)

    def test_sensitive_list_can_be_extended(self):
        with patch.object(ai, "SENSITIVE_WORDS", ai.SENSITIVE_WORDS + ["欺凌"]):
            self.assertEqual(ai.analyze_post("欺凌")["moderation"], "need_review")

    def test_missing_key_returns_fallback_without_http(self):
        with patch.dict(os.environ, {}, clear=True):
            result = ai.analyze_post("普通测试")
        self.assertEqual(result["moderation"], "need_review")
        self.assertEqual(len(self.requests), 0)
        self.constructor.assert_not_called()

    def test_empty_or_invalid_input_has_no_http(self):
        for text in ("", " \n ", "\u200b\u0336", "字" * 3001, None):
            with self.subTest(text_type=type(text).__name__):
                self.assertEqual(
                    ai.analyze_post(text)["moderation"], "need_review"
                )
        self.assertEqual(len(self.requests), 0)

    def test_timeout_has_one_request_not_three(self):
        self.network_error = True
        self.assertEqual(self.result()["moderation"], "need_review")
        self.assertEqual(len(self.requests), 1)

    def test_provider_errors_have_one_request_each(self):
        for code in (401, 429, 500, 503):
            with self.subTest(code=code):
                self.status_code = code
                self.assertEqual(self.result()["moderation"], "need_review")
        self.assertEqual(len(self.requests), 4)

    def test_empty_choices_and_null_content_fall_back(self):
        self.no_choices = True
        self.assertEqual(self.result()["moderation"], "need_review")
        self.no_choices = False
        self.content = None
        self.assertEqual(ai.analyze_post("普通测试")["moderation"], "need_review")


class IntegrationTests(OfflineCase):
    def setUp(self):
        super().setUp()
        self.temporary = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(
            db, "DB_PATH", Path(self.temporary.name) / "test.db"
        )
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.temporary.cleanup()
        super().tearDown()

    def rows(self):
        with db._connection() as connection:
            return connection.execute("SELECT * FROM posts ORDER BY id").fetchall()

    def submit(self, content="测试心声", consent=True):
        app = AppTest.from_file(str(PROJECT / "app.py")).run()
        self.assertEqual(len(app.exception), 0)
        app.text_area[0].input(content)
        if consent:
            app.checkbox[0].check()
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        return app

    def test_safe_pending_and_three_ai_fields_persist(self):
        app = self.submit("今天ＡＢＣ\u200b让我紧张")
        row = self.rows()[0]
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["category"], VALID["category"])
        self.assertEqual(row["intensity"], VALID["intensity"])
        self.assertEqual(row["ai_reply"], VALID["ai_reply"])
        self.assertEqual(row["content"], "今天ＡＢＣ\u200b让我紧张")
        self.assertEqual(row["consent_public"], 1)
        self.assertEqual(app.text[0].value, VALID["ai_reply"])
        self.assertEqual(len(app.success), 1)
        self.assertEqual(app.text_area[0].value, "")
        self.assertFalse(app.checkbox[0].value)
        app.run()
        app.radio[0].set_value("心声墙").run()
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(len(db.get_approved_posts()), 0)

    def test_review_and_crisis_status_mapping(self):
        for moderation, status in (("need_review", "pending"), ("crisis", "crisis")):
            with self.subTest(moderation=moderation):
                self.content = json.dumps({**VALID, "moderation": moderation})
                app = self.submit()
                self.assertEqual(self.rows()[-1]["status"], status)
                self.assertEqual(len(app.warning), int(status == "crisis"))
        self.assertEqual(len(self.requests), 2)

    def test_pinyin_escalation_stays_pending(self):
        self.submit("紫砂")
        self.assertEqual(self.rows()[0]["status"], "pending")
        self.assertEqual(len(self.requests), 1)

    def test_api_failure_still_saves_and_shows_fallback(self):
        self.status_code = 503
        app = self.submit(consent=False)
        row = self.rows()[0]
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["consent_public"], 0)
        self.assertEqual(row["category"], "情绪")
        self.assertEqual(row["intensity"], 3)
        self.assertEqual(row["ai_reply"], ai.FALLBACK_REPLY)
        self.assertEqual(app.text[0].value, ai.FALLBACK_REPLY)

    def test_empty_or_invisible_form_does_not_call_model(self):
        for text in (" \n ", "\u200b\u0336"):
            app = self.submit(text)
            self.assertEqual(len(app.error), 1)
        self.assertEqual(len(self.rows()), 0)
        self.assertEqual(len(self.requests), 0)

    def test_database_failure_preserves_draft(self):
        with patch.object(db, "create_post", side_effect=sqlite3.OperationalError):
            app = self.submit("请保留这段输入")
        self.assertEqual(len(app.error), 1)
        self.assertEqual(app.text_area[0].value, "请保留这段输入")
        self.assertEqual(len(self.rows()), 0)

    def test_ai_reply_uses_literal_text_not_html(self):
        reply = "这不是诊断，<script>alert(1)</script>。你可以找信任的大人聊聊。"
        self.content = json.dumps({**VALID, "ai_reply": reply})
        app = self.submit()
        self.assertEqual(app.text[0].value, reply)

    def test_existing_posts_untouched_by_init(self):
        db.init_db()
        old_id = db.create_post("第 1 阶段留下的心声", False)
        db.init_db()
        self.submit()
        old = self.rows()[0]
        self.assertEqual(old["id"], old_id)
        self.assertIsNone(old["category"])
        self.assertIsNone(old["intensity"])
        self.assertIsNone(old["ai_reply"])

    def test_new_post_cannot_be_autoapproved(self):
        db.init_db()
        with self.assertRaises(ValueError):
            db.create_post("test", True, status="approved")
        self.assertEqual(len(self.rows()), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
