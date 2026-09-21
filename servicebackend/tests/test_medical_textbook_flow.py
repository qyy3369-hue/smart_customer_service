"""Offline tests for textbook-grounded doctor answers and examiner handoff."""

import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.RAG.book_rag import BookSearchResult
from app.agent.attending_doctor import attending_doctor_node
from app.agent.evidence import textbook_retriever_node, web_retriever_node
from app.agent.medical_examiner import CaseAssessment, medical_examiner_node
from app.agent.supervisor import EvidenceReview, evidence_supervisor_node
from app.agent.tools import WebSearchResult


def state() -> dict:
    return {
        "messages": [HumanMessage(content="额头痛三小时，中度，阵发性。")],
        "user_id": "test_user",
        "thread_id": "test_thread",
        "medical_documents": [],
        "diagnosis": None,
        "prescription": None,
        "next": None,
        "case_summary": "额头痛三小时，中度，阵发性。",
        "ready_for_doctor": False,
        "sources": [],
        "retrieval_status": None,
        "textbook_hits": [],
        "textbook_status": None,
        "unavailable_books": [],
        "retrieval_queries": [],
        "evidence_route": None,
        "evidence_reason": None,
        "web_hits": [],
        "web_status": None,
    }


def hit(book_id="diagnostics", page=201) -> dict:
    title = "诊断学" if book_id == "diagnostics" else "内科学"
    return {
        "book_id": book_id,
        "content": "头痛评估应结合病史与查体。",
        "pdf_page": page,
        "chunk_index": 0,
        "book_title": title,
        "edition": "第9版" if book_id == "diagnostics" else "第10版",
        "pdf_filename": f"{book_id}.pdf",
        "distance": 0.25,
    }


