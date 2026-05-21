"""Required documents per case type, used to populate missing_documents and SMS requests."""

REQUIRED_DOCS: dict[str, list[str]] = {
    "personal_injury": [
        "police_report",
        "medical_records",
        "insurance_information",
        "photos_of_scene",
    ],
    "family_law": [
        "marriage_certificate",
        "financial_statements",
        "tax_returns_last_2_years",
    ],
    "criminal_defense": [
        "arrest_record",
        "police_report",
        "bail_documents",
    ],
    "employment": [
        "employment_contract",
        "termination_letter",
        "relevant_written_communications",
        "pay_stubs",
    ],
    "real_estate": [
        "lease_or_purchase_agreement",
        "property_deed",
        "correspondence_with_other_party",
    ],
    "immigration": [
        "passport",
        "visa_documents",
        "i94_record",
    ],
    "estate_planning": [
        "existing_will_or_trust",
        "list_of_assets",
        "beneficiary_information",
    ],
    "other": [],
}


def get_required_docs(case_type: str) -> list[str]:
    return REQUIRED_DOCS.get(case_type, REQUIRED_DOCS["other"])


def friendly_doc_name(doc_type: str) -> str:
    return doc_type.replace("_", " ").title()
