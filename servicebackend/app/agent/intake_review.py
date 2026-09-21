"""Structured checkpoint between symptom cards and the attending doctor."""

import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agent.base import get_model
from app.agent.state import MedicalAgentState


MAX_INTAKE_ROUNDS = 5
FOLLOW_UP_SIGNAL = re.compile(
    r"(?:仍需|还需|需要)(?:确认|了解|补充)|请(?:问|补充|确认)|"
    r"(?:^|\n)\s*(?:#{1,4}\s*)?(?:病例信息|证据分析|仍需确认|下一步)|[？?]"
)


class FollowUpCard(BaseModel):
    title: str = Field(description="面向患者的一句简短问题")
    hint: str = Field(default="可多选；没有合适选项可选择其他。")
    options: list[str] = Field(description="3到6个简短、互不重复的患者可理解选项")


class IntakeReadiness(BaseModel):
    ready_for_initial_assessment: bool = Field(
        description="现有信息是否足以形成带不确定性的初步判断"
    )
    reason: str = Field(description="一句内部理由，不展示给患者")
    questions: list[FollowUpCard] = Field(
        description="信息不足时返回1到2张卡片；足够时必须为空"
    )


REVIEW_PROMPT = """你是问诊完整性检查点，不诊断、不解释病因，也不直接回复患者。
判断现有卡片答案是否足以让医学分析助手形成有条件的初步判断和一般建议。

规则：
1. 不要求资料完美完整；只有答案很可能改变初步方向、处理建议或就医级别时才追问。
2. 已经回答过的部位、感觉、持续时间、程度、诱因和危险征象不得重复询问。
3. 信息足够时 ready_for_initial_assessment=true 且 questions=[]。
4. 信息不足时只返回最有价值的1到2张卡片，每张3到6个普通患者看得懂的短选项。
5. 问题与选项中不得写疾病名称、分析过程、诊断结论、来源或治疗方案。
6. 不询问姓名、联系方式；年龄或性别只有确实会改变当前判断时才询问。
7. 卡片允许多选；不要输出“其他”和“不确定”，系统会自动补充。
"""


DOCTOR_FOLLOWUP_PROMPT = """下面的主治医生草稿违规包含了继续追问。
不要保留草稿中的病例分析、诊断、建议或来源，只把确实缺少的信息改写成1到2张选择卡片。
每张卡片提供3到6个普通患者看得懂的短选项，不要输出“其他”和“不确定”。
ready_for_initial_assessment 必须为 false。不得重复病例摘要中已经明确的信息。
"""


def _dialogue_summary(state: MedicalAgentState) -> str:
    summary = (state.get("case_summary") or "").strip()
    if summary:
        return summary
    return "\n".join(
        str(message.content)
        for message in state.get("messages", [])[-12:]
        if isinstance(message, HumanMessage) and isinstance(message.content, str)
    )


def _safe_text(value: str, limit: int) -> str:
    return " ".join(str(value).strip().split())[:limit]


def _cards_from_questions(questions: list[FollowUpCard], round_number: int) -> list[dict]:
    cards = []
    for question_index, question in enumerate(questions[:2], start=1):
        title = _safe_text(question.title, 60)
        labels = []
        for raw_label in question.options[:6]:
            label = _safe_text(raw_label, 28)
            if label and label not in labels and label not in {"其他", "不确定", "说不清"}:
                labels.append(label)
        if not title or len(labels) < 2:
            continue
        options = [
            {"value": f"choice_{option_index}", "label": label}
            for option_index, label in enumerate(labels, start=1)
        ]
        options.extend([
            {"value": "unsure", "label": "不确定"},
            {"value": "other", "label": "其他"},
        ])
        cards.append({
            "id": f"followup_r{round_number}_q{question_index}",
            "title": title,
            "hint": _safe_text(question.hint, 80) or "可多选；没有合适选项可选择其他。",
            "options": options,
        })
    return cards


def _fallback_card(round_number: int) -> list[dict]:
    return [{
        "id": f"followup_r{round_number}_q1",
        "title": "还有哪些情况可能和这次不适有关？",
        "hint": "可多选；没有其他情况可直接选择。",
        "options": [
            {"value": "choice_1", "label": "近期受伤或过度活动"},
            {"value": "choice_2", "label": "休息后仍持续"},
            {"value": "choice_3", "label": "症状正在变化"},
            {"value": "none", "label": "没有其他补充"},
            {"value": "unsure", "label": "不确定"},
            {"value": "other", "label": "其他"},
        ],
    }]