class TestDoctorTextbookFlow(unittest.TestCase):
    def test_doctor_model_can_disable_thinking_without_global_change(self):
        from app.agent.base import get_model

        self.assertEqual(get_model(enable_thinking=False).extra_body,
                         {"enable_thinking": False})
        self.assertIsNone(get_model().extra_body)

    @patch("app.agent.attending_doctor.create_agent")
    @patch("app.agent.attending_doctor.get_user_long_memory", return_value="")
    @patch("app.agent.attending_doctor.get_long_term_memory")
    @patch("app.agent.attending_doctor.get_model")
    def test_doctor_cites_only_retrieved_pages(
        self, _model, _store, _memory, create_agent
    ):
        case = state()
        case["textbook_hits"] = [hit(), hit("internal_medicine", 301)]
        case["textbook_status"] = "ready"
        create_agent.return_value.invoke.return_value = {
            "messages": [AIMessage(content="需要结合病史继续评估[教材1]。"
                                   "页码由程序核验，勿引用PDF第999页。")]
        }
        result = attending_doctor_node(case)
        prompt = create_agent.call_args.kwargs["system_prompt"]
        self.assertIn("《诊断学》", prompt)
        self.assertIn("《内科学》", prompt)
        self.assertIn("PDF第201页", result["messages"][-1].content)
        self.assertNotIn("PDF第999页", result["messages"][-1].content)
        self.assertEqual(result["sources"][0]["pdf_page"], 201)
        self.assertEqual(result["retrieval_status"], "book_only")
        self.assertEqual(result["sources"][0]["type"], "textbook")

    @patch("app.agent.attending_doctor.create_agent")
    @patch("app.agent.attending_doctor.get_user_long_memory", return_value="")
    @patch("app.agent.attending_doctor.get_long_term_memory")
    @patch("app.agent.attending_doctor.get_model")
    def test_no_hit_does_not_invoke_doctor_model(
        self, _model, _store, _memory, create_agent
    ):
        result = attending_doctor_node(state())
        self.assertEqual(result["retrieval_status"], "no_sources")
        self.assertEqual(result["sources"], [])
        self.assertIn("暂时没有找到足够可靠的资料", result["messages"][-1].content)
        self.assertIn("初步判断", result["messages"][-1].content)
        create_agent.assert_not_called()

    @patch("app.agent.attending_doctor.create_agent")
    @patch("app.agent.attending_doctor.get_user_long_memory", return_value="")
    @patch("app.agent.attending_doctor.get_long_term_memory")
    @patch("app.agent.attending_doctor.get_model")
    def test_answer_without_valid_marker_is_not_published_as_grounded(
        self, _model, _store, _memory, create_agent
    ):
        case = state()
        case["textbook_hits"] = [hit()]
        create_agent.return_value.invoke.return_value = {
            "messages": [AIMessage(content="这是确定诊断[教材99]")]
        }
        result = attending_doctor_node(case)
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["retrieval_status"], "invalid_citation")
        self.assertNotIn("确定诊断", result["messages"][-1].content)

    @patch("app.agent.attending_doctor.create_agent")
    @patch("app.agent.attending_doctor.get_user_long_memory", return_value="")
    @patch("app.agent.attending_doctor.get_long_term_memory")
    @patch("app.agent.attending_doctor.get_model")
    def test_overconfident_exclusion_is_softened(
        self, _model, _store, _memory, create_agent
    ):
        case = state()
        case["textbook_hits"] = [hit()]
        create_agent.return_value.invoke.return_value = {
            "messages": [AIMessage(content=(
                "### 初步判断\n更接近常见紧张性不适[教材1]。"
                "目前证据不支持严重疾病，但需观察症状演变。"
                "暂不考虑严重脊柱病变。"
            ))]
        }
        result = attending_doctor_node(case)
        content = result["messages"][-1].content
        self.assertNotIn("证据不支持", content)
        self.assertNotIn("排除", content)
        self.assertNotIn("暂不考虑", content)
        self.assertIn("线上信息有限，仍需观察症状变化", content)
        self.assertEqual(result["sources"][0]["reference"], "教材1")

    @patch("app.agent.attending_doctor.create_agent")
    @patch("app.agent.attending_doctor.get_user_long_memory", return_value="")
    @patch("app.agent.attending_doctor.get_long_term_memory")
    @patch("app.agent.attending_doctor.get_model")
    def test_mixed_valid_and_fabricated_markers_are_rejected(
        self, _model, _store, _memory, create_agent
    ):
        case = state()
        case["textbook_hits"] = [hit()]
        create_agent.return_value.invoke.return_value = {
            "messages": [AIMessage(content="事实[教材1]，臆造内容[教材99]")]
        }
        result = attending_doctor_node(case)
        self.assertEqual(result["sources"], [])
        self.assertNotIn("臆造内容", result["messages"][-1].content)

    @patch("app.agent.attending_doctor.create_agent")
    @patch("app.agent.attending_doctor.get_user_long_memory", return_value="")
    @patch("app.agent.attending_doctor.get_long_term_memory")
    @patch("app.agent.attending_doctor.get_model")
    def test_web_only_answer_uses_actual_url_not_book_page(
        self, _model, _store, _memory, create_agent
    ):
        case = state()
        case["web_hits"] = [{
            "title": "示例医学资料", "url": "https://example.org/guide",
            "content": "小腿不适需结合病史。", "published_date": "2026-01-01",
        }]
        case["evidence_route"] = "web_only"
        create_agent.return_value.invoke.return_value = {
            "messages": [AIMessage(content="教材支持的分析：需结合病史[网页1]。")]
        }
        result = attending_doctor_node(case)
        self.assertEqual(result["retrieval_status"], "web_only")
        self.assertEqual(result["sources"][0]["url"], "https://example.org/guide")
        self.assertNotIn("PDF第", result["messages"][-1].content)
        self.assertNotIn("教材支持的分析", result["messages"][-1].content)
        self.assertIn("网页资料分析", result["messages"][-1].content)
        self.assertIn("教材检索未命中", result["messages"][-1].content)


