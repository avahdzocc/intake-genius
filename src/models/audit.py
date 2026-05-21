from typing import Optional
from pydantic import BaseModel


class AuditEntry(BaseModel):
    case_id: str
    agent_observation: Optional[str] = None
    agent_reasoning: Optional[str] = None
    action_taken: Optional[str] = None
    action_result: Optional[str] = None