def legacy_doctor_followup_cards(messages: list) -> list[dict]:
    """Deterministically upgrade an unfinished, text-only doctor turn on reload."""
    draft = next((
        str(message.content) for message in reversed(messages[-8:])
        if isinstance(message, AIMessage) and isinstance(message.content, str)
        and "【主治医生】" in message.content and FOLLOW_UP_SIGNAL.search(message.content)
    ), "")
    if not draft:
        return []
    questions = []
    if any(term in draft for term in ("外侧", "内侧", "定位", "哪一侧")):
        questions.append({
            "id": "followup_r3_q1", "title": "手肘附近更靠哪一侧？",
            "hint": "可多选；说不清也可以直接选择。",
            "options": [
                {"value": "choice_1", "label": "外侧"},
                {"value": "choice_2", "label": "内侧"},
                {"value": "choice_3", "label": "前侧"},
                {"value": "choice_4", "label": "后侧"},
                {"value": "unsure", "label": "说不清"},
                {"value": "other", "label": "其他"},
            ],
        })
    if any(term in draft for term in ("诱因", "重复", "拧毛巾", "鼠标", "提重物", "运动")):
        questions.append({
            "id": f"followup_r3_q{len(questions) + 1}",
            "title": "近期有反复用手或手臂的动作吗？",
            "hint": "可多选；没有明显诱因可直接选择。",
            "options": [
                {"value": "choice_1", "label": "拧毛巾等旋转动作"},
                {"value": "choice_2", "label": "长时间使用鼠标键盘"},
                {"value": "choice_3", "label": "提重物或用力抓握"},
                {"value": "choice_4", "label": "球拍类或手臂运动"},
                {"value": "none", "label": "没有明显重复动作"},
                {"value": "unsure", "label": "不确定"},
                {"value": "other", "label": "其他"},
            ],
        })
    return questions[:2] or _fallback_card(3)


def review_intake(summary: str) -> IntakeReadiness:
    reviewer = get_model(enable_thinking=False).with_structured_output(
        IntakeReadiness, method="function_calling"
    )
    return reviewer.invoke([
        SystemMessage(content=REVIEW_PROMPT),
        HumanMessage(content=f"当前结构化病例摘要：\n{summary}"),
    ], extra_body={"enable_thinking": False})


def intake_review_node(state: MedicalAgentState) -> dict:
    """Route to more cards or evidence retrieval; never publish reasoning."""
    current_round = max(2, int(state.get("intake_round") or 2))
    summary = _dialogue_summary(state)
    try:
        decision = review_intake(summary)
        if decision.ready_for_initial_assessment:
            return {
                "intake_questions": [], "intake_route": "textbook_retriever",
                "intake_review_reason": decision.reason, "ready_for_doctor": True,
            }
        if current_round >= MAX_INTAKE_ROUNDS:
            return {
                "messages": [AIMessage(content=(
                    "已经通过多轮卡片补充信息，但线上资料仍不足以形成可靠的初步判断。"
                    "建议线下就医，由医生结合查体继续评估。"
                ))],
                "intake_questions": [], "intake_route": "__end__",
                "intake_review_reason": decision.reason, "ready_for_doctor": False,
            }
        next_round = current_round + 1
        cards = _cards_from_questions(decision.questions, next_round) or _fallback_card(next_round)
        return {
            "messages": [AIMessage(content="还需要确认少量关键信息，请继续选择卡片。")],
            "intake_questions": cards, "intake_round": next_round,
            "intake_route": "__end__", "intake_review_reason": decision.reason,
            "ready_for_doctor": False,
        }
    except Exception as exc:
        print(f"问诊完整性检查失败: {exc}")
        if current_round >= MAX_INTAKE_ROUNDS:
            return {
                "messages": [AIMessage(content="暂时无法核对问诊完整性，建议线下就医评估。")],
                "intake_questions": [], "intake_route": "__end__", "ready_for_doctor": False,
            }
        next_round = current_round + 1
        return {
            "messages": [AIMessage(content="还需要确认一项信息，请继续选择卡片。")],
            "intake_questions": _fallback_card(next_round), "intake_round": next_round,
            "intake_route": "__end__", "ready_for_doctor": False,
        }


def doctor_followup_cards(summary: str, draft: str, current_round: int) -> list[dict]:
    """Convert a violating doctor follow-up draft into cards without publishing it."""
    if current_round >= MAX_INTAKE_ROUNDS:
        return []
    next_round = current_round + 1
    try:
        reviewer = get_model(enable_thinking=False).with_structured_output(
            IntakeReadiness, method="function_calling"
        )
        decision = reviewer.invoke([
            SystemMessage(content=DOCTOR_FOLLOWUP_PROMPT),
            HumanMessage(content=f"病例摘要：\n{summary}\n\n违规草稿：\n{draft}"),
        ], extra_body={"enable_thinking": False})
        return _cards_from_questions(decision.questions, next_round) or _fallback_card(next_round)
    except Exception as exc:
        print(f"主治医生追问转卡片失败: {exc}")
        return _fallback_card(next_round)
