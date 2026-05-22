"""Seed sample data for development and demo deployments."""
import asyncio
import json
import logging
import uuid

import aiosqlite

from src.config import settings

logger = logging.getLogger(__name__)

# Stable IDs so cases can reference attorneys consistently across deploys
ATTORNEY_CHEN = "a0000000-0000-0000-0000-000000000001"
ATTORNEY_RIVERA = "a0000000-0000-0000-0000-000000000002"
ATTORNEY_PATEL = "a0000000-0000-0000-0000-000000000003"
ATTORNEY_OBRIEN = "a0000000-0000-0000-0000-000000000004"
ATTORNEY_OKAFOR = "a0000000-0000-0000-0000-000000000005"

ATTORNEYS = [
    {
        "id": ATTORNEY_CHEN,
        "name": "Sarah Chen",
        "email": "schen@firm.com",
        "practice_areas": json.dumps(["personal_injury", "medical_malpractice"]),
        "bar_admissions": json.dumps(["CA", "NY"]),
        "max_active_cases": 25,
        "current_active_cases": 18,
    },
    {
        "id": ATTORNEY_RIVERA,
        "name": "Marcus Rivera",
        "email": "mrivera@firm.com",
        "practice_areas": json.dumps(["family_law", "divorce", "child_custody"]),
        "bar_admissions": json.dumps(["CA", "TX"]),
        "max_active_cases": 20,
        "current_active_cases": 12,
    },
    {
        "id": ATTORNEY_PATEL,
        "name": "Priya Patel",
        "email": "ppatel@firm.com",
        "practice_areas": json.dumps(["immigration", "employment"]),
        "bar_admissions": json.dumps(["CA", "WA", "OR"]),
        "max_active_cases": 30,
        "current_active_cases": 8,
    },
    {
        "id": ATTORNEY_OBRIEN,
        "name": "James O'Brien",
        "email": "jobrien@firm.com",
        "practice_areas": json.dumps(["criminal_defense", "DUI"]),
        "bar_admissions": json.dumps(["CA"]),
        "max_active_cases": 15,
        "current_active_cases": 11,
    },
    {
        "id": ATTORNEY_OKAFOR,
        "name": "Linda Okafor",
        "email": "lokafor@firm.com",
        "practice_areas": json.dumps(["real_estate", "estate_planning", "probate"]),
        "bar_admissions": json.dumps(["CA", "NV"]),
        "max_active_cases": 25,
        "current_active_cases": 5,
    },
]

