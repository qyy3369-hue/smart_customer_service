import traceback
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from app.agent.tools import save_user_info, save_medical_info
from langchain.agents import create_agent
from app.agent.memory import get_user_long_memory, get_long_term_memory
from app.agent.state import MedicalAgentState
from app.agent.base import get_model
# 体检员提示词
MEDICAL_EXAMINER_PROMPT = """
【角色定义】
你是体检员，专门负责收集用户健康信息。

【回复规则】
- 回复简洁
- 每次只问2-3个关键问题
{memory_section}

【职责范围】
你的职责（只做这些）：
1. 优先收集本次症状和相关检查；姓名、联系方式不是进入教材分析的必要条件
2. 收集症状信息：主要症状、持续时间、严重程度
3. 收集病史信息：既往病史、过敏史、家族病史
4. 【重要 - 必须执行】当用户提供个人信息时，立即调用 save_user_info 工具保存到长记忆：
   - 用户提供姓名（如"我叫张三"、"张三"）→ 调用 save_user_info
   - 用户提供年龄（如"我30岁"、"30岁"）→ 调用 save_user_info
   - 用户提供性别（如"我是男性"、"男"、"女性"、"女"）→ 调用 save_user_info
   - 用户提供联系方式（如"电话13812345678"）→ 调用 save_user_info
   - 用户同时提供多个信息（如"张三，30岁，男"）→ 调用 save_user_info 一次性保存所有字段
5. 【重要 - 必须执行】当用户提供或修改病史信息时，立即调用 save_medical_info 工具保存到长记忆：
   - 症状描述（如"肚子痛"、"头痛"）→ 类别用"症状描述"
   - 过敏史（如"对青霉素过敏"）→ 类别用"过敏史"
   - 既往病史（如"做过阑尾手术"、"有高血压"）→ 类别用"既往病史"
6. 【混合信息识别】用户可能在同一句话中提供多种信息，必须识别并分别保存：
   - 例如："男，持续了一上午了，中度"
     * "男" → 调用 save_user_info 保存性别
     * "持续了一上午了，中度" → 调用 save_medical_info 保存症状
7. 收集到信息后立即保存，不要告诉用户已保存
8. 信息收集够了就生成健康信息摘要，不要自行作诊断或建议具体科室
9. 用户之前说过的病史、过敏史可能不完整，回复时应告诉用户当前已知的信息，并询问是否还有补充

不是你的职责（不要做）：
- 不要诊断疾病、不要开药，那是医生的工作
- 不要指导用药，那是药师的工作
- 不要做导诊引导，那是顾问的工作

【收集策略】
- 重要：如果用户说上传了文档，你应该已经从"用户已有信息"中看到了文档提取的内容，直接基于这些信息回复，不要说无法读取PDF
- 用户可选择上传医疗文档，但不能把上传当成分析的前置条件
- 用户选择上传文档后，说明文档信息已自动提取并保存在你的上下文中，你可以直接读取
- 只有在用户不上传文档或文档信息不完整时，才需要手动收集用户信息
- 如果确实需要报告，可提醒用户上传；已有足够症状信息时不要重复索要
- 已有的信息不要重复问，但要确认是否完整
- 每轮只问1-2个最关键的缺失信息
- 不要一次列出所有问题
- 如果用户提到过敏史或病史，主动询问细节（如过敏药物名称、发病时间等）

【回复话术示例】
- "为了更准确地为您分析，您可以点击下方的「上传医疗文档」按钮，上传病历、体检报告或化验单，系统会自动提取信息。"
- "如果您暂时不方便上传，可以告诉我您的姓名、年龄和主要症状吗？"

【语言风格】
简洁友好，像医院导检台护士。
"""


class CaseAssessment(BaseModel):
    """Explicit handoff decision; never inferred from free-form reply wording."""

    chief_complaint: str = Field(description="本次主要不适；未知则留空")
    duration: str = Field(description="本次不适持续时间；未知则留空")
    summary: str = Field(description="只含本次相关医学事实的简短摘要，不含姓名电话或诊断")
    ready_for_doctor: bool = Field(description="信息是否足以做有条件的教材分析")
    follow_up_question: str = Field(description="如果信息不足，最关键的一个追问")


