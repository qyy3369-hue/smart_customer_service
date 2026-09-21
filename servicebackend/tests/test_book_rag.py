"""Offline tests for the pharmacology pgvector retrieval path."""

import unittest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.RAG.book_rag import (
    format_pharmacology_context,
    search_pharmacology,
    search_textbooks,
    vector_literal,
)
from app.agent.pharmacist import pharmacist_node


class TestBookRag(unittest.TestCase):
    def test_vector_literal_checks_dimension_and_finite_values(self):
        self.assertEqual(vector_literal([0.5] * 1024).count(","), 1023)
        with self.assertRaises(ValueError):
            vector_literal([0.5] * 512)
        with self.assertRaises(ValueError):
            vector_literal([float("nan")] * 1024)

    def test_context_preserves_pdf_page_provenance(self):
        context = format_pharmacology_context([{
            "book_title": "药理学",
            "edition": "第九版",
            "pdf_page": 101,
            "content": "阿托品为M胆碱受体阻断药。",
        }])
        self.assertIn("PDF第101页", context)
        self.assertIn("阿托品", context)
        self.assertIn("不一定等于书内印刷页码", context)

    @patch("app.RAG.book_rag.embedding_client")
    @patch("app.RAG.book_rag.psycopg.connect")
    def test_retrieval_requires_ready_source(self, connect, client):
        connection = connect.return_value.__enter__.return_value
        connection.execute.return_value.fetchall.return_value = []
        self.assertEqual(search_pharmacology("阿托品"), [])
        client.assert_not_called()

    @patch("app.RAG.book_rag.embedding_client")
    @patch("app.RAG.book_rag.psycopg.connect")
    def test_retrieval_filters_unrelated_results(self, connect, client):
        connection = connect.return_value.__enter__.return_value
        ready_result = MagicMock()
        ready_result.fetchall.return_value = [("pharmacology",)]
        search_result = MagicMock()
        search_result.fetchall.return_value = [
            ("阿托品相关内容", 100, 0, "药理学", "第九版", "book.pdf", 0.22),
            ("无关内容", 101, 0, "药理学", "第九版", "book.pdf", 0.78),
        ]
        connection.execute.side_effect = [ready_result, search_result]
        client.return_value.embeddings.create.return_value.data = [
            MagicMock(embedding=[0.1] * 1024)
        ]
        hits = search_pharmacology("阿托品", limit=2)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["pdf_page"], 100)
        self.assertIn("c.pdf_page >=", connection.execute.call_args.args[0])

    @patch("app.RAG.book_rag.embedding_client")
    @patch("app.RAG.book_rag.psycopg.connect")
    def test_two_books_share_one_query_embedding_and_keep_provenance(self, connect, client):
        connection = connect.return_value.__enter__.return_value
        ready_result = MagicMock()
        ready_result.fetchall.return_value = [("diagnostics",), ("internal_medicine",)]
        diagnostics_result = MagicMock()
        diagnostics_result.fetchall.return_value = [
            ("诊断相关片段", 201, 0, "诊断学", "第9版", "diagnostics.pdf", 0.25)
        ]
        medicine_result = MagicMock()
        medicine_result.fetchall.return_value = [
            ("内科相关片段", 301, 0, "内科学", "第10版", "medicine.pdf", 0.30)
        ]
        connection.execute.side_effect = [ready_result, diagnostics_result, medicine_result]
        client.return_value.embeddings.create.return_value.data = [
            MagicMock(embedding=[0.1] * 1024)
        ]

        result = search_textbooks("头痛持续三小时", ("diagnostics", "internal_medicine"))
        self.assertEqual([hit["book_id"] for hit in result.hits],
                         ["diagnostics", "internal_medicine"])
        self.assertEqual([hit["pdf_page"] for hit in result.hits], [201, 301])
        self.assertEqual(result.unavailable_books, [])
        client.return_value.embeddings.create.assert_called_once()

    def test_unknown_book_is_rejected_before_api_call(self):
        with self.assertRaises(ValueError):
            search_textbooks("头痛", ("not_a_book",))

    @patch("app.RAG.book_rag.embedding_client")
    @patch("app.RAG.book_rag.psycopg.connect")
    def test_multibook_search_drops_distant_cross_book_false_positive(
        self, connect, client
    ):
        connection = connect.return_value.__enter__.return_value
        ready_result = MagicMock()
        ready_result.fetchall.return_value = [("diagnostics",), ("internal_medicine",)]
        diagnostics_result = MagicMock()
        diagnostics_result.fetchall.return_value = [
            ("头痛章节", 79, 0, "诊断学", "第9版", "diagnostics.pdf", 0.40)
        ]
        medicine_result = MagicMock()
        medicine_result.fetchall.return_value = [
            ("高原病中的头痛", 959, 0, "内科学", "第10版", "medicine.pdf", 0.49)
        ]
        connection.execute.side_effect = [ready_result, diagnostics_result, medicine_result]
        client.return_value.embeddings.create.return_value.data = [
            MagicMock(embedding=[0.1] * 1024)
        ]
        result = search_textbooks("额头痛", ("diagnostics", "internal_medicine"))
        self.assertEqual([item["pdf_page"] for item in result.hits], [79])

    @patch("app.agent.pharmacist.save_user_long_memory")
    @patch("app.agent.pharmacist.create_agent")
    @patch("app.agent.pharmacist.search_pharmacology")
    @patch("app.agent.pharmacist.get_user_long_memory", return_value="")
    @patch("app.agent.pharmacist.get_long_term_memory")
    @patch("app.agent.pharmacist.get_model")
    def test_pharmacist_injects_retrieval_into_prompt(
        self, _model, _store, _memory, search, create_agent, _save
    ):
        search.return_value = [{
            "book_title": "药理学",
            "edition": "第九版",
            "pdf_page": 101,
            "content": "阿托品为M胆碱受体阻断药。",
        }]
        agent = MagicMock()
        agent.invoke.return_value = {"messages": [AIMessage(content="阿托品相关说明。") ]}
        create_agent.return_value = agent
        state = {
            "messages": [HumanMessage(content="阿托品有什么作用？")],
            "user_id": "test_user",
            "thread_id": "test_thread",
            "diagnosis": None,
        }
        result = pharmacist_node(state)
        search.assert_called_once_with("阿托品有什么作用？")
        prompt = create_agent.call_args.kwargs["system_prompt"]
        self.assertIn("PDF第101页", prompt)
        self.assertIn("阿托品为M胆碱受体阻断药", prompt)
        self.assertTrue(result["messages"][-1].content.startswith("【药师】"))


if __name__ == "__main__":
    unittest.main()