DEMO_CASES = [
    {
        "id": "c0000000-0000-0000-0000-000000000001",
        "status": "INTAKE_COMPLETE",
        "client_name": "Maria Santos",
        "client_email": "maria.santos@example.com",
        "client_phone": "+15551234001",
        "case_type": "personal_injury",
        "urgency": "high",
        "jurisdiction": "CA",
        "complexity": "high",
        "assigned_attorney_id": ATTORNEY_CHEN,
        "consult_datetime": "2026-05-16T10:00:00",
        "intake_source": "web_form",
        "raw_intake_text": "Rear-ended on I-280 by a commercial truck on May 8, 2026. Suffered herniated disc and concussion. Currently unable to work as a nurse. $42,000 in medical bills so far with ongoing physical therapy. Trucking company's insurer has contacted me.",
        "key_entities_json": json.dumps({"adverse_parties": ["ABC Trucking LLC"], "incident_date": "2026-05-08", "location": "I-280, San Jose, CA"}),
        "created_at": "2026-05-09T08:15:00",
        "updated_at": "2026-05-16T11:00:00",
        "follow_up_count": 1,
    },
    {
        "id": "c0000000-0000-0000-0000-000000000002",
        "status": "AWAITING_DOCS",
        "client_name": "Robert Kim",
        "client_email": "r.kim@example.com",
        "client_phone": "+15551234002",
        "case_type": "employment",
        "urgency": "standard",
        "jurisdiction": "CA",
        "complexity": "moderate",
        "assigned_attorney_id": ATTORNEY_PATEL,
        "consult_datetime": "2026-05-20T14:00:00",
        "intake_source": "referral",
        "raw_intake_text": "Wrongful termination from TechCorp Inc. after filing an internal complaint about unsafe working conditions in the warehouse. Employed for 6 years, fired two weeks after the complaint. Have emails from manager referencing the complaint.",
        "key_entities_json": json.dumps({"adverse_parties": ["TechCorp Inc."], "incident_date": "2026-05-01", "location": "TechCorp warehouse, Oakland, CA"}),
        "created_at": "2026-05-12T11:30:00",
        "updated_at": "2026-05-18T09:00:00",
        "follow_up_count": 0,
    },
    {
        "id": "c0000000-0000-0000-0000-000000000003",
        "status": "SCHEDULING",
        "client_name": "Alex Johnson",
        "client_email": None,
        "client_phone": "+15550001234",
        "case_type": "personal_injury",
        "urgency": "standard",
        "jurisdiction": "CA",
        "complexity": "moderate",
        "assigned_attorney_id": ATTORNEY_CHEN,
        "intake_source": "web_form",
        "raw_intake_text": "I was in a car accident on the 101 last Tuesday. The other driver ran a red light.",
        "key_entities_json": json.dumps({"adverse_parties": ["unknown driver"], "incident_date": "2026-05-07", "location": "US-101, CA"}),
        "created_at": "2026-05-14T02:48:54",
        "updated_at": "2026-05-14T02:48:56",
        "follow_up_count": 0,
    },
    {
        "id": "c0000000-0000-0000-0000-000000000004",
        "status": "CONFLICT_FLAGGED",
        "client_name": "Jane Martinez",
        "client_email": "jane.martinez.test@example.com",
        "client_phone": "+15558675309",
        "case_type": "personal_injury",
        "urgency": "standard",
        "jurisdiction": "CA",
        "complexity": "moderate",
        "intake_source": "phone",
        "raw_intake_text": "Client slipped on an unmarked wet floor at a grocery store on May 10, 2026. Sustained a fractured wrist and soft tissue damage to her lower back. She was taken by ambulance to St. Mary's Hospital. She has medical bills totaling approximately $14,000 and missed two weeks of work. Store has not responded to her attempts to contact them.",
        "key_entities_json": json.dumps({"adverse_parties": ["grocery store (unnamed)"], "incident_date": "2026-05-10", "location": "grocery store; treated at St. Mary's Hospital"}),
        "created_at": "2026-05-14T03:59:21",
        "updated_at": "2026-05-14T14:38:50",
        "follow_up_count": 0,
    },
    {
        "id": "c0000000-0000-0000-0000-000000000005",
        "status": "ROUTING",
        "client_name": "David Okonkwo",
        "client_email": "d.okonkwo@example.com",
        "client_phone": "+15551234005",
        "case_type": "immigration",
        "urgency": "high",
        "jurisdiction": "CA",
        "complexity": "high",
        "intake_source": "web_form",
        "raw_intake_text": "H-1B visa holder, employer just revoked sponsorship without notice. I have 60 days to find a new sponsor or leave the country. My spouse and two children are on dependent visas. We've lived here for 4 years.",
        "key_entities_json": json.dumps({"adverse_parties": ["former employer (unnamed)"], "incident_date": "2026-05-18", "location": "San Francisco, CA"}),
        "created_at": "2026-05-18T16:45:00",
        "updated_at": "2026-05-19T09:20:00",
        "follow_up_count": 0,
    },
    {
        "id": "c0000000-0000-0000-0000-000000000006",
        "status": "CLASSIFYING",
        "client_name": "Patricia Nguyen",
        "client_email": "p.nguyen@example.com",
        "client_phone": "+15551234006",
        "case_type": None,
        "urgency": None,
        "jurisdiction": None,
        "complexity": None,
        "intake_source": "email",
        "raw_intake_text": "My landlord has refused to return my $3,200 security deposit after I moved out. The apartment was left in perfect condition and I have photos from move-in and move-out. Landlord claims there is damage but won't provide an itemized list. Lease ended April 30.",
        "key_entities_json": "{}",
        "created_at": "2026-05-21T10:00:00",
        "updated_at": "2026-05-21T10:00:30",
        "follow_up_count": 0,
    },
    {
        "id": "c0000000-0000-0000-0000-000000000007",
        "status": "NEW",
        "client_name": "Thomas Bell",
        "client_email": "t.bell@example.com",
        "client_phone": "+15551234007",
        "case_type": None,
        "urgency": None,
        "jurisdiction": None,
        "complexity": None,
        "intake_source": "web_form",
        "raw_intake_text": "I need help with my mother's estate. She passed away last month and left a will, but my brother is contesting it. The estate includes a house in Napa Valley and several investment accounts.",
        "key_entities_json": "{}",
        "created_at": "2026-05-22T07:30:00",
        "updated_at": "2026-05-22T07:30:00",
        "follow_up_count": 0,
    },
    {
        "id": "c0000000-0000-0000-0000-000000000008",
        "status": "REJECTED",
        "client_name": "Gary Feldman",
        "client_email": "g.feldman@example.com",
        "client_phone": "+15551234008",
        "case_type": "criminal_defense",
        "urgency": "high",
        "jurisdiction": "NV",
        "complexity": "high",
        "intake_source": "phone",
        "raw_intake_text": "Facing felony charges in Las Vegas. Need representation for arraignment next week.",
        "key_entities_json": json.dumps({"adverse_parties": ["State of Nevada"], "location": "Las Vegas, NV"}),
        "created_at": "2026-05-10T14:00:00",
        "updated_at": "2026-05-10T14:15:00",
        "follow_up_count": 0,
    },
    {
        "id": "c0000000-0000-0000-0000-000000000009",
        "status": "SCHEDULING",
        "client_name": "Aisha Patel",
        "client_email": "aisha.p@example.com",
        "client_phone": "+15551234009",
        "case_type": "family_law",
        "urgency": "high",
        "jurisdiction": "CA",
        "complexity": "high",
        "assigned_attorney_id": ATTORNEY_RIVERA,
        "consult_datetime": "2026-05-23T11:00:00",
        "intake_source": "referral",
        "raw_intake_text": "Filing for divorce after 12 years of marriage. Two minor children ages 8 and 5. Spouse is self-employed and I suspect is hiding income. Need to discuss custody arrangement and asset division including our home in Palo Alto.",
        "key_entities_json": json.dumps({"adverse_parties": ["spouse (unnamed)"], "location": "Palo Alto, CA"}),
        "created_at": "2026-05-17T09:00:00",
        "updated_at": "2026-05-19T16:30:00",
        "follow_up_count": 0,
    },
    {
        "id": "c0000000-0000-0000-0000-000000000010",
        "status": "AWAITING_DOCS",
        "client_name": "James Whitfield",
        "client_email": "j.whitfield@example.com",
        "client_phone": "+15551234010",
        "case_type": "real_estate",
        "urgency": "standard",
        "jurisdiction": "CA",
        "complexity": "moderate",
        "assigned_attorney_id": ATTORNEY_OKAFOR,
        "consult_datetime": "2026-05-19T15:00:00",
        "intake_source": "web_form",
        "raw_intake_text": "Purchased a home in Sacramento 6 months ago. Recently discovered the seller did not disclose known foundation issues and a history of flooding in the basement. Inspector missed it too. Repair estimates are $85,000.",
        "key_entities_json": json.dumps({"adverse_parties": ["seller (unnamed)", "home inspector"], "incident_date": "2025-11-15", "location": "Sacramento, CA"}),
        "created_at": "2026-05-13T13:00:00",
        "updated_at": "2026-05-20T10:00:00",
        "follow_up_count": 2,
    },
]

