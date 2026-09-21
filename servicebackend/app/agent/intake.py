"""Low-cost, structured pain intake before evidence retrieval."""

import re

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.intake_review import legacy_doctor_followup_cards


PAIN_COMPLAINT = re.compile(r"疼|痛|酸胀|酸痛|刺痛|胀痛|灼痛|不适|麻木")
MEDICATION_QUERY = re.compile(r"止痛药|吃什么药|用什么药|药物|剂量|副作用|能不能吃")
FOLLOW_UP_DETAIL = re.compile(
    r"(?:\d+|[一二两三四五六七八九十百半几数]+)\s*(?:小时|天|周|月|年)|"
    r"半天|上午|下午|晚上|左|右|双侧|两边|靠近|手肘|肘部|手腕|肩|小臂|前臂|上臂|"
    r"酸|胀|刺|麻|无力|肿|发热|受伤|扭伤|久坐|运动|提重物"
)
BACK_PAIN = re.compile(r"背|后背|腰")
UPPER_LIMB_PAIN = re.compile(r"肩|上臂|手臂|胳膊|小臂|前臂|肘|手腕|手掌|手指")
DURATION = re.compile(r"(?:\d+|[一二两三四五六七八九十百半几数]+)\s*(?:小时|天|周|月|年)|半天|一上午|一下午|一晚上|昨[天日晚]|今[天日晚]|刚刚|刚才|近期|最近")

FIRST_QUESTIONS = [
    {"id": "location", "title": "背部哪里疼？", "hint": "可多选；如果选项不贴切，可在“其他”里补充。", "options": [
        {"value": "upper", "label": "偏上"}, {"value": "middle", "label": "偏中部"},
        {"value": "lower", "label": "偏下 / 腰部"}, {"value": "spine", "label": "脊椎正中"},
        {"value": "leg", "label": "延伸到腿部"}, {"value": "unsure", "label": "说不清"},
        {"value": "other", "label": "其他"},
    ]},
    {"id": "feeling", "title": "疼痛更接近哪种感觉？", "hint": "可以同时选择多项。", "options": [
        {"value": "ache", "label": "酸胀 / 钝痛"}, {"value": "sharp", "label": "刺痛"},
        {"value": "movement", "label": "活动时更痛"}, {"value": "rest", "label": "休息时也痛"},
        {"value": "unsure", "label": "说不清"}, {"value": "other", "label": "其他"},
    ]},
    {"id": "warning", "title": "现在有下面这些情况吗？", "hint": "若有，请如实选择；都没有请选“以上均无”。", "options": [
        {"value": "leg_weakness", "label": "双腿明显无力 / 麻木"},
        {"value": "saddle", "label": "会阴部感觉异常"},
        {"value": "bladder", "label": "新出现排尿或排便控制异常"},
        {"value": "chest", "label": "胸痛或呼吸困难"},
        {"value": "trauma", "label": "严重外伤后出现"},
        {"value": "fever", "label": "发热或明显不适"},
        {"value": "worsening", "label": "突然很痛或快速加重"},
        {"value": "none", "label": "以上均无"},
        {"value": "unsure", "label": "不确定"},
        {"value": "other", "label": "其他"},
    ]},
]

