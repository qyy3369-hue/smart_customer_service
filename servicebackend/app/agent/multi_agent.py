from app.agent.memory import get_long_term_memory
from app.agent.memory import get_short_term_memory,init_memory_system
from app.agent.state import MedicalAgentState
from langgraph.graph import StateGraph,END
from app.agent.supervisor import supervisor_node, evidence_supervisor_node
from app.agent.evidence import textbook_retriever_node, web_retriever_node
from app.agent.medical_examiner import medical_examiner_node
from app.agent.attending_doctor import attending_doctor_node
from app.agent.pharmacist import pharmacist_node
from app.agent.intake import intake_gate_node
from app.agent.intake_review import intake_review_node

#创建智能体入口

def create_medical_system():
    init_memory_system()

    checkpointer=get_short_term_memory()

    store=get_long_term_memory()

    builder=StateGraph(MedicalAgentState)

    builder.add_node("intake_gate", intake_gate_node)
    builder.add_node("intake_review", intake_review_node)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("medical_examiner", medical_examiner_node)
    builder.add_node("attending_doctor", attending_doctor_node)
    builder.add_node("pharmacist", pharmacist_node)
    builder.add_node("textbook_retriever", textbook_retriever_node)
    builder.add_node("evidence_supervisor", evidence_supervisor_node)
    builder.add_node("web_retriever", web_retriever_node)

    builder.set_entry_point("intake_gate")
    builder.add_conditional_edges(
        "intake_gate",
        lambda state: state.get("intake_route", "supervisor"),
        {"supervisor": "supervisor", "intake_review": "intake_review",
         "textbook_retriever": "textbook_retriever", "__end__": END},
    )
    builder.add_conditional_edges(
        "intake_review",
        lambda state: state.get("intake_route", "__end__"),
        {"textbook_retriever": "textbook_retriever", "__end__": END},
    )
    builder.add_conditional_edges(
        "supervisor",
        lambda state: state.get("next", "__end__"),
        {
            "medical_examiner": "medical_examiner",
            # 继续分析旧病例时也先重整病情，避免把“继续分析”当检索词。
            "attending_doctor": "medical_examiner",
            "pharmacist": "pharmacist",
            "__end__": END
        } 
    )
    builder.add_conditional_edges(
        "medical_examiner",
        lambda state: "textbook_retriever" if state.get("ready_for_doctor") else "__end__",
        {"textbook_retriever": "textbook_retriever", "__end__": END},
    )
    builder.add_edge("textbook_retriever", "evidence_supervisor")
    builder.add_conditional_edges(
        "evidence_supervisor",
        lambda state: state.get("next", "attending_doctor"),
        {"web_retriever": "web_retriever", "attending_doctor": "attending_doctor"},
    )
    builder.add_edge("web_retriever", "attending_doctor")
    builder.add_edge("attending_doctor", END)
    builder.add_edge("pharmacist", END)

    graph = builder.compile(checkpointer=checkpointer, store=store)

    return graph

# 别名兼容
create_medical_agent_system = create_medical_system