_CASE_COLS = (
    "id", "status", "client_name", "client_email", "client_phone",
    "case_type", "urgency", "jurisdiction", "complexity",
    "assigned_attorney_id", "consult_datetime", "intake_source",
    "raw_intake_text", "key_entities_json", "created_at", "updated_at",
    "follow_up_count",
)

DEMO_AUDIT_LOG = [
    # Maria Santos — full lifecycle
    {"id": "al000001", "case_id": "c0000000-0000-0000-0000-000000000001", "timestamp": "2026-05-09T08:15:30", "agent_observation": "status=NEW, raw intake present", "agent_reasoning": "Classified: personal_injury | high | CA | high", "action_taken": "status=CLASSIFYING", "action_result": "advance to CLASSIFYING"},
    {"id": "al000002", "case_id": "c0000000-0000-0000-0000-000000000001", "timestamp": "2026-05-09T08:15:45", "agent_observation": "conflict check", "agent_reasoning": "No conflicts found with ABC Trucking LLC", "action_taken": "status=CONFLICT_CHECK", "action_result": "CLEAR"},
    {"id": "al000003", "case_id": "c0000000-0000-0000-0000-000000000001", "timestamp": "2026-05-09T08:16:00", "agent_observation": "routing", "agent_reasoning": "Matched to Sarah Chen — personal_injury, CA bar, has capacity", "action_taken": "status=ROUTING", "action_result": "assigned to Sarah Chen"},
    {"id": "al000004", "case_id": "c0000000-0000-0000-0000-000000000001", "timestamp": "2026-05-09T08:16:30", "agent_observation": "routing complete, attorney assigned", "agent_reasoning": "Scheduled consultation for May 16 at 10:00 AM. SMS sent to +15551234001.", "action_taken": "status=SCHEDULING", "action_result": "advance to SCHEDULING"},
    {"id": "al000005", "case_id": "c0000000-0000-0000-0000-000000000001", "timestamp": "2026-05-16T11:00:00", "agent_observation": "client confirmed consultation attendance", "agent_reasoning": "All required documents received. Advancing to intake complete.", "action_taken": "status=INTAKE_COMPLETE", "action_result": "advance to INTAKE_COMPLETE"},

    # Robert Kim — awaiting docs
    {"id": "al000010", "case_id": "c0000000-0000-0000-0000-000000000002", "timestamp": "2026-05-12T11:30:30", "agent_observation": "status=NEW, raw intake present", "agent_reasoning": "Classified: employment | standard | CA | moderate", "action_taken": "status=CLASSIFYING", "action_result": "advance to CLASSIFYING"},
    {"id": "al000011", "case_id": "c0000000-0000-0000-0000-000000000002", "timestamp": "2026-05-12T11:30:45", "agent_observation": "conflict check", "agent_reasoning": "No conflicts found with TechCorp Inc.", "action_taken": "status=CONFLICT_CHECK", "action_result": "CLEAR"},
    {"id": "al000012", "case_id": "c0000000-0000-0000-0000-000000000002", "timestamp": "2026-05-12T11:31:00", "agent_observation": "routing", "agent_reasoning": "Matched to Priya Patel — employment law, CA bar, has capacity", "action_taken": "status=ROUTING", "action_result": "assigned to Priya Patel"},
    {"id": "al000013", "case_id": "c0000000-0000-0000-0000-000000000002", "timestamp": "2026-05-12T11:31:30", "agent_observation": "routing complete, attorney assigned", "agent_reasoning": "Scheduled consultation for May 20 at 2:00 PM. SMS sent to +15551234002.", "action_taken": "status=SCHEDULING", "action_result": "advance to SCHEDULING"},
    {"id": "al000014", "case_id": "c0000000-0000-0000-0000-000000000002", "timestamp": "2026-05-18T09:00:00", "agent_observation": "client confirmed, awaiting employment records", "agent_reasoning": "Client needs to provide termination letter, internal complaint emails, and last 3 pay stubs", "action_taken": "status=AWAITING_DOCS", "action_result": "advance to AWAITING_DOCS"},

    # Alex Johnson — scheduling
    {"id": "al000020", "case_id": "c0000000-0000-0000-0000-000000000003", "timestamp": "2026-05-14T02:48:55", "agent_observation": "status=NEW, raw intake present", "agent_reasoning": "Classified: personal_injury | standard | CA | moderate", "action_taken": "status=CLASSIFYING", "action_result": "advance to CLASSIFYING"},
    {"id": "al000021", "case_id": "c0000000-0000-0000-0000-000000000003", "timestamp": "2026-05-14T02:48:55", "agent_observation": "conflict check", "agent_reasoning": "No conflicts found", "action_taken": "status=CONFLICT_CHECK", "action_result": "CLEAR"},
    {"id": "al000022", "case_id": "c0000000-0000-0000-0000-000000000003", "timestamp": "2026-05-14T02:48:56", "agent_observation": "routing", "agent_reasoning": "Matched to Sarah Chen — personal_injury, CA bar", "action_taken": "status=ROUTING", "action_result": "assigned to Sarah Chen"},
    {"id": "al000023", "case_id": "c0000000-0000-0000-0000-000000000003", "timestamp": "2026-05-14T02:48:56", "agent_observation": "routing complete, attorney assigned", "agent_reasoning": "Scheduled with Sarah Chen. SMS sent to +15550001234.", "action_taken": "status=SCHEDULING", "action_result": "advance to SCHEDULING"},

    # Jane Martinez — conflict flagged
    {"id": "al000030", "case_id": "c0000000-0000-0000-0000-000000000004", "timestamp": "2026-05-14T03:59:31", "agent_observation": "status=NEW, raw intake present", "agent_reasoning": "Classified: personal_injury | standard | CA | moderate", "action_taken": "status=CLASSIFYING", "action_result": "advance to CLASSIFYING"},
    {"id": "al000031", "case_id": "c0000000-0000-0000-0000-000000000004", "timestamp": "2026-05-14T03:59:40", "agent_observation": "conflict check", "agent_reasoning": "Conflict detected — flagging for human review. Jane Martinez ↔ Janet Martinez (similarity 91%) — Same surname, similar first name; new case involves the same grocery store chain that is an existing client in case C0000001", "action_taken": "status=CONFLICT_FLAGGED", "action_result": "CONFLICT_FLAGGED"},
    {"id": "al000032", "case_id": "c0000000-0000-0000-0000-000000000004", "timestamp": "2026-05-14T03:59:41", "agent_observation": "conflict flagged", "agent_reasoning": "High-priority task created for managing partner — client not contacted", "action_taken": "status=CONFLICT_FLAGGED", "action_result": "CONFLICT_FLAGGED"},

    # David Okonkwo — routing
    {"id": "al000040", "case_id": "c0000000-0000-0000-0000-000000000005", "timestamp": "2026-05-18T16:45:30", "agent_observation": "status=NEW, raw intake present", "agent_reasoning": "Classified: immigration | high | CA | high", "action_taken": "status=CLASSIFYING", "action_result": "advance to CLASSIFYING"},
    {"id": "al000041", "case_id": "c0000000-0000-0000-0000-000000000005", "timestamp": "2026-05-18T16:45:45", "agent_observation": "conflict check", "agent_reasoning": "No conflicts found", "action_taken": "status=CONFLICT_CHECK", "action_result": "CLEAR"},
    {"id": "al000042", "case_id": "c0000000-0000-0000-0000-000000000005", "timestamp": "2026-05-19T09:20:00", "agent_observation": "routing", "agent_reasoning": "Matched to Priya Patel — immigration, CA/WA/OR bar, has capacity", "action_taken": "status=ROUTING", "action_result": "assigned to Priya Patel"},

    # Patricia Nguyen — classifying
    {"id": "al000050", "case_id": "c0000000-0000-0000-0000-000000000006", "timestamp": "2026-05-21T10:00:30", "agent_observation": "status=NEW, raw intake present", "agent_reasoning": "Running classification on intake text", "action_taken": "status=CLASSIFYING", "action_result": "advance to CLASSIFYING"},

    # Gary Feldman — rejected (out of jurisdiction)
    {"id": "al000060", "case_id": "c0000000-0000-0000-0000-000000000008", "timestamp": "2026-05-10T14:05:00", "agent_observation": "status=NEW, raw intake present", "agent_reasoning": "Classified: criminal_defense | high | NV | high", "action_taken": "status=CLASSIFYING", "action_result": "advance to CLASSIFYING"},
    {"id": "al000061", "case_id": "c0000000-0000-0000-0000-000000000008", "timestamp": "2026-05-10T14:10:00", "agent_observation": "conflict check", "agent_reasoning": "No conflicts found", "action_taken": "status=CONFLICT_CHECK", "action_result": "CLEAR"},
    {"id": "al000062", "case_id": "c0000000-0000-0000-0000-000000000008", "timestamp": "2026-05-10T14:15:00", "agent_observation": "routing", "agent_reasoning": "No attorney admitted in NV for criminal defense. Case outside firm jurisdiction. Declining with referral.", "action_taken": "status=REJECTED", "action_result": "REJECTED — outside jurisdiction"},

    # Aisha Patel — scheduling
    {"id": "al000070", "case_id": "c0000000-0000-0000-0000-000000000009", "timestamp": "2026-05-17T09:00:30", "agent_observation": "status=NEW, raw intake present", "agent_reasoning": "Classified: family_law | high | CA | high", "action_taken": "status=CLASSIFYING", "action_result": "advance to CLASSIFYING"},
    {"id": "al000071", "case_id": "c0000000-0000-0000-0000-000000000009", "timestamp": "2026-05-17T09:00:45", "agent_observation": "conflict check", "agent_reasoning": "No conflicts found", "action_taken": "status=CONFLICT_CHECK", "action_result": "CLEAR"},
    {"id": "al000072", "case_id": "c0000000-0000-0000-0000-000000000009", "timestamp": "2026-05-17T09:01:00", "agent_observation": "routing", "agent_reasoning": "Matched to Marcus Rivera — family_law, CA/TX bar, has capacity", "action_taken": "status=ROUTING", "action_result": "assigned to Marcus Rivera"},
    {"id": "al000073", "case_id": "c0000000-0000-0000-0000-000000000009", "timestamp": "2026-05-19T16:30:00", "agent_observation": "routing complete, attorney assigned", "agent_reasoning": "Scheduled consultation for May 23 at 11:00 AM. SMS sent to +15551234009.", "action_taken": "status=SCHEDULING", "action_result": "advance to SCHEDULING"},

    # James Whitfield — awaiting docs (with follow-ups)
    {"id": "al000080", "case_id": "c0000000-0000-0000-0000-000000000010", "timestamp": "2026-05-13T13:00:30", "agent_observation": "status=NEW, raw intake present", "agent_reasoning": "Classified: real_estate | standard | CA | moderate", "action_taken": "status=CLASSIFYING", "action_result": "advance to CLASSIFYING"},
    {"id": "al000081", "case_id": "c0000000-0000-0000-0000-000000000010", "timestamp": "2026-05-13T13:00:45", "agent_observation": "conflict check", "agent_reasoning": "No conflicts found", "action_taken": "status=CONFLICT_CHECK", "action_result": "CLEAR"},
    {"id": "al000082", "case_id": "c0000000-0000-0000-0000-000000000010", "timestamp": "2026-05-13T13:01:00", "agent_observation": "routing", "agent_reasoning": "Matched to Linda Okafor — real_estate, CA/NV bar, has capacity", "action_taken": "status=ROUTING", "action_result": "assigned to Linda Okafor"},
    {"id": "al000083", "case_id": "c0000000-0000-0000-0000-000000000010", "timestamp": "2026-05-13T13:01:30", "agent_observation": "routing complete, attorney assigned", "agent_reasoning": "Scheduled consultation for May 19 at 3:00 PM. SMS sent to +15551234010.", "action_taken": "status=SCHEDULING", "action_result": "advance to SCHEDULING"},
    {"id": "al000084", "case_id": "c0000000-0000-0000-0000-000000000010", "timestamp": "2026-05-19T16:00:00", "agent_observation": "client confirmed, awaiting documents", "agent_reasoning": "Need purchase agreement, inspection report, repair estimates, and disclosure statement", "action_taken": "status=AWAITING_DOCS", "action_result": "advance to AWAITING_DOCS"},
    {"id": "al000085", "case_id": "c0000000-0000-0000-0000-000000000010", "timestamp": "2026-05-20T10:00:00", "agent_observation": "follow-up sent", "agent_reasoning": "SMS reminder sent for outstanding documents. Follow-up #2.", "action_taken": "follow_up", "action_result": "SMS sent to +15551234010"},
]