UPPER_LIMB_QUESTIONS = [
    {"id": "location", "title": "手臂具体哪里不舒服？", "hint": "左右侧和具体部位都可以多选。", "options": [
        {"value": "left_arm", "label": "左侧"}, {"value": "right_arm", "label": "右侧"},
        {"value": "both_arms", "label": "双侧"}, {"value": "shoulder", "label": "肩部"},
        {"value": "upper_arm", "label": "上臂"}, {"value": "elbow", "label": "手肘附近"},
        {"value": "forearm", "label": "小臂 / 前臂"}, {"value": "wrist", "label": "手腕附近"},
        {"value": "hand", "label": "延伸到手部"}, {"value": "unsure", "label": "说不清"},
        {"value": "other", "label": "其他"},
    ]},
    {"id": "feeling", "title": "不舒服更接近哪种感觉？", "hint": "可同时选择多项。", "options": [
        {"value": "ache", "label": "酸胀 / 钝痛"}, {"value": "sharp", "label": "刺痛"},
        {"value": "numb", "label": "麻木 / 发麻"}, {"value": "weak", "label": "无力"},
        {"value": "swollen", "label": "肿胀"}, {"value": "movement", "label": "活动时更明显"},
        {"value": "rest", "label": "休息时也不舒服"}, {"value": "unsure", "label": "说不清"},
        {"value": "other", "label": "其他"},
    ]},
    {"id": "warning", "title": "现在有下面这些情况吗？", "hint": "若有请如实选择；都没有请选“以上均无”。", "options": [
        {"value": "major_trauma", "label": "严重外伤或明显变形"},
        {"value": "sudden_weakness", "label": "手臂突然明显无力 / 麻木"},
        {"value": "poor_circulation", "label": "手部发白、发紫或冰冷"},
        {"value": "chest", "label": "胸痛或呼吸困难"},
        {"value": "fever", "label": "红肿发热或全身不适"},
        {"value": "worsening", "label": "疼痛突然很强或快速加重"},
        {"value": "none", "label": "以上均无"}, {"value": "unsure", "label": "不确定"},
        {"value": "other", "label": "其他"},
    ]},
]

GENERIC_PAIN_QUESTIONS = [
    {"id": "location", "title": "具体哪里不舒服？", "hint": "可多选；没有合适选项可在“其他”中说明。", "options": [
        {"value": "left", "label": "偏左侧"}, {"value": "right", "label": "偏右侧"},
        {"value": "both", "label": "双侧 / 两边"}, {"value": "central", "label": "正中"},
        {"value": "surface", "label": "靠近表面"}, {"value": "deep", "label": "感觉较深"},
        {"value": "radiating", "label": "向其他部位延伸"}, {"value": "unsure", "label": "说不清"},
        {"value": "other", "label": "其他"},
    ]},
    {"id": "feeling", "title": "不舒服更接近哪种感觉？", "hint": "可同时选择多项。", "options": [
        {"value": "ache", "label": "酸胀 / 钝痛"}, {"value": "sharp", "label": "刺痛"},
        {"value": "burning", "label": "灼热感"}, {"value": "numb", "label": "麻木 / 发麻"},
        {"value": "movement", "label": "活动时更明显"}, {"value": "rest", "label": "休息时也不舒服"},
        {"value": "unsure", "label": "说不清"}, {"value": "other", "label": "其他"},
    ]},
    {"id": "warning", "title": "现在有下面这些情况吗？", "hint": "若有请如实选择；都没有请选“以上均无”。", "options": [
        {"value": "major_trauma", "label": "严重外伤后出现"},
        {"value": "sudden_weakness", "label": "突然无力、麻木或意识异常"},
        {"value": "chest", "label": "胸痛或呼吸困难"},
        {"value": "fever", "label": "发热或明显全身不适"},
        {"value": "worsening", "label": "疼痛突然很强或快速加重"},
        {"value": "none", "label": "以上均无"}, {"value": "unsure", "label": "不确定"},
        {"value": "other", "label": "其他"},
    ]},
]

SECOND_QUESTIONS = [
    {"id": "duration", "title": "这次疼了多久？", "hint": "如果反复发作，也可在“其他”里说明。", "options": [
        {"value": "hours", "label": "几小时内"}, {"value": "days", "label": "1–3 天"},
        {"value": "week", "label": "约一周"}, {"value": "long", "label": "更久 / 反复出现"},
        {"value": "unsure", "label": "不确定"}, {"value": "other", "label": "其他"},
    ]},
    {"id": "trigger", "title": "出现前有什么明显诱因？", "hint": "可多选，没有明显诱因可直接选择。", "options": [
        {"value": "lifting", "label": "搬重物 / 扭伤"}, {"value": "sitting", "label": "久坐"},
        {"value": "exercise", "label": "运动后"}, {"value": "none", "label": "没有明显诱因"},
        {"value": "unsure", "label": "不确定"}, {"value": "other", "label": "其他"},
    ]},
]

