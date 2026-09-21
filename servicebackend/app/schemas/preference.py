from pydantic import BaseModel
from typing import Optional, Dict

class PreferenceSaveRequest(BaseModel):
    key: str
    value: str
    user_id: Optional[str] = None

class PreferenceResponse(BaseModel):
    message: str
    key: Optional[str] = None
    value: Optional[str] = None

class PreferenceListResponse(BaseModel):
    preferences: str
    data: Optional[Dict[str, str]] = None

class MedicalHistoryResponse(BaseModel):
    medical_history: str