DEMO_MISSING_DOCS = [
    # Robert Kim
    {"id": "md000001", "case_id": "c0000000-0000-0000-0000-000000000002", "document_type": "Termination letter", "requested_at": "2026-05-18T09:00:00", "received_at": None, "follow_up_count": 0},
    {"id": "md000002", "case_id": "c0000000-0000-0000-0000-000000000002", "document_type": "Internal complaint emails", "requested_at": "2026-05-18T09:00:00", "received_at": None, "follow_up_count": 0},
    {"id": "md000003", "case_id": "c0000000-0000-0000-0000-000000000002", "document_type": "Last 3 pay stubs", "requested_at": "2026-05-18T09:00:00", "received_at": None, "follow_up_count": 0},
    # James Whitfield
    {"id": "md000010", "case_id": "c0000000-0000-0000-0000-000000000010", "document_type": "Purchase agreement", "requested_at": "2026-05-19T16:00:00", "received_at": "2026-05-20T08:00:00", "follow_up_count": 0},
    {"id": "md000011", "case_id": "c0000000-0000-0000-0000-000000000010", "document_type": "Home inspection report", "requested_at": "2026-05-19T16:00:00", "received_at": None, "follow_up_count": 2},
    {"id": "md000012", "case_id": "c0000000-0000-0000-0000-000000000010", "document_type": "Foundation repair estimates", "requested_at": "2026-05-19T16:00:00", "received_at": None, "follow_up_count": 1},
    {"id": "md000013", "case_id": "c0000000-0000-0000-0000-000000000010", "document_type": "Seller disclosure statement", "requested_at": "2026-05-19T16:00:00", "received_at": "2026-05-20T09:30:00", "follow_up_count": 0},
]