class TestExaminerHandoff(unittest.TestCase):
    @patch("app.agent.medical_examiner.assess_case")
    @patch("app.agent.medical_examiner.create_agent")
    @patch("app.agent.medical_examiner.get_user_long_memory", return_value="")
    @patch("app.agent.medical_examiner.get_long_term_memory")
    @patch("app.agent.medical_examiner.get_model")
    def test_complete_case_hands_off_without_exposing_examiner_advice(
        self, _model, _store, _memory, create_agent, assess
    ):
        create_agent.return_value.invoke.return_value = {
            "messages": [AIMessage(content="建议挂耳鼻喉科")]
        }
        assess.return_value = CaseAssessment(
            chief_complaint="额头痛", duration="三小时",
            summary="额头痛三小时，中度，阵发性。", ready_for_doctor=True,
            follow_up_question="",
        )
        result = medical_examiner_node(state())
        self.assertTrue(result["ready_for_doctor"])
        self.assertEqual(result["next"], "attending_doctor")
        self.assertNotIn("messages", result)

    @patch("app.agent.medical_examiner.assess_case")
    @patch("app.agent.medical_examiner.create_agent")
    @patch("app.agent.medical_examiner.get_user_long_memory", return_value="")
    @patch("app.agent.medical_examiner.get_long_term_memory")
    @patch("app.agent.medical_examiner.get_model")
    def test_incomplete_case_asks_one_question(
        self, _model, _store, _memory, create_agent, assess
    ):
        create_agent.return_value.invoke.return_value = {
            "messages": [AIMessage(content="建议挂耳鼻喉科")]
        }
        assess.return_value = CaseAssessment(
            chief_complaint="额头痛", duration="", summary="额头痛，持续时间未知。",
            ready_for_doctor=False, follow_up_question="持续多久了？",
        )
        result = medical_examiner_node(state())
        self.assertFalse(result["ready_for_doctor"])
        self.assertIn("持续多久了", result["messages"][-1].content)
        self.assertNotIn("耳鼻喉科", result["messages"][-1].content)

    @patch("app.agent.medical_examiner.assess_case")
    @patch("app.agent.medical_examiner.create_agent")
    @patch("app.agent.medical_examiner.get_user_long_memory", return_value="")
    @patch("app.agent.medical_examiner.get_long_term_memory")
    @patch("app.agent.medical_examiner.get_model")
    def test_ready_summary_keeps_complaint_and_duration(
        self, _model, _store, _memory, create_agent, assess
    ):
        create_agent.return_value.invoke.return_value = {"messages": []}
        assess.return_value = CaseAssessment(
            chief_complaint="双侧小腿肚不适", duration="两天", summary="没有额外检查结果",
            ready_for_doctor=True, follow_up_question="",
        )
        result = medical_examiner_node(state())
        self.assertTrue(result["ready_for_doctor"])
        self.assertIn("双侧小腿肚不适", result["case_summary"])
        self.assertIn("两天", result["case_summary"])


