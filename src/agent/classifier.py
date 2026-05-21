from pathlib import Path

import anthropic

from src.config import settings
from src.models.case import ClassificationResult, CaseUrgency, CaseComplexity

_PROMPT_PATH = Path(__file__).parent / "prompts" / "classifier.txt"
_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def classify_intake(raw_text: str) -> ClassificationResult:
    system_prompt = _PROMPT_PATH.read_text()

    response = await _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": f"Classify this legal intake:\n\n{raw_text}",
            }
        ],
        tools=[
            {
                "name": "submit_classification",
                "description": "Submit the structured classification result",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "case_type": {
                            "type": "string",
                            "enum": [
                                "personal_injury",
                                "family_law",
                                "criminal_defense",
                                "employment",
                                "real_estate",
                                "immigration",
                                "estate_planning",
                                "other",
                            ],
                        },
                        "urgency": {
                            "type": "string",
                            "enum": ["emergency", "time_sensitive", "standard"],
                        },
                        "jurisdiction": {"type": "string"},
                        "complexity": {
                            "type": "string",
                            "enum": ["simple", "moderate", "complex"],
                        },
                        "key_entities": {
                            "type": "object",
                            "properties": {
                                "client_name": {"type": "string"},
                                "adverse_parties": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "incident_date": {"type": "string"},
                                "location": {"type": "string"},
                            },
                        },
                    },
                    "required": ["case_type", "urgency", "jurisdiction", "complexity", "key_entities"],
                },
            }
        ],
        tool_choice={"type": "auto"},
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_classification":
            data = block.input
            return ClassificationResult(
                case_type=data["case_type"],
                urgency=CaseUrgency(data["urgency"]),
                jurisdiction=data["jurisdiction"],
                complexity=CaseComplexity(data["complexity"]),
                key_entities=data.get("key_entities", {}),
            )

    raise ValueError("Classifier did not return a structured result")