SECOND_WITH_DURATION = [
    {"id": "severity", "title": "目前疼痛影响到什么程度？", "hint": "按此刻的感受选择。", "options": [
        {"value": "mild", "label": "轻微，不影响活动"},
        {"value": "moderate", "label": "明显，活动受影响"},
        {"value": "severe", "label": "很强，难以正常活动"},
        {"value": "unsure", "label": "说不清"}, {"value": "other", "label": "其他"},
    ]},
    SECOND_QUESTIONS[1],
]

QUESTION_BANK = (FIRST_QUESTIONS + UPPER_LIMB_QUESTIONS + GENERIC_PAIN_QUESTIONS
                 + SECOND_QUESTIONS + SECOND_WITH_DURATION)
OPTION_LABELS = {option["value"]: option["label"]
                 for question in QUESTION_BANK for option in question["options"]}
URGENT = {"leg_weakness", "saddle", "bladder", "chest", "trauma", "major_trauma",
          "sudden_weakness", "poor_circulation"}
URGENT_FREE_TEXT = re.compile(r"(?:大小便|排尿|排便).{0,5}(?:失禁|控制不了|困难|异常)|会阴.{0,4}(?:麻木|无感觉)|双腿.{0,4}(?:无力|麻木)|胸痛|呼吸困难|车祸|严重外伤")


def _urgent_in_free_text(answers: dict) -> bool:
    for answer in answers.values():
        text = answer.get("other_text", "")
        for match in URGENT_FREE_TEXT.finditer(text):
            if not re.search(r"没有|并无|否认|未见|无", text[max(0, match.start() - 5):match.start()]):
                return True
    return False


def _normalize(questions: list[dict], submission: dict) -> dict | None:
    if set(submission) != {q["id"] for q in questions}:
        return None
    result = {}
    for question in questions:
        answer = submission.get(question["id"])
        if not isinstance(answer, dict):
            return None
        choices = answer.get("choices", [])
        other = answer.get("other_text", "")
        option_labels = {option["value"]: option["label"] for option in question["options"]}
        allowed = set(option_labels)
        if (not isinstance(choices, list) or not choices or len(choices) > len(allowed)
                or any(not isinstance(choice, str) or choice not in allowed for choice in choices)
                or len(set(choices)) != len(choices)
                or not isinstance(other, str) or len(other) > 300
                or ("other" in choices and not other.strip())
                or ("other" not in choices and bool(other.strip()))
                or ("none" in choices and len(choices) > 1)
                or ("unsure" in choices and len(choices) > 1)):
            return None
        result[question["id"]] = {
            "choices": choices,
            "other_text": other.strip(),
            "display": [option_labels[choice] for choice in choices if choice != "other"],
        }
    return result


def _summary(complaint: str, answers: dict) -> str:
    parts = [f"用户原始描述：{complaint}"]
    for key, answer in answers.items():
        values = answer.get("display") or [
            OPTION_LABELS.get(choice, choice) for choice in answer["choices"] if choice != "other"
        ]
        if answer["other_text"]:
            values.append(f"其他：{answer['other_text']}")
        parts.append(f"{key}：{'、'.join(values)}")
    return "；".join(parts)


def _recent_complaint(messages: list) -> str:
    """Recover a symptom followed by a short answer such as '半天 手肘 酸'."""
    human_texts = [message.content.strip() for message in messages[-10:]
                   if isinstance(message, HumanMessage)
                   and isinstance(message.content, str) and message.content.strip()]
    if not human_texts:
        return ""
    latest = human_texts[-1]
    if PAIN_COMPLAINT.search(latest) and not MEDICATION_QUERY.search(latest):
        return latest
    if len(latest) <= 80 and FOLLOW_UP_DETAIL.search(latest):
        prior = next((text for text in reversed(human_texts[:-1])
                      if PAIN_COMPLAINT.search(text) and not MEDICATION_QUERY.search(text)), "")
        if prior:
            return f"{prior}；补充：{latest}"
    return ""