class TestEvidenceRouting(unittest.TestCase):
    @patch("app.agent.evidence._rewrite_textbook_query",
           return_value="双侧小腿腓肠肌不适 鉴别诊断")
    @patch("app.agent.evidence.search_textbooks")
    def test_empty_first_query_is_rewritten_once_before_web(
        self, search, rewrite
    ):
        search.side_effect = [BookSearchResult([], []), BookSearchResult([hit()], [])]
        case = state()
        case["case_summary"] = "双侧小腿肚不适"
        result = textbook_retriever_node(case)
        self.assertEqual(result["textbook_status"], "ready")
        self.assertEqual(len(result["retrieval_queries"]), 2)
        self.assertEqual(search.call_count, 2)
        rewrite.assert_called_once_with("双侧小腿肚不适")

    @patch("app.agent.evidence.search_web_sources")
    @patch("app.agent.evidence._rewrite_textbook_query",
           return_value="双侧小腿腓肠肌不适 鉴别诊断")
    @patch("app.agent.evidence.search_textbooks",
           return_value=BookSearchResult([], []))
    def test_no_book_hit_routes_to_source_preserving_web(
        self, search, _rewrite, web_search
    ):
        case = state()
        case["case_summary"] = "双侧小腿肚不适"
        case.update(textbook_retriever_node(case))
        self.assertEqual(search.call_count, 2)
        case.update(evidence_supervisor_node(case))
        self.assertEqual(case["evidence_route"], "web_only")
        self.assertEqual(case["next"], "web_retriever")
        web_search.return_value = WebSearchResult([{
            "title": "示例来源", "url": "https://example.org/a",
            "content": "不适需结合病史。", "published_date": "",
        }], "ready")
        result = web_retriever_node(case)
        self.assertEqual(result["web_hits"][0]["url"], "https://example.org/a")
        self.assertEqual(result["web_status"], "ready")

    @patch("app.agent.supervisor.review_textbook_hits")
    def test_strong_book_evidence_skips_web(self, review):
        review.return_value = EvidenceReview(
            accepted_indexes=[1, 2], needs_web=False, reason="相关教材覆盖足够"
        )
        case = state()
        case["textbook_hits"] = [hit(), hit("internal_medicine", 301)]
        case["textbook_status"] = "ready"
        result = evidence_supervisor_node(case)
        self.assertEqual(result["evidence_route"], "book_only")
        self.assertEqual(result["next"], "attending_doctor")

    @patch("app.agent.supervisor.review_textbook_hits")
    def test_weak_or_partial_book_evidence_requests_web(self, review):
        review.return_value = EvidenceReview(
            accepted_indexes=[1], needs_web=True, reason="教材覆盖不足"
        )
        case = state()
        case["textbook_hits"] = [hit()]
        case["textbook_status"] = "partial"
        result = evidence_supervisor_node(case)
        self.assertEqual(result["evidence_route"], "book_plus_web")

    @patch("app.agent.supervisor.review_textbook_hits")
    def test_unrelated_vector_hit_is_rejected_and_routes_to_web(self, review):
        review.return_value = EvidenceReview(
            accepted_indexes=[], needs_web=False, reason="片段只讨论尿路，与小腿不适无关"
        )
        case = state()
        case["case_summary"] = "双侧小腿肚不适"
        case["textbook_hits"] = [hit("internal_medicine", 533)]
        case["textbook_status"] = "ready"
        result = evidence_supervisor_node(case)
        self.assertEqual(result["textbook_hits"], [])
        self.assertEqual(result["textbook_status"], "irrelevant")
        self.assertEqual(result["evidence_route"], "web_only")
        self.assertEqual(result["next"], "web_retriever")


