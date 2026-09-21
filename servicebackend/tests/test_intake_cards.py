"""Regression checks for staged, zero-LLM symptom intake."""

import unittest
import asyncio
import json
from unittest.mock import patch
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from app.agent.intake import (
    FIRST_QUESTIONS,
    SECOND_QUESTIONS,
    SECOND_WITH_DURATION,
    UPPER_LIMB_QUESTIONS,
    intake_gate_node,
)
from app.agent.intake_review import FollowUpCard, IntakeReadiness, intake_review_node


def answers(questions, overrides=None):
    choices = {"location": ["middle"], "feeling": ["ache"], "warning": ["none"],
               "duration": ["hours"], "severity": ["mild"], "trigger": ["none"]}
    choices.update(overrides or {})
    return {q["id"]: {"choices": choices.get(q["id"], [q["options"][0]["value"]]),
                      "other_text": ""} for q in questions}


class TestIntakeCards(unittest.TestCase):
    def test_half_day_back_pain_asks_cards_without_retrieval(self):
        result = intake_gate_node({"messages": [HumanMessage(content="我背疼半天了")]})
        self.assertEqual(result["intake_route"], "__end__")
        self.assertEqual(len(result["intake_questions"]), 3)
        self.assertFalse(result["ready_for_doctor"])

    def test_forearm_pain_uses_upper_limb_cards(self):
        result = intake_gate_node({"messages": [HumanMessage(content="我小臂疼")]})
        self.assertEqual(result["intake_route"], "__end__")
        self.assertEqual(result["intake_questions"], UPPER_LIMB_QUESTIONS)
        labels = [option["label"] for option in result["intake_questions"][0]["options"]]
        self.assertIn("手肘附近", labels)
        self.assertIn("小臂 / 前臂", labels)

    def test_short_follow_up_recovers_recent_forearm_complaint(self):
        result = intake_gate_node({"messages": [
            HumanMessage(content="我小臂疼"),
            AIMessage(content="请问持续多久、哪个位置、什么感觉？"),
            HumanMessage(content="半天 手肘 酸"),
        ]})
        self.assertEqual(result["intake_questions"], UPPER_LIMB_QUESTIONS)
        self.assertEqual(result["intake_complaint"], "我小臂疼；补充：半天 手肘 酸")

    def test_cards_reconstructed_from_old_examiner_turn_can_be_submitted(self):
        first_result = intake_gate_node({
            "messages": [
                HumanMessage(content="我小臂疼"),
                AIMessage(content="【体检员】请问持续多久？"),
                HumanMessage(content="半天 手肘 酸"),
                AIMessage(content="【体检员】还需要了解是否受伤。"),
                HumanMessage(content="已提交问诊卡片"),
            ],
            "intake_questions": [], "intake_answers": {}, "intake_submission": answers(
                UPPER_LIMB_QUESTIONS, {"location": ["elbow"]}),
        })
        self.assertEqual(first_result["intake_route"], "__end__")
        self.assertEqual(first_result["intake_questions"], SECOND_WITH_DURATION)

        result = intake_gate_node({
            "messages": [HumanMessage(content="已提交问诊卡片")],
            "intake_complaint": "我小臂疼；补充：半天 手肘 酸",
            "intake_round": 2,
            "intake_questions": SECOND_WITH_DURATION,
            "intake_answers": first_result["intake_answers"],
            "intake_submission": answers(SECOND_WITH_DURATION),
        })
        self.assertEqual(result["intake_route"], "intake_review")
        self.assertIn("我小臂疼；补充：半天 手肘 酸", result["case_summary"])
        self.assertIn("手肘附近", result["case_summary"])
        self.assertIn("以上均无", result["case_summary"])

    @patch("app.api.conversation.get_short_term_memory")
    def test_reopening_old_text_examiner_turn_returns_cards(self, get_memory):
        from app.api.conversation import get_conversation

        get_memory.return_value.list.return_value = [MagicMock(checkpoint={
            "channel_values": {"messages": [
                HumanMessage(content="我小臂疼"),
                AIMessage(content="【体检员】还需要了解具体位置。"),
                HumanMessage(content="半天 手肘 酸"),
                AIMessage(content="【体检员】还需要了解是否有外伤。"),
            ]}
        })]
        database = MagicMock()
        database.query.return_value.filter.return_value.first.return_value = MagicMock(
            id="old-thread", user_id=7, title="旧会话", last_message="半天 手肘 酸",
            last_active=None, created_at=None)
        result = asyncio.run(get_conversation(
            conversation_id="old-thread", current_user=MagicMock(id=7), db=database))
        self.assertEqual(result["intake_questions"], UPPER_LIMB_QUESTIONS)

    @patch("app.api.conversation.get_short_term_memory")
    def test_reopening_old_doctor_followup_restores_cards_and_hides_analysis(self, get_memory):
        from app.api.conversation import get_conversation

        old_answer = (
            "【主治医生】\n病例信息……\n证据分析……\n仍需确认/下一步\n"
            "1. 诱因确认：是否频繁拧毛巾、提重物或使用鼠标？\n"
            "2. 定位细化：疼痛在手肘外侧还是内侧？"
        )
        get_memory.return_value.list.return_value = [MagicMock(checkpoint={
            "channel_values": {"messages": [
                HumanMessage(content="我小臂疼半天"), AIMessage(content=old_answer),
            ]}
        })]
        database = MagicMock()
        database.query.return_value.filter.return_value.first.return_value = MagicMock(
            id="legacy-doctor", user_id=7, title="旧主治医生会话", last_message="",
            last_active=None, created_at=None)
        result = asyncio.run(get_conversation(
            conversation_id="legacy-doctor", current_user=MagicMock(id=7), db=database))
        self.assertEqual(len(result["intake_questions"]), 2)
        self.assertIn("手肘附近更靠哪一侧", result["intake_questions"][0]["title"])
        self.assertNotIn("证据分析", result["messages"][-1]["content"])
        self.assertIn("继续选择卡片", result["messages"][-1]["content"])

    def test_medication_question_does_not_open_symptom_cards(self):
        result = intake_gate_node({"messages": [HumanMessage(content="头痛能不能吃止痛药")]})
        self.assertEqual(result["intake_route"], "supervisor")
        self.assertEqual(result["intake_questions"], [])

    def test_first_cards_always_continue_with_second_batch(self):
        result = intake_gate_node({
            "messages": [HumanMessage(content="已提交问诊卡片")],
            "intake_complaint": "我背疼半天了", "intake_round": 1,
            "intake_questions": FIRST_QUESTIONS, "intake_answers": {},
            "intake_submission": answers(FIRST_QUESTIONS),
        })
        self.assertEqual(result["intake_route"], "__end__")
        self.assertEqual(result["intake_questions"], SECOND_WITH_DURATION)
        self.assertIn("偏中部", result["intake_answers"]["location"]["display"])
        self.assertNotIn("病例信息", result["messages"][0].content)

    def test_second_cards_go_to_readiness_checkpoint(self):
        result = intake_gate_node({
            "messages": [HumanMessage(content="已提交问诊卡片")],
            "intake_complaint": "我背疼半天了", "intake_round": 2,
            "intake_questions": SECOND_WITH_DURATION,
            "intake_answers": answers(FIRST_QUESTIONS),
            "intake_submission": answers(SECOND_WITH_DURATION),
        })
        self.assertEqual(result["intake_route"], "intake_review")
        self.assertEqual(result["intake_questions"], [])
        self.assertIn("偏中部", result["case_summary"])
        self.assertIn("轻微，不影响活动", result["case_summary"])
        self.assertNotIn("主动脉夹层", result["case_summary"])

    @patch("app.agent.intake_review.review_intake")
    def test_checkpoint_returns_more_cards_without_analysis(self, review):
        review.return_value = IntakeReadiness(
            ready_for_initial_assessment=False,
            reason="手肘内外侧会改变肌群判断",
            questions=[FollowUpCard(
                title="疼痛更靠近手肘哪一侧？",
                hint="可多选。",
                options=["外侧", "内侧", "前侧", "后侧"],
            )],
        )
        result = intake_review_node({
            "case_summary": "小臂靠近手肘酸胀半天", "intake_round": 2,
            "messages": [],
        })
        self.assertEqual(result["intake_route"], "__end__")
        self.assertFalse(result["ready_for_doctor"])
        self.assertEqual(result["intake_questions"][0]["title"], "疼痛更靠近手肘哪一侧？")
        self.assertNotIn("肌群判断", result["messages"][0].content)

    @patch("app.agent.intake_review.review_intake")
    def test_checkpoint_routes_only_when_ready(self, review):
        review.return_value = IntakeReadiness(
            ready_for_initial_assessment=True, reason="关键事实齐全", questions=[]
        )
        result = intake_review_node({
            "case_summary": "背部中段轻微酸胀半天，无危险征象", "intake_round": 2,
            "messages": [],
        })
        self.assertEqual(result["intake_route"], "textbook_retriever")
        self.assertTrue(result["ready_for_doctor"])

    @patch("app.agent.intake_review.review_intake")
    def test_checkpoint_stops_after_round_limit_instead_of_looping(self, review):
        review.return_value = IntakeReadiness(
            ready_for_initial_assessment=False,
            reason="仍缺少线下查体",
            questions=[FollowUpCard(title="还疼吗？", options=["是", "否"])],
        )
        result = intake_review_node({
            "case_summary": "信息仍有限", "intake_round": 5, "messages": [],
        })
        self.assertEqual(result["intake_route"], "__end__")
        self.assertEqual(result["intake_questions"], [])
        self.assertIn("线下就医", result["messages"][0].content)

    def test_missing_duration_gets_only_two_more_cards(self):
        result = intake_gate_node({
            "messages": [HumanMessage(content="已提交问诊卡片")],
            "intake_complaint": "我背疼", "intake_round": 1,
            "intake_questions": FIRST_QUESTIONS, "intake_answers": {},
            "intake_submission": answers(FIRST_QUESTIONS),
        })
        self.assertEqual([q["id"] for q in result["intake_questions"]],
                         [q["id"] for q in SECOND_QUESTIONS])
        self.assertEqual(result["intake_route"], "__end__")

    def test_unclear_symptoms_do_not_repeat_known_duration(self):
        result = intake_gate_node({
            "messages": [HumanMessage(content="已提交问诊卡片")],
            "intake_complaint": "我背疼半天", "intake_round": 1,
            "intake_questions": FIRST_QUESTIONS, "intake_answers": {},
            "intake_submission": answers(FIRST_QUESTIONS, {
                "location": ["unsure"], "feeling": ["unsure"]}),
        })
        self.assertEqual([q["id"] for q in result["intake_questions"]], ["severity", "trigger"])

    def test_red_flag_stops_model_work(self):
        result = intake_gate_node({
            "messages": [HumanMessage(content="已提交问诊卡片")],
            "intake_complaint": "我背疼半天了", "intake_round": 1,
            "intake_questions": FIRST_QUESTIONS, "intake_answers": {},
            "intake_submission": answers(FIRST_QUESTIONS, {"warning": ["bladder"]}),
        })
        self.assertEqual(result["intake_route"], "__end__")
        self.assertIn("急诊", result["messages"][0].content)

    def test_red_flag_in_other_text_also_stops_model_work(self):
        submission = answers(FIRST_QUESTIONS, {"warning": ["other"]})
        submission["warning"]["other_text"] = "现在有胸痛"
        result = intake_gate_node({
            "messages": [HumanMessage(content="已提交问诊卡片")],
            "intake_complaint": "我背疼半天了", "intake_round": 1,
            "intake_questions": FIRST_QUESTIONS, "intake_answers": {},
            "intake_submission": submission,
        })
        self.assertEqual(result["intake_route"], "__end__")
        self.assertIn("急诊", result["messages"][0].content)

    def test_other_requires_text_and_none_is_exclusive(self):
        for warning in (["other"], ["none", "fever"]):
            result = intake_gate_node({
                "messages": [HumanMessage(content="已提交问诊卡片")],
                "intake_complaint": "我背疼半天了", "intake_round": 1,
                "intake_questions": FIRST_QUESTIONS, "intake_answers": {},
                "intake_submission": answers(FIRST_QUESTIONS, {"warning": warning}),
            })
            self.assertEqual(result["intake_questions"], FIRST_QUESTIONS)
            self.assertEqual(result["intake_route"], "__end__")

    def test_graph_persists_cards_and_skips_expensive_nodes_until_submission(self):
        from langgraph.checkpoint.memory import InMemorySaver
        from app.agent.multi_agent import create_medical_system

        visited = []

        def node(name, result):
            def run(_state):
                visited.append(name)
                return result
            return run

        with patch.multiple(
            "app.agent.multi_agent",
            init_memory_system=lambda: None,
            get_short_term_memory=lambda: InMemorySaver(),
            get_long_term_memory=lambda: None,
            supervisor_node=node("supervisor", {"next": "__end__"}),
            medical_examiner_node=node("medical_examiner", {}),
            intake_review_node=node("intake_review", {
                "intake_route": "textbook_retriever", "ready_for_doctor": True,
            }),
            textbook_retriever_node=node("textbook_retriever", {"textbook_hits": []}),
            evidence_supervisor_node=node("evidence_supervisor", {"next": "attending_doctor"}),
            web_retriever_node=node("web_retriever", {}),
            attending_doctor_node=node("attending_doctor", {"messages": []}),
            pharmacist_node=node("pharmacist", {}),
        ):
            graph = create_medical_system()
            config = {"configurable": {"thread_id": "intake-test"}}
            first = graph.invoke({"messages": [HumanMessage(content="背疼半天")],
                                  "intake_submission": None}, config=config)
            self.assertEqual(len(first["intake_questions"]), 3)
            self.assertEqual(visited, [])
            second = graph.invoke({"messages": [HumanMessage(content="已提交问诊卡片")],
                                   "intake_submission": answers(FIRST_QUESTIONS)}, config=config)
            self.assertEqual(second["intake_questions"], SECOND_WITH_DURATION)
            self.assertEqual(visited, [])
            third = graph.invoke({"messages": [HumanMessage(content="已提交问诊卡片")],
                                  "intake_submission": answers(SECOND_WITH_DURATION)}, config=config)
            self.assertEqual(third["intake_questions"], [])
            self.assertEqual(visited, ["intake_review", "textbook_retriever",
                                       "evidence_supervisor", "attending_doctor"])

    @patch("app.api.chat.create_medical_agent_system")
    def test_sse_only_streams_doctor_and_finishes_with_verified_message(self, create_graph):
        from app.api.chat import ChatRequest, stream_message

        database = MagicMock()
        database.query.return_value.filter.return_value.first.return_value = MagicMock(
            id="intake-test", user_id=7)
        graph = create_graph.return_value
        graph.stream.return_value = iter([
            ("custom", {"type": "internal_note", "text": "内部评估"}),
            ("custom", {"type": "doctor_delta", "text": "初稿"}),
            ("updates", {"attending_doctor": {"messages": [AIMessage(content="已核验回答[教材1]")],
                                               "sources": [{"reference": "教材1"}]}}),
        ])

        async def run():
            response = await stream_message(
                ChatRequest(user_id="user_7", thread_id="intake-test", message="背疼半天"),
                current_user=MagicMock(id=7), db=database,
            )
            chunks = [chunk async for chunk in response.body_iterator]
            return b"".join(chunk if isinstance(chunk, bytes) else chunk.encode() for chunk in chunks).decode()

        body = asyncio.run(run())
        self.assertNotIn("内部评估", body)
        self.assertIn('event: delta\ndata: {"text": "初稿"}', body)
        final = body.split("event: final\ndata: ", 1)[1].split("\n\n", 1)[0]
        self.assertEqual(json.loads(final)["message"], "已核验回答[教材1]")

    @patch("app.agent.attending_doctor.get_stream_writer")
    @patch("app.agent.attending_doctor.get_user_long_memory", return_value="")
    @patch("app.agent.attending_doctor.get_long_term_memory")
    @patch("app.agent.attending_doctor.get_model")
    def test_doctor_emits_real_model_chunks_but_returns_verified_answer(
        self, get_model, _store, _memory, writer,
    ):
        from app.agent.attending_doctor import attending_doctor_node

        get_model.return_value.stream.return_value = [
            AIMessageChunk(content="条件性分析"), AIMessageChunk(content="[教材1]")]
        case = {
            "messages": [HumanMessage(content="背疼半天")],
            "case_summary": "背疼半天；偏中部；酸胀；危险征象卡片均无",
            "intake_answers": {"location": {"choices": ["middle"], "other_text": ""}},
            "stream_response": True, "user_id": "user_7", "thread_id": "t",
            "textbook_hits": [{"book_id": "diagnostics", "book_title": "诊断学", "edition": "第9版",
                               "pdf_page": 65, "pdf_filename": "book.pdf", "content": "背痛评估。"}],
            "web_hits": [], "unavailable_books": [], "textbook_status": "ready", "web_status": "no_match",
        }
        result = attending_doctor_node(case)
        prompt = get_model.return_value.stream.call_args.args[0][0].content
        self.assertIn("### 初步判断", prompt)
        self.assertNotIn("病例信息—证据分析", prompt)
        self.assertIn("不要再向用户提出文字问题", prompt)
        streamed = "".join(call.args[0]["text"] for call in writer.return_value.call_args_list)
        self.assertEqual(streamed, result["messages"][0].content)
        self.assertNotEqual(streamed, "条件性分析")
        self.assertIn("《诊断学》第9版，PDF第65页", result["messages"][0].content)
        self.assertEqual(result["sources"][0]["reference"], "教材1")

    @patch("app.agent.attending_doctor.get_user_long_memory", return_value="")
    @patch("app.agent.attending_doctor.get_long_term_memory")
    @patch("app.agent.attending_doctor.get_model")
    def test_langgraph_custom_stream_reaches_http_layer(self, get_model, _store, _memory):
        from langgraph.graph import StateGraph, END
        from app.agent.attending_doctor import attending_doctor_node
        from app.agent.state import MedicalAgentState

        get_model.return_value.stream.return_value = [
            AIMessageChunk(content="有条件的分析[教材1]")]
        builder = StateGraph(MedicalAgentState)
        builder.add_node("doctor", attending_doctor_node)
        builder.set_entry_point("doctor")
        builder.add_edge("doctor", END)
        graph = builder.compile()
        events = list(graph.stream({
            "messages": [HumanMessage(content="背疼半天")], "user_id": "user_7", "thread_id": "t",
            "case_summary": "背疼半天；偏中部；酸胀", "intake_answers": {"location": {}},
            "stream_response": True,
            "textbook_hits": [{"book_id": "diagnostics", "book_title": "诊断学", "edition": "第9版",
                               "pdf_page": 65, "pdf_filename": "book.pdf", "content": "背痛评估。"}],
            "web_hits": [], "unavailable_books": [], "textbook_status": "ready", "web_status": "no_match",
        }, stream_mode=["custom", "updates"]))
        streamed = "".join(
            data["text"] for mode, data in events
            if mode == "custom" and data.get("type") == "doctor_delta"
        )
        self.assertIn("有条件的分析[教材1]", streamed)
        self.assertIn("引用来源", streamed)

    @patch("app.agent.attending_doctor.doctor_followup_cards")
    @patch("app.agent.attending_doctor.get_stream_writer")
    @patch("app.agent.attending_doctor.get_user_long_memory", return_value="")
    @patch("app.agent.attending_doctor.get_long_term_memory")
    @patch("app.agent.attending_doctor.get_model")
    def test_doctor_followup_is_blocked_and_replaced_by_cards(
        self, get_model, _store, _memory, writer, followup_cards,
    ):
        from app.agent.attending_doctor import attending_doctor_node

        get_model.return_value.stream.return_value = [
            AIMessageChunk(content="### 仍需确认\n请问疼痛在手肘外侧还是内侧？[教材1]")
        ]
        followup_cards.return_value = [{
            "id": "followup_r3_q1", "title": "疼痛更靠近哪一侧？", "hint": "可多选。",
            "options": [{"value": "choice_1", "label": "外侧"},
                        {"value": "choice_2", "label": "内侧"},
                        {"value": "other", "label": "其他"}],
        }]
        case = {
            "messages": [HumanMessage(content="已提交问诊卡片")],
            "case_summary": "小臂靠近手肘酸胀半天", "intake_round": 2,
            "intake_answers": {"location": {}}, "stream_response": True,
            "user_id": "user_7", "thread_id": "t",
            "textbook_hits": [{"book_id": "diagnostics", "book_title": "诊断学",
                               "edition": "第9版", "pdf_page": 65,
                               "pdf_filename": "book.pdf", "content": "疼痛评估。"}],
            "web_hits": [], "unavailable_books": [], "textbook_status": "ready",
            "web_status": "no_match",
        }
        result = attending_doctor_node(case)
        self.assertEqual(result["retrieval_status"], "needs_more_info")
        self.assertEqual(result["intake_questions"][0]["title"], "疼痛更靠近哪一侧？")
        self.assertNotIn("仍需确认", result["messages"][0].content)
        writer.return_value.assert_not_called()


if __name__ == "__main__":
    unittest.main()