ASSESSMENT_PROMPT = """你只判断本次病例信息是否足以交给医学分析助手，不做诊断。
优先看最新症状对话；既往病史不是本次病因。姓名、联系方式、上传报告均非必要条件。
至少要知道主要不适、持续时间，以及本次疼痛的部位或性质/程度，才可标记 ready_for_doctor=true。
如尚未询问可能改变就医紧急程度的伴随情况，先用简短追问确认，不能仅凭“症状+时长”就交给医生。
其他非关键不明信息应写进摘要供医生注明不确定性，不要为了追求完整而反复追问。
summary 只保留用户明确提供的症状、程度、伴随症状、相关病史/过敏和检查事实。
不猜测疾病，不建议科室，不放入姓名、电话。信息不足时只给一个最有价值的问题。
用户历史信息是背景，不可把其中旧症状自动当成本次症状。"""


def assess_case(model, messages: list, user_context: str) -> CaseAssessment:
    dialogue = "\n".join(
        f"{'用户' if isinstance(msg, HumanMessage) else '助手'}：{msg.content}"
        for msg in messages[-12:]
        if isinstance(msg, (HumanMessage, AIMessage)) and isinstance(msg.content, str)
    )
    assessor = model.with_structured_output(CaseAssessment, method="function_calling")
    return assessor.invoke([
        SystemMessage(content=ASSESSMENT_PROMPT),
        HumanMessage(content=f"用户历史信息：\n{user_context}\n\n最近对话：\n{dialogue}"),
    ], extra_body={"enable_thinking": False})

#体检员节点
def medical_examiner_node(state:MedicalAgentState):
    try:
        model=get_model(enable_thinking=False)

        messages=state["messages"]

        user_id=state["user_id"]

        store=get_long_term_memory()
        #用户个人信息和医疗信息
        user_context = get_user_long_memory(user_id=user_id, store=store)


        #初始化用户的记忆信息
        memory_section=""
        if user_context:
            memory_section=f"\n====用户已有信息（不要重复去问）====\n{user_context}\n===已有信息结束==="\
            
        #自己处理
        agent=create_agent(
            model=model,
            tools=[save_user_info,save_medical_info],
            system_prompt=MEDICAL_EXAMINER_PROMPT.format(memory_section=memory_section)
        )

        #构建配置信息
        config={
            "configurable":{
                "user_id":user_id,
                "thread_id":state["thread_id"]
            }
        }
        # 保存用户本轮提供的事实；最终回复由结构化评估决定，避免体检员越权导诊。
        agent.invoke({"messages": messages}, config=config)

        assessment = assess_case(model, messages, user_context)
        ready = bool(
            assessment.ready_for_doctor
            and assessment.chief_complaint.strip()
            and assessment.duration.strip()
        )
        summary = assessment.summary.strip()
        if ready:
            missing_facts = [
                fact for fact in (assessment.chief_complaint.strip(), assessment.duration.strip())
                if fact not in summary
            ]
            summary = "；".join([*missing_facts, summary] if summary else missing_facts)
            return {
                "case_summary": summary,
                "ready_for_doctor": True,
                "next": "attending_doctor",
            }

        question = assessment.follow_up_question.strip() or "主要哪里不舒服，持续多久了？"
        summary_line = f"目前了解到：{summary}\n" if summary else ""
        return {
            "messages": [AIMessage(content=f"【体检员】\n{summary_line}还需要了解：{question}")],
            "case_summary": summary or None,
            "ready_for_doctor": False,
            "next": "__end__"
        }

    except Exception as e:
        print(f"体检员执行出错:{e}")
        print(traceback.format_exc())
        return{
            "messages":[
                AIMessage(content="【体检员】\n暂时无法整理本次信息，请描述主要不适和持续时间后重试。")
            ],
            "case_summary": None,
            "ready_for_doctor": False,
            "next":"__end__"
        }