def _questions_for(complaint: str) -> list[dict]:
    if BACK_PAIN.search(complaint):
        return FIRST_QUESTIONS
    if UPPER_LIMB_PAIN.search(complaint):
        return UPPER_LIMB_QUESTIONS
    return GENERIC_PAIN_QUESTIONS


def suggested_intake(messages: list) -> tuple[str, list[dict]]:
    """Return a deterministic complaint and cards without changing graph state."""
    complaint = _recent_complaint(messages)
    return complaint, (_questions_for(complaint) if complaint else [])


def intake_gate_node(state: dict) -> dict:
    """Ask at most two batches; avoid all LLM/retrieval calls until intake completes."""
    submission = state.get("intake_submission")
    pending = state.get("intake_questions") or []
    recovered_complaint = ""
    if submission is not None and not pending:
        # Supports cards reconstructed when an older text-only examiner turn is reopened.
        # The final message is the card preview, so recover from the earlier conversation.
        prior_messages = (state.get("messages") or [])[:-1]
        recovered_complaint, suggested = suggested_intake(prior_messages)
        pending = legacy_doctor_followup_cards(prior_messages) or suggested
    if submission is not None and pending:
        normalized = _normalize(pending, submission)
        if normalized is None:
            return {"messages": [AIMessage(content="请选择每张卡片的选项；若选“其他”，请补充文字后重试。")],
                    "intake_questions": pending, "intake_submission": None, "intake_route": "__end__"}
        answers = {**(state.get("intake_answers") or {}), **normalized}
        complaint = state.get("intake_complaint") or recovered_complaint or "疼痛不适"
        warning = set(answers.get("warning", {}).get("choices", []))
        if warning & URGENT or _urgent_in_free_text(answers):
            return {"messages": [AIMessage(content="你选择了需要尽快线下评估的情况。请尽快前往急诊；若症状正在加重或行动不便，请寻求当地急救帮助。线上问答不能据此确定病因，先不要等待进一步卡片或自行用药。")],
                    "intake_answers": answers, "intake_questions": [], "intake_submission": None,
                    "intake_route": "__end__", "ready_for_doctor": False}
        if warning & {"fever", "worsening"}:
            return {"messages": [AIMessage(content="你选择了发热、明显不适或疼痛突然加重等情况，建议尽快线下就医评估，不要只靠线上问答等待病情变化。如果同时出现胸痛、呼吸困难、双腿明显无力或新出现大小便控制异常，请前往急诊。")],
                    "intake_answers": answers, "intake_questions": [], "intake_submission": None,
                    "intake_route": "__end__", "ready_for_doctor": False}
        # The first batch deliberately does not ask everything. Always finish the
        # deterministic second batch before any retrieval or doctor generation.
        if state.get("intake_round", 1) == 1:
            follow_up = SECOND_WITH_DURATION if DURATION.search(complaint) else SECOND_QUESTIONS
            return {"messages": [AIMessage(content="还差两项信息，请继续选择。完成后再生成初步判断。")],
                    "intake_answers": answers, "intake_questions": follow_up,
                    "intake_round": 2, "intake_submission": None, "intake_route": "__end__"}
        summary = _summary(complaint, answers)
        return {"intake_answers": answers, "intake_questions": [], "intake_submission": None,
                "intake_route": "intake_review", "case_summary": summary,
                "ready_for_doctor": False}

    complaint = _recent_complaint(state.get("messages", []))
    if submission is not None:
        return {"messages": [AIMessage(content="这组问诊卡片已失效，请重新描述当前不适。")],
                "intake_route": "__end__", "intake_submission": None}
    if complaint:
        return {"messages": [AIMessage(content="先了解几项关键情况，再给你有条件的分析。可多选，也可以在“其他”中补充。")],
                "intake_complaint": complaint, "intake_answers": {},
                "intake_questions": _questions_for(complaint),
                "intake_round": 1, "intake_route": "__end__", "ready_for_doctor": False}
    return {"intake_questions": [], "intake_answers": {}, "intake_complaint": None,
            "intake_route": "supervisor", "intake_submission": None}