class TestGraphHandoff(unittest.TestCase):
    def test_doctor_route_still_rebuilds_case_before_retrieval(self):
        from app.agent.multi_agent import create_medical_system

        visited = []

        def node(name, output):
            def run(_state):
                visited.append(name)
                return output
            return run

        with patch.multiple(
            "app.agent.multi_agent",
            init_memory_system=lambda: None,
            get_short_term_memory=lambda: None,
            get_long_term_memory=lambda: None,
            supervisor_node=node("supervisor", {"next": "attending_doctor"}),
            medical_examiner_node=node("medical_examiner", {
                "ready_for_doctor": True, "case_summary": "额头痛三小时"
            }),
            textbook_retriever_node=node("textbook_retriever", {
                "textbook_hits": [hit()], "textbook_status": "ready"
            }),
            evidence_supervisor_node=node("evidence_supervisor", {
                "evidence_route": "book_only", "next": "attending_doctor"
            }),
            web_retriever_node=node("web_retriever", {}),
            attending_doctor_node=node("attending_doctor", {
                "messages": [AIMessage(content="【主治医生】分析[教材1]")]
            }),
            pharmacist_node=node("pharmacist", {}),
        ):
            graph_state = state()
            graph_state["messages"] = [HumanMessage(content="请继续分析这份复查报告")]
            create_medical_system().invoke(graph_state)
        self.assertEqual(visited, [
            "supervisor", "medical_examiner", "textbook_retriever",
            "evidence_supervisor", "attending_doctor",
        ])

    def test_empty_book_path_reaches_web_then_doctor(self):
        from app.agent.multi_agent import create_medical_system

        visited = []

        def node(name, output):
            def run(_state):
                visited.append(name)
                return output
            return run

        with patch.multiple(
            "app.agent.multi_agent",
            init_memory_system=lambda: None,
            get_short_term_memory=lambda: None,
            get_long_term_memory=lambda: None,
            supervisor_node=node("supervisor", {"next": "medical_examiner"}),
            medical_examiner_node=node("medical_examiner", {
                "ready_for_doctor": True, "case_summary": "双侧小腿不适"
            }),
            textbook_retriever_node=node("textbook_retriever", {
                "textbook_hits": [], "textbook_status": "no_match"
            }),
            evidence_supervisor_node=node("evidence_supervisor", {
                "evidence_route": "web_only", "next": "web_retriever"
            }),
            web_retriever_node=node("web_retriever", {
                "web_hits": [{"title": "资料", "url": "https://example.org/a",
                              "content": "相关说明"}], "web_status": "ready"
            }),
            attending_doctor_node=node("attending_doctor", {
                "messages": [AIMessage(content="【主治医生】网页分析[网页1]")],
                "retrieval_status": "web_only",
            }),
            pharmacist_node=node("pharmacist", {}),
        ):
            graph_state = state()
            graph_state["messages"] = [HumanMessage(content="请继续分析这份复查报告")]
            result = create_medical_system().invoke(graph_state)
        self.assertEqual(visited, [
            "supervisor", "medical_examiner", "textbook_retriever",
            "evidence_supervisor", "web_retriever", "attending_doctor",
        ])
        self.assertEqual(result["retrieval_status"], "web_only")

    @patch("app.agent.multi_agent.web_retriever_node")
    @patch("app.agent.multi_agent.evidence_supervisor_node")
    @patch("app.agent.multi_agent.textbook_retriever_node")
    @patch("app.agent.multi_agent.pharmacist_node")
    @patch("app.agent.multi_agent.attending_doctor_node")
    @patch("app.agent.multi_agent.medical_examiner_node")
    @patch("app.agent.multi_agent.supervisor_node")
    @patch("app.agent.multi_agent.get_long_term_memory", return_value=None)
    @patch("app.agent.multi_agent.get_short_term_memory", return_value=None)
    @patch("app.agent.multi_agent.init_memory_system")
    def test_complete_case_reaches_doctor_in_same_turn(
        self, _init, _short, _long, supervisor, examiner, doctor, _pharmacist,
        textbook, evidence_gate, web
    ):
        from app.agent.multi_agent import create_medical_system

        supervisor.side_effect = lambda _state: {"next": "medical_examiner"}
        examiner.side_effect = lambda _state: {
            "ready_for_doctor": True, "case_summary": "额头痛三小时", "next": "attending_doctor"
        }
        textbook.side_effect = lambda _state: {
            "textbook_hits": [hit()], "textbook_status": "ready", "retrieval_queries": ["额头痛三小时"]
        }
        evidence_gate.side_effect = lambda _state: {
            "evidence_route": "book_only", "next": "attending_doctor"
        }
        doctor.side_effect = lambda _state: {
            "messages": [AIMessage(content="【主治医生】教材分析[教材1]")], "next": "__end__"
        }
        graph_state = state()
        graph_state["messages"] = [HumanMessage(content="请继续分析这份复查报告")]
        result = create_medical_system().invoke(graph_state)
        textbook.assert_called_once()
        evidence_gate.assert_called_once()
        web.assert_not_called()
        doctor.assert_called_once()
        self.assertIn("【主治医生】", result["messages"][-1].content)


class TestChatResponse(unittest.TestCase):
    @patch("app.api.chat.create_medical_agent_system")
    def test_response_exposes_only_cited_sources(self, create_graph):
        from app.api.chat import ChatRequest, send_message

        database = MagicMock()
        conversation = MagicMock(id="test_thread", user_id=7)
        database.query.return_value.filter.return_value.first.return_value = conversation
        graph = create_graph.return_value
        graph.invoke.return_value = {
            "messages": [AIMessage(content="【主治医生】教材分析[教材1]")],
            "sources": [{"reference": "教材1", "book_title": "诊断学", "pdf_page": 79}],
            "retrieval_status": "ready",
        }
        result = asyncio.run(send_message(
            ChatRequest(user_id="user_7", thread_id="test_thread", message="额头痛"),
            current_user=MagicMock(id=7), db=database,
        ))
        payload = json.loads(result.body)
        self.assertEqual(payload["sources"][0]["pdf_page"], 79)
        self.assertEqual(payload["retrieval_status"], "ready")
        self.assertEqual(graph.invoke.call_args.args[0]["sources"], [])


if __name__ == "__main__":
    unittest.main()