DEMO_ENGAGEMENT_LETTER = {
    "id": "el000001",
    "case_id": "c0000000-0000-0000-0000-000000000001",
    "letter_text": (
        "ENGAGEMENT LETTER\n\n"
        "Dear Maria Santos,\n\n"
        "Thank you for choosing our firm to represent you in your personal injury matter "
        "arising from the motor vehicle accident on May 8, 2026.\n\n"
        "Attorney Sarah Chen will serve as your primary counsel. Our firm will represent "
        "you on a contingency fee basis of 33.3% of any recovery obtained. You will not "
        "owe attorney fees unless we obtain a recovery on your behalf.\n\n"
        "Please do not hesitate to contact us with any questions.\n\n"
        "Sincerely,\nSarah Chen, Esq."
    ),
}


async def seed_attorneys(db: aiosqlite.Connection) -> None:
    """Insert sample attorneys. Safe to call repeatedly (INSERT OR IGNORE)."""
    for attorney in ATTORNEYS:
        await db.execute(
            """
            INSERT OR IGNORE INTO attorneys
                (id, name, email, practice_areas, bar_admissions,
                 max_active_cases, current_active_cases)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attorney["id"],
                attorney["name"],
                attorney["email"],
                attorney["practice_areas"],
                attorney["bar_admissions"],
                attorney["max_active_cases"],
                attorney["current_active_cases"],
            ),
        )
    await db.commit()
    logger.info("Seeded %d attorneys.", len(ATTORNEYS))


async def seed_demo_cases(db: aiosqlite.Connection) -> None:
    """Insert demo cases, audit log, missing docs, and engagement letter."""
    placeholders = ", ".join("?" for _ in _CASE_COLS)
    col_names = ", ".join(_CASE_COLS)
    for case in DEMO_CASES:
        vals = tuple(case.get(c) for c in _CASE_COLS)
        await db.execute(
            f"INSERT OR IGNORE INTO cases ({col_names}) VALUES ({placeholders})",
            vals,
        )

    for entry in DEMO_AUDIT_LOG:
        await db.execute(
            """INSERT OR IGNORE INTO audit_log
               (id, case_id, timestamp, agent_observation, agent_reasoning,
                action_taken, action_result)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (entry["id"], entry["case_id"], entry["timestamp"],
             entry["agent_observation"], entry["agent_reasoning"],
             entry["action_taken"], entry["action_result"]),
        )

    for doc in DEMO_MISSING_DOCS:
        await db.execute(
            """INSERT OR IGNORE INTO missing_documents
               (id, case_id, document_type, requested_at, received_at, follow_up_count)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (doc["id"], doc["case_id"], doc["document_type"],
             doc["requested_at"], doc["received_at"], doc["follow_up_count"]),
        )

    el = DEMO_ENGAGEMENT_LETTER
    await db.execute(
        """INSERT OR IGNORE INTO engagement_letters (id, case_id, letter_text)
           VALUES (?, ?, ?)""",
        (el["id"], el["case_id"], el["letter_text"]),
    )

    await db.commit()
    logger.info("Seeded %d demo cases with audit log, docs, and engagement letter.", len(DEMO_CASES))


async def seed() -> None:
    """Standalone seed: init DB then insert attorneys and demo data."""
    from src.db.database import init_db

    await init_db()
    async with aiosqlite.connect(settings.database_url) as db:
        await seed_attorneys(db)
        await seed_demo_cases(db)
    print(f"Seeded {len(ATTORNEYS)} attorneys and {len(DEMO_CASES)} demo cases.")


if __name__ == "__main__":
    asyncio.run(seed())
