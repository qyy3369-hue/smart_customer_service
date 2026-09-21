import uuid
import traceback
from app.agent.memory import save_user_long_memory
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.messages import AIMessage
from app.agent.tools import search_web, save_user_info, save_medical_info
from langchain.agents import create_agent
from app.agent.memory import get_user_long_memory, get_long_term_memory
from app.agent.state import MedicalAgentState
from app.agent.base import get_model
from app.RAG.book_rag import search_pharmacology, format_pharmacology_context


# 药师提示词
PHARMACIST_PROMPT = """
【角色定义】
你是药师，只负责药品和用药相关问题。

【回复规则】
- 回复简洁实用
- 只回答用户实际询问的范围；仅问药理机制时，不主动扩展为个人用药处方
- 教材是学习资料，不把书中剂量直接当作对具体用户的处方

【职责范围】
你的职责（只做这些）：
1. 根据诊断和处方，给出详细用药指导：药名、剂量、服用时间、注意事项
2. 审核过敏禁忌，有问题直接提醒并给替代方案
3. 药品咨询：药物副作用、相互作用、存储方式
4. 提供药品替代方案（经济型/同类替代）
5. 讨论具体用药时说明相关禁忌，并询问用户是否有胃病、肝肾功能问题、怀孕等情况；有风险时提醒咨询医生评估，不直接决定替换药物
6. 可以使用 search_web 工具搜索药物相关知识（如药物详细信息、最新用药指南）
7. 优先参考提供的《药理学》检索片段；使用教材内容时标明“《药理学》第九版，PDF第X页”
8. 教材未覆盖或检索失败时如实说明，不要编造页码；最新用药信息应另行核实
9. 只有检索片段直接支持的说法才可标注教材页码，不要把模型常识冒充教材原文

不是你的职责（不要做）：
- 不要诊断疾病，那是医生的工作
- 不要收集用户基本信息，那是体检员的工作
- 不要做导诊引导，那是顾问的工作

【语言风格】
简明扼要，像药房窗口的药师。
"""


#药师节点
def pharmacist_node(state:MedicalAgentState):
    try:
        model=get_model()

        messages=state["messages"]

        user_id=state["user_id"]

        store=get_long_term_memory()

        #从状态中获取诊断的信息
        diagnosis=state.get("diagnosis","")
        
        #如果有诊断信息需要添加到列表末尾
        if diagnosis:
            messages=messages+[SystemMessage(content=f"\n\n【诊断信息】\n\n{diagnosis}")]

        #用户个人信息和医疗信息
        user_context = get_user_long_memory(user_id=user_id, store=store)

        latest_question = next(
            (msg.content for msg in reversed(messages)
             if isinstance(msg, HumanMessage) and isinstance(msg.content, str)),
            "",
        )
        try:
            textbook_hits = search_pharmacology(latest_question) if latest_question else []
            textbook_context = format_pharmacology_context(textbook_hits)
        except Exception as exc:
            print(f"药理学检索不可用: {exc}")
            textbook_context = "教材知识库暂时不可用。不要声称答案来自《药理学》，也不要编造页码。"


        #初始化用户的记忆信息
        if user_context:
            system_message=SystemMessage(content=f"用户历史信息（特别注意过敏史）：\n\n{user_context}")
            messages=[system_message]+messages
        #自己处理
        agent=create_agent(
            model=model,
            tools=[search_web,save_medical_info],
            system_prompt=PHARMACIST_PROMPT + "\n\n【教材检索上下文】\n" + textbook_context)
        

        #构建配置信息
        config={
            "configurable":{
                "user_id":user_id,
                "thread_id":state["thread_id"]
            }
        }
        response=agent.invoke({"messages":messages},config=config)
        
        # 从后往前找最后一条有实际文本内容的 AIMessage
        ai_msg = None
        if response["messages"]:
            for msg in reversed(response["messages"]):
                if isinstance(msg, AIMessage) and msg.content and msg.content.strip():
                    ai_msg = msg
                    break
        
        if ai_msg:
            if not ai_msg.content.startswith("【药师】"):
                ai_msg.content = "【药师】\n" + ai_msg.content
            
            #保存处方
            save_user_long_memory(
                store=store,
                namespace=("user_medical_record", user_id, "prescription"),
                item_id=f"prescription_{uuid.uuid4().hex[:8]}",
                data={"content": ai_msg.content, "timestamp": str(uuid.uuid1())} 
            )
        return {
            "messages": response["messages"],
            "prescription": ai_msg.content if ai_msg else None,
            "next": "__end__"
        } 

    except Exception as e:
        print(f"药师执行出错:{e}")
        print(traceback.format_exc())
        return{
            "messages":[
                AIMessage(content=f"【药师】\n抱歉，系统开小差了，请稍后再试。{str(e)}")
            ],
            "next":"__end__"
        }
