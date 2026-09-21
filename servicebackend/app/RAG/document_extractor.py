from langchain_openai import ChatOpenAI
from app.config.settings import settings
from langchain_community.document_loaders import PyPDFLoader
from typing import Optional, Any, List, Dict
from pydantic import BaseModel, Field
import os
import uuid

MEDICAL_EXTRACTOR_PROMPT = """
你是专业的医疗信息提取专家，从医疗文档中提取关键信息。
【必须提取的字段】
1. basic_info（基本信息）- 必须提取！包含：
   - name: 患者姓名（字符串）
   - age: 年龄（整数或字符串，如"30"或"30岁"）
   - gender: 性别（男/女）
   - phone: 联系电话（字符串，如"13812345678"）
   - email: 电子邮箱（字符串，如"zhangsan@example.com"）
   - address: 家庭地址（字符串）
   - id_card: 身份证号（字符串）
   注意：如果文档中有这些信息，必须提取；如果没有，可以省略该字段
   
2. symptoms（症状）- 症状列表，每项可以是字符串或对象
3. medical_history（既往病史）- 历史疾病列表
4. allergies（过敏史）- 过敏药物或食物列表
5. diagnoses（诊断结果）- 医生诊断列表
6. medications（用药记录）- 当前或历史用药列表
7. test_results（检查结果）- 化验/检查结果列表
8. doctor_notes（医生备注）- 其他备注（字符串或列表）

【提取规则】
1. 只提取文档中明确提到的信息，不要臆测或编造
2. 如果文档中有患者姓名、年龄、性别、电话、邮箱、地址等，必须填入 basic_info
3. 如果某类信息确实不存在，返回空列表 [] 或 null
4. 保持原文表述，不要改写
5. 必须返回符合 MedicalRecord 格式的 JSON
"""

# 医疗记录结构化数据
class MedicalRecord(BaseModel):
    # 基本信息
    basic_info: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="""
        基本信息对象，包含：
        name(姓名)，age(年龄)，gender(性别)，phone(电话)，email(邮箱)，address(地址)，id_card(身份证号)
        """
    )
    # 医疗信息
    symptoms: Any = Field(default_factory=list, description="症状列表")
    medical_history: Any = Field(default_factory=list, description="既往病史列表")
    allergies: Any = Field(default_factory=list, description="过敏史列表")
    diagnoses: Any = Field(default_factory=list, description="诊断结果列表")
    medications: Any = Field(default_factory=list, description="用药记录列表")
    test_results: Any = Field(default_factory=list, description="检查结果列表")
    doctor_notes: Any = Field(default=None, description="医生备注列表")


def extract_medical_info_from_pdf(file_path: str) -> MedicalRecord:
    try:
        print("开始处理 PDF")

        loader = PyPDFLoader(file_path)
        documents = loader.load()

        full_text = "\n\n".join([doc.page_content for doc in documents])
        print(f"加载成功，共{len(documents)}页，{len(full_text)}字符")

        # 初始化LLM
        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            temperature=0,
            api_key=settings.DASHSCOPE_API_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )

        structured_llm = llm.with_structured_output(MedicalRecord)

        # 构建提示词
        system_prompt = MEDICAL_EXTRACTOR_PROMPT
        result = structured_llm.invoke([
            ("system", system_prompt),
            ("human", f"请从以下医疗文档中提取信息:\n\n{full_text[:8000]}")
        ])
        print("信息提取成功")
        return result

    except Exception as e:
        print(f"处理失败: {str(e)}")
        return MedicalRecord()



# 将提取结构化信息保存至长记忆里
def save_extracted_info_to_store(store, user_id: str, record: MedicalRecord, filename: str) -> list:
    saved_items = []

    if record.basic_info:
        basic_text = ",".join([f"{k}:{v}" for k, v in record.basic_info.items() if v is not None])
        namespace = ("user_preference", str(user_id))
        store.put(
            namespace,
            f"basic_{filename}",
            {
                "key": "基本信息",
                "value": basic_text,
                "source": f"文档:{filename}"
            }
        )
        print(f"保存基本信息到长记忆里: {basic_text}")
        saved_items.append("基本信息:" + basic_text)

    # 保存医疗信息
    medical_parts = []
    medical_fields = {
        "symptoms": ("症状", record.symptoms),
        "medical_history": ("既往病史", record.medical_history),
        "allergies": ("过敏史", record.allergies),
        "diagnoses": ("诊断结果", record.diagnoses),
        "medications": ("用药记录", record.medications),
        "test_results": ("检查结果", record.test_results),
        "doctor_notes": ("医生备注", record.doctor_notes)
    }

    namespace = ("user_medical_history", str(user_id))
    for field_key, (field_label, items) in medical_fields.items():
        if items:
            if isinstance(items, str):
                items = [items]
            elif not isinstance(items, list):
                items = [items]
            content = "; ".join(str(item) for item in items if item is not None)
            if content.strip():
                item_id = f"doc_{field_key}_{filename}_{uuid.uuid4().hex[:6]}"
                store.put(
                    namespace,
                    item_id,
                    {
                        "category": field_label,
                        "content": f"{content} (来自文档:{filename})",
                        "source": f"文档:{filename}"
                    }
                )
                medical_parts.append(f"{field_label}: {content}")

    if medical_parts:
        medical_text = "\n".join(medical_parts)
        print("已保存医疗信息到长记忆")
        saved_items.append(f"医疗信息:{medical_text[:100]}... ")

    return saved_items