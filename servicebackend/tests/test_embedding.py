"""
Embedding 模型初始化与调用的单元测试
"""

import unittest
from unittest.mock import patch, MagicMock
from app.config.settings import settings
from app.agent.base import get_embedding_model, get_embeddings


class TestEmbeddingModel(unittest.TestCase):
    """测试 Embedding 模型配置与初始化"""

    def test_settings_has_embedding_model(self):
        """验证 settings 中正确配置了 EMBEDDING_MODEL"""
        self.assertEqual(settings.EMBEDDING_MODEL, "qwen3.7-text-embedding-flash")

    def test_get_embedding_model_instance(self):
        """验证 get_embedding_model 返回正确的 DashScopeEmbeddings 实例和模型名称"""
        emb = get_embedding_model()
        self.assertEqual(emb.model, "qwen3.7-text-embedding-flash")
        # 验证别名一致性
        self.assertIs(get_embeddings, get_embedding_model)

    @patch("dashscope.TextEmbedding.call")
    def test_mock_embed_query(self, mock_call):
        """验证通过 Mock 模拟 DashScope 向量提取逻辑"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.output = {
            "embeddings": [
                {"embedding": [0.1] * 1024, "text_index": 0}
            ]
        }
        mock_call.return_value = mock_response

        emb = get_embedding_model()
        vec = emb.embed_query("测试医疗文本")
        self.assertEqual(len(vec), 1024)
        mock_call.assert_called_once()


if __name__ == "__main__":
    unittest.main()
