"""
联网搜索工具 search_web 的单元测试
使用模拟的 Tavily results 响应验证摘要提取逻辑，不依赖真实网络请求。
"""

import unittest
from unittest.mock import patch
from app.agent.tools import search_web, search_web_sources


class TestSearchWebTool(unittest.TestCase):
    """测试 search_web 工具的功能与异常处理"""

    @patch("app.agent.tools.settings.TAVILY_API_KEY", "test-key")
    @patch("app.agent.tools.tavily.search")
    def test_source_search_keeps_title_url_and_filters_invalid_links(self, mock_search):
        mock_search.return_value = {"results": [
            {"title": "资料 A", "url": "https://example.org/a",
             "content": "相关说明", "published_date": "2026-01-01"},
            {"title": "伪造链接", "url": "javascript:alert(1)", "content": "不可用"},
            {"title": "重复", "url": "https://example.org/a", "content": "重复内容"},
        ]}
        result = search_web_sources("小腿不适")
        self.assertEqual(result.status, "ready")
        self.assertEqual(len(result.hits), 1)
        self.assertEqual(result.hits[0]["title"], "资料 A")
        self.assertEqual(result.hits[0]["url"], "https://example.org/a")

    @patch("app.agent.tools.settings.TAVILY_API_KEY", "test-key")
    @patch("app.agent.tools.tavily.search", side_effect=RuntimeError("offline"))
    def test_source_search_failure_is_not_evidence(self, _mock_search):
        result = search_web_sources("小腿不适")
        self.assertEqual(result.status, "error")
        self.assertEqual(result.hits, [])

    @patch("app.agent.tools.tavily.search")
    def test_extract_summaries_from_standard_tavily_results(self, mock_search):
        """
        验证能够正确从 Tavily 返回的 'results' 列表中提取摘要 (content 字段)
        """
        mock_search.return_value = {
            "query": "阿司匹林适应症",
            "follow_up_questions": None,
            "answer": None,
            "images": [],
            "results": [
                {
                    "title": "阿司匹林临床应用指南",
                    "url": "https://example.com/guide",
                    "content": "阿司匹林主要用于解热、镇痛、抗炎，以及抑制血小板聚集预防心脑血管疾病。",
                    "score": 0.95,
                    "raw_content": None,
                },
                {
                    "title": "阿司匹林说明书与用法用量",
                    "url": "https://example.com/drug",
                    "content": "口服吸收迅速而完全，用于缓解轻度或中度疼痛。",
                    "score": 0.88,
                    "raw_content": None,
                },
            ],
            "response_time": 0.32,
        }

        # 通过 tool.invoke 调用（模拟 LangChain Agent 调用方式）
        result = search_web.invoke("阿司匹林适应症")

        # 验证调用参数
        mock_search.assert_called_once_with("阿司匹林适应症", max_results=3)

        # 验证提取的摘要
        expected = (
            "阿司匹林主要用于解热、镇痛、抗炎，以及抑制血小板聚集预防心脑血管疾病。\n"
            "口服吸收迅速而完全，用于缓解轻度或中度疼痛。"
        )
        self.assertEqual(result, expected)

    @patch("app.agent.tools.tavily.search")
    def test_search_web_invoke_dict_args(self, mock_search):
        """
        验证通过字典参数 invoke({"query": "..."}) 也能正常提取摘要
        """
        mock_search.return_value = {
            "results": [
                {
                    "title": "高血压日常管理",
                    "content": "保持低盐饮食，每天食盐摄入量建议少于5克。",
                }
            ]
        }

        result = search_web.invoke({"query": "高血压管理"})
        mock_search.assert_called_once_with("高血压管理", max_results=3)
        self.assertEqual(result, "保持低盐饮食，每天食盐摄入量建议少于5克。")

    @patch("app.agent.tools.tavily.search")
    def test_search_web_empty_results(self, mock_search):
        """
        验证当 results 列表为空时，返回 '未找到相关的信息'
        """
        mock_search.return_value = {
            "query": "冷门罕见病关键词",
            "results": [],
        }

        result = search_web.invoke("冷门罕见病关键词")
        self.assertEqual(result, "未找到相关的信息")

    @patch("app.agent.tools.tavily.search")
    def test_search_web_filters_empty_and_whitespace_content(self, mock_search):
        """
        验证过滤掉空字符串、纯空白或缺少 content 字段的脏数据
        """
        mock_search.return_value = {
            "results": [
                {"title": "无内容项", "content": ""},
                {"title": "纯空格项", "content": "   \n\t  "},
                {"title": "有效摘要项", "content": "  布洛芬为解热镇痛类非处方药。  "},
                {"title": "缺少content键项", "url": "https://example.com"},
                "非字典项",
            ]
        }

        result = search_web.invoke("布洛芬")
        # 应该只保留有效项并去除首尾空白
        self.assertEqual(result, "布洛芬为解热镇痛类非处方药。")

    @patch("app.agent.tools.tavily.search")
    def test_search_web_backward_compatibility_with_result_field(self, mock_search):
        """
        验证兼容旧版或第三方 mock 可能使用的单数 'result' 字段
        """
        mock_search.return_value = {
            "result": [
                {"content": "这是单数 result 字段提取的摘要内容"}
            ]
        }

        result = search_web.invoke("测试兼容")
        self.assertEqual(result, "这是单数 result 字段提取的摘要内容")

    @patch("app.agent.tools.tavily.search")
    def test_search_web_handles_api_exception(self, mock_search):
        """
        验证当 Tavily API 抛出异常时，能够优雅捕获并返回错误提示，不导致崩溃
        """
        mock_search.side_effect = Exception("API rate limit exceeded or network down")

        result = search_web.invoke("异常测试")
        self.assertTrue(result.startswith("搜索出错："))
        self.assertIn("API rate limit exceeded or network down", result)


if __name__ == "__main__":
    unittest.main()
