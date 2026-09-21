from typing import Optional
from langgraph.graph import add_messages
from sqlalchemy.util.typing import Annotated
from typing import TypedDict,List


#状态模块
class MedicalAgentState(TypedDict):
    #消息列表
    messages:Annotated[list,add_messages]

    user_id:str
    
    thread_id:str

    medical_documents:List

    diagnosis:Optional[str]

    prescription:Optional[str]

    next:Optional[str]

    # 每轮重置；体检员用结构化摘要控制是否交给医生。
    case_summary:Optional[str]
    ready_for_doctor:bool

    # 只记录医生回答实际引用的教材来源。
    sources:List[dict]
    retrieval_status:Optional[str]

    # 教材检索 -> 监督者证据路由 -> 可选联网 -> 医生。
    textbook_hits:List[dict]
    textbook_status:Optional[str]
    unavailable_books:List[str]
    retrieval_queries:List[str]
    evidence_route:Optional[str]
    evidence_reason:Optional[str]
    web_hits:List[dict]
    web_status:Optional[str]

    # Persisted structured intake; submission is reset after each invocation.
    intake_questions:List[dict]
    intake_answers:dict
    intake_complaint:Optional[str]
    intake_round:int
    intake_submission:Optional[dict]
    intake_route:Optional[str]
    intake_review_reason:Optional[str]
    stream_response:bool
