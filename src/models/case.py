from __future__ import annotations
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CaseStatus(str, Enum):
    NEW = "NEW"
    CLASSIFYING = "CLASSIFYING"
    CONFLICT_CHECK = "CONFLICT_CHECK"
    CONFLICT_FLAGGED = "CONFLICT_FLAGGED"
    ROUTING = "ROUTING"
    SCHEDULING = "SCHEDULING"
    AWAITING_DOCS = "AWAITING_DOCS"
    INTAKE_COMPLETE = "INTAKE_COMPLETE"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


class CaseUrgency(str, Enum):
    EMERGENCY = "emergency"
    TIME_SENSITIVE = "time_sensitive"
    STANDARD = "standard"


class CaseComplexity(str, Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class ClassificationResult(BaseModel):
    case_type: str
    urgency: CaseUrgency
    jurisdiction: str
    complexity: CaseComplexity
    key_entities: dict


class Case(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: CaseStatus = CaseStatus.NEW

    client_name: Optional[str] = None
    client_email: Optional[str] = None
    client_phone: Optional[str] = None

    case_type: Optional[str] = None
    urgency: Optional[str] = None
    jurisdiction: Optional[str] = None
    complexity: Optional[str] = None

    assigned_attorney_id: Optional[str] = None
    consult_datetime: Optional[str] = None

    intake_source: Optional[str] = None
    raw_intake_text: Optional[str] = None
    key_entities: dict = Field(default_factory=dict)

    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_client_contact_at: Optional[str] = None
    follow_up_count: int = 0

    def days_since_last_contact(self) -> float:
        if not self.last_client_contact_at:
            if not self.created_at:
                return 0.0
            ref = self.created_at
        else:
            ref = self.last_client_contact_at
        try:
            dt = datetime.fromisoformat(ref.replace("Z", "+00:00"))
            delta = datetime.now(timezone.utc) - dt
            return delta.total_seconds() / 86400
        except Exception:
            return 0.0


class IntakeRequest(BaseModel):
    client_name: Optional[str] = None
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    description: str
    matter_type: Optional[str] = None
    urgency: Optional[str] = None
    referral_source: Optional[str] = None
    intake_source: str = "web_form"
