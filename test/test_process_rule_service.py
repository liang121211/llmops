import pytest

from internal.service.process_rule_service import ProcessRuleService


class TestProcessRuleService:
    """处理规则服务测试。"""

    def test_get_text_splitter_default(self, app_context):
        import inject

        service = inject.instance(ProcessRuleService)
        rule = {
            "segment": {
                "separators": ["\n\n", "\n"],
                "chunk_size": 500,
                "chunk_overlap": 50,
            }
        }
        splitter = service.get_text_splitter(rule)
        assert splitter._chunk_size == 500
        assert splitter._chunk_overlap == 50

    def test_get_text_splitter_custom(self, app_context):
        import inject

        service = inject.instance(ProcessRuleService)
        rule = {
            "segment": {
                "separators": ["。", "."],
                "chunk_size": 200,
                "chunk_overlap": 20,
            }
        }
        splitter = service.get_text_splitter(rule)
        assert splitter._chunk_size == 200
        assert splitter._chunk_overlap == 20

    def test_pre_process_remove_extra_space(self):
        rule = {
            "pre_process_rules": [
                {"id": "remove_extra_space", "enabled": True},
            ]
        }
        result = ProcessRuleService.pre_process_text("hello   world  \n  foo", rule)
        assert result == "hello world foo"

    def test_pre_process_remove_url_and_email(self):
        rule = {
            "pre_process_rules": [
                {"id": "remove_url_and_email", "enabled": True},
            ]
        }
        text = "visit https://example.com or email test@example.com for info"
        result = ProcessRuleService.pre_process_text(text, rule)
        assert "https://example.com" not in result
        assert "test@example.com" not in result
        assert "visit" in result
        assert "for info" in result

    def test_pre_process_disabled_rule(self):
        rule = {
            "pre_process_rules": [
                {"id": "remove_extra_space", "enabled": False},
            ]
        }
        text = "hello   world"
        result = ProcessRuleService.pre_process_text(text, rule)
        assert result == "hello   world"

    def test_pre_process_both_rules(self):
        rule = {
            "pre_process_rules": [
                {"id": "remove_extra_space", "enabled": True},
                {"id": "remove_url_and_email", "enabled": True},
            ]
        }
        text = "  visit   https://example.com   and  mail@test.com  "
        result = ProcessRuleService.pre_process_text(text, rule)
        assert "  " not in result
        assert "https://" not in result
        assert "@" not in result
