import json
from typing import Optional

from pydantic import BaseModel, field_validator


class Attorney(BaseModel):
    id: str
    name: Optional[str] = None
    email: Optional[str] = None
    practice_areas: list[str] = []
    bar_admissions: list[str] = []
    max_active_cases: int = 25
    current_active_cases: int = 0

    @field_validator("practice_areas", "bar_admissions", mode="before")
    @classmethod
    def parse_json_list(cls, v: str | list) -> list:
        if isinstance(v, str):
            return json.loads(v)
        return v

    @property
    def capacity_ratio(self) -> float:
        if self.max_active_cases == 0:
            return 1.0
        return self.current_active_cases / self.max_active_cases
