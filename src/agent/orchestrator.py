import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from src.config import settings
from src.db.queries import (
    load_case,
    update_case,
    log_audit,
    get_attorney_by_id,
    get_missing_docs,
    add_missing_docs,
    save_case_parties,
    update_calendar_event_id,
)
from src.models.case import Case, CaseStatus
from src.models.audit import AuditEntry
from src.agent.classifier import classify_intake
from src.agent.conflict_checker import check_conflicts
from src.agent.router import route_to_attorney
from src.agent.follow_up import generate_follow_up_message, should_follow_up, MAX_FOLLOW_UPS
from src.agent.doc_list import get_required_docs, friendly_doc_name
from src.agent.doc_generator import generate_engagement_letter
from src.db.queries import save_engagement_letter
from src.integrations.twilio_client import send_sms
from src.integrations.calendar_client import find_next_available_slot, create_event
from src.integrations.task_board import create_task

logger = logging.getLogger(__name__)

TERMINAL_STATES = {CaseStatus.INTAKE_COMPLETE, CaseStatus.REJECTED, CaseStatus.BLOCKED}


@dataclass
class Observation:
    has_contact_info: bool
    has_case_description: bool
    assigned_attorney: str | None
    consult_scheduled: bool
    days_since_last_contact: float


def _observe(case: Case) -> Observation:
    return Observation(
        has_contact_info=bool(case.client_phone or case.client_email),
        has_case_description=bool(case.raw_intake_text),
        assigned_attorney=case.assigned_attorney_id,
        consult_scheduled=case.consult_datetime is not None,
        days_since_last_contact=case.days_since_last_contact(),
    )


def _first_name(full_name: str | None) -> str:
    if not full_name:
        return "there"
    return full_name.split()[0]


class IntakeAgent:
    def __init__(self, case: Case) -> None:
        self.case = case

    async def run(self) -> Case:
        while self.case.status not in TERMINAL_STATES:
            obs = _observe(self.case)
            prev_status = self.case.status

            if self.case.status == CaseStatus.NEW:
                await self._step_classify(obs)

            elif self.case.status == CaseStatus.CLASSIFYING:
                await self._step_conflict_check(obs)

            elif self.case.status == CaseStatus.CONFLICT_CHECK:
                await self._step_route(obs)

            elif self.case.status == CaseStatus.ROUTING:
                await self._step_schedule(obs)
                break  # Stays in SCHEDULING, waiting for client to confirm via SMS

            elif self.case.status == CaseStatus.CONFLICT_FLAGGED:
                await self._step_notify_conflict(obs)
                break  # Waiting for human review

            elif self.case.status in (CaseStatus.SCHEDULING, CaseStatus.AWAITING_DOCS):
                break  # External input required

            else:
                break

            await update_case(self.case)

            if self.case.status == prev_status:
                break

        return self.case

    # ── State transition steps ────────────────────────────────────────────────

    async def _step_classify(self, obs: Observation) -> None:
        self.case.status = CaseStatus.CLASSIFYING
        parties_to_save = []
        try:
            result = await classify_intake(self.case.raw_intake_text or "")
            self.case.case_type = result.case_type
            self.case.urgency = result.urgency.value
            self.case.jurisdiction = result.jurisdiction
            self.case.complexity = result.complexity.value
            self.case.key_entities = result.key_entities

            # Persist client + adverse parties for future conflict checks
            if self.case.client_name:
                parties_to_save.append({"name": self.case.client_name, "role": "client"})
            for adverse in result.key_entities.get("adverse_parties", []):
                if adverse:
                    parties_to_save.append({"name": adverse, "role": "adverse"})
            if parties_to_save:
                await save_case_parties(self.case.id, parties_to_save)

            reasoning = (
                f"Classified: {result.case_type} | {result.urgency.value} | "
                f"{result.jurisdiction} | {result.complexity.value}"
            )
        except Exception as exc:
            reasoning = f"Classification failed: {exc}"
            logger.exception("Classification error for case %s", self.case.id)

        await self._audit(obs, "status=NEW, raw intake present", reasoning, "advance to CLASSIFYING")

    async def _step_conflict_check(self, obs: Observation) -> None:
        self.case.status = CaseStatus.CONFLICT_CHECK
        conflict_result = await check_conflicts(self.case)

        if conflict_result["status"] == "CONFLICT_FLAGGED":
            self.case.status = CaseStatus.CONFLICT_FLAGGED
            # Build an explanation from the matched parties
            details = []
            for m in conflict_result.get("matches", []):
                detail = f"{m.get('new_party', '?')} ↔ {m.get('existing_party', '?')} (similarity {m.get('similarity_score', 0):.0%})"
                eval_info = m.get("evaluation", {})
                if eval_info.get("explanation"):
                    detail += f" — {eval_info['explanation']}"
                details.append(detail)
            reasoning = "Conflict detected — flagging for human review. " + "; ".join(details) if details else "Conflict detected — flagging for human review"
        else:
            reasoning = "No conflicts found"

        await self._audit(obs, "conflict check", reasoning, conflict_result["status"])

    async def _step_route(self, obs: Observation) -> None:
        self.case.status = CaseStatus.ROUTING
        attorney = await route_to_attorney(self.case)

        if attorney:
            self.case.assigned_attorney_id = attorney.id
            reasoning = f"Assigned to {attorney.name}"
        else:
            reasoning = "No attorney matched — manual assignment needed"

        await self._audit(obs, "routing", reasoning, "assigned" if attorney else "unassigned")

    async def _step_schedule(self, obs: Observation) -> None:
        """Find a slot, create a calendar event, SMS the client, create an Asana task."""
        self.case.status = CaseStatus.SCHEDULING

        attorney = None
        if self.case.assigned_attorney_id:
            attorney = await get_attorney_by_id(self.case.assigned_attorney_id)

        attorney_name = attorney.name if attorney else "an attorney"
        attorney_email = attorney.email if attorney else ""

        # 1. Find next available slot
        slot_dt = await find_next_available_slot(attorney_email or "")

        # 2. Create calendar event
        event = await create_event(
            attorney_email=attorney_email or "",
            client_name=self.case.client_name or "Client",
            dt=slot_dt,
            case_id=self.case.id,
        )
        self.case.consult_datetime = slot_dt.isoformat()
        if event.get("event_id") and event["event_id"] != "STUB":
            await update_calendar_event_id(self.case.id, event["event_id"])

        # 3. Format the proposed time for SMS
        slot_str = slot_dt.strftime("%A, %B %-d at %-I:%M %p")

        # 4. SMS the client with a confirmation request
        if self.case.client_phone:
            sms_body = (
                f"Hi {_first_name(self.case.client_name)}, thanks for contacting "
                f"{settings.firm_name}. We'd like to schedule a consultation with "
                f"{attorney_name} on {slot_str}. Reply YES to confirm or call "
                f"{settings.intake_email} to reschedule."
            )
            await send_sms(self.case.client_phone, sms_body)
            self.case.last_client_contact_at = datetime.now(timezone.utc).isoformat()

        # 5. Create Asana task for the attorney
        task_desc = (
            f"New intake — {self.case.case_type or 'unknown type'}\n"
            f"Client: {self.case.client_name}\n"
            f"Phone: {self.case.client_phone}\n"
            f"Email: {self.case.client_email}\n"
            f"Urgency: {self.case.urgency}\n"
            f"Proposed consult: {slot_str}\n"
            f"Jurisdiction: {self.case.jurisdiction}\n\n"
            f"Intake summary:\n{self.case.raw_intake_text}"
        )
        await create_task(
            title=f"New intake: {self.case.client_name or 'Unknown'} — {self.case.case_type or 'TBD'}",
            description=task_desc,
            assignee_email=attorney_email or "",
            priority="high" if self.case.urgency == "emergency" else "normal",
        )

        reasoning = (
            f"Scheduled with {attorney_name} on {slot_str}. "
            f"SMS sent to {self.case.client_phone}. Calendar event: {event.get('event_id')}."
        )
        await self._audit(obs, "routing complete, attorney assigned", reasoning, "advance to SCHEDULING")

    async def _step_notify_conflict(self, obs: Observation) -> None:
        """Create a high-priority Asana task for the managing partner; do NOT contact the client."""
        matches = []  # Would come from the conflict result stored on the case in a richer impl
        task_desc = (
            f"POTENTIAL CONFLICT — Review Required\n\n"
            f"New intake: {self.case.client_name}\n"
            f"Case type: {self.case.case_type}\n"
            f"Phone: {self.case.client_phone}\n\n"
            f"Intake summary:\n{self.case.raw_intake_text}\n\n"
            f"Please review and clear or reject this intake."
        )
        await create_task(
            title=f"⚠️ Conflict review: {self.case.client_name or 'Unknown'} intake",
            description=task_desc,
            assignee_email=settings.managing_partner_email or "",
            priority="high",
        )
        await self._audit(
            obs,
            "conflict flagged",
            "High-priority Asana task created for managing partner — client not contacted",
            "CONFLICT_FLAGGED",
        )

    # ── External event handlers ───────────────────────────────────────────────

    async def handle_client_confirmed(self) -> Case:
        """Client replied YES — advance SCHEDULING → AWAITING_DOCS, request documents."""
        if self.case.status != CaseStatus.SCHEDULING:
            return self.case

        self.case.status = CaseStatus.AWAITING_DOCS

        # Seed missing_documents table
        required = get_required_docs(self.case.case_type or "other")
        if required:
            await add_missing_docs(self.case.id, required)

        # SMS the client with the doc list
        if self.case.client_phone and required:
            doc_lines = "\n".join(f"• {friendly_doc_name(d)}" for d in required)
            slot_str = ""
            if self.case.consult_datetime:
                try:
                    dt = datetime.fromisoformat(self.case.consult_datetime)
                    slot_str = dt.strftime("%A, %B %-d")
                except Exception:
                    pass
            sms_body = (
                f"Your consultation is confirmed! "
                f"{'For ' + slot_str + ', p' if slot_str else 'P'}"
                f"lease send us the following before we meet:\n{doc_lines}\n"
                f"Reply or email to {settings.intake_email}. Reply STOP to unsubscribe."
            )
            await send_sms(self.case.client_phone, sms_body)
            self.case.last_client_contact_at = datetime.now(timezone.utc).isoformat()

        # Generate and store engagement letter in background
        attorney_name = ""
        if self.case.assigned_attorney_id:
            attorney = await get_attorney_by_id(self.case.assigned_attorney_id)
            if attorney:
                attorney_name = attorney.name or ""
        doc_names = [friendly_doc_name(d) for d in required] if required else []
        try:
            letter = await generate_engagement_letter(
                self.case, attorney_name=attorney_name, required_docs=doc_names
            )
            await save_engagement_letter(self.case.id, letter)
        except Exception as exc:
            logger.warning("Engagement letter generation skipped: %s", exc)

        obs = _observe(self.case)
        await self._audit(obs, "client confirmed consultation", "advancing to AWAITING_DOCS, doc request SMS sent", "ok")
        await update_case(self.case)
        return self.case

    async def handle_follow_up(self) -> Case:
        """Trigger a follow-up SMS for stale cases."""
        if not await should_follow_up(self.case):
            # Max follow-ups reached — block and create manual task
            self.case.status = CaseStatus.BLOCKED
            await create_task(
                title=f"Manual follow-up needed: {self.case.client_name}",
                description=(
                    f"Case {self.case.id} has had {self.case.follow_up_count} automated "
                    f"follow-up attempts with no response. A manual phone call is needed.\n"
                    f"Phone: {self.case.client_phone}"
                ),
                assignee_email=settings.managing_partner_email or "",
                priority="normal",
            )
            obs = _observe(self.case)
            await self._audit(obs, "max follow-ups reached", "case blocked, manual task created", "BLOCKED")
            await update_case(self.case)
            return self.case

        missing = await get_missing_docs(self.case.id)
        message = await generate_follow_up_message(self.case, missing)

        if self.case.client_phone and message:
            await send_sms(self.case.client_phone, message)

        self.case.follow_up_count += 1
        self.case.last_client_contact_at = datetime.now(timezone.utc).isoformat()

        obs = _observe(self.case)
        await self._audit(
            obs,
            f"stale case, {self.case.follow_up_count - 1} prior follow-ups",
            f"sent follow-up #{self.case.follow_up_count}",
            "sms_sent",
        )
        await update_case(self.case)
        return self.case

    async def handle_conflict_resolved(self, cleared: bool) -> Case:
        """Managing partner cleared (or rejected) the conflict."""
        if self.case.status != CaseStatus.CONFLICT_FLAGGED:
            return self.case

        if cleared:
            self.case.status = CaseStatus.ROUTING
            await update_case(self.case)
            return await run_intake_agent(self.case.id)  # resume the loop
        else:
            self.case.status = CaseStatus.REJECTED
            # Send polite declination to the client
            if self.case.client_phone:
                sms_body = (
                    f"Hi {_first_name(self.case.client_name)}, thank you for contacting "
                    f"{settings.firm_name}. Unfortunately, we are unable to represent you "
                    f"in this matter due to a conflict of interest. We recommend contacting "
                    f"your state bar's referral service. We wish you the best."
                )
                await send_sms(self.case.client_phone, sms_body)

            obs = _observe(self.case)
            await self._audit(obs, "conflict rejected by managing partner", "client notified, case REJECTED", "REJECTED")
            await update_case(self.case)
            return self.case

    # ── Utilities ─────────────────────────────────────────────────────────────

    async def _audit(self, obs: Observation, observation: str, reasoning: str, result: str) -> None:
        entry = AuditEntry(
            case_id=self.case.id,
            agent_observation=observation,
            agent_reasoning=reasoning,
            action_taken=f"status={self.case.status.value}",
            action_result=result,
        )
        await log_audit(entry)


async def run_intake_agent(case_id: str) -> Case | None:
    case = await load_case(case_id)
    if case is None:
        return None
    agent = IntakeAgent(case)
    return await agent.run()


async def run_follow_up(case_id: str) -> Case | None:
    case = await load_case(case_id)
    if case is None:
        return None
    agent = IntakeAgent(case)
    return await agent.handle_follow_up()


async def run_conflict_resolution(case_id: str, cleared: bool) -> Case | None:
    case = await load_case(case_id)
    if case is None:
        return None
    agent = IntakeAgent(case)
    return await agent.handle_conflict_resolved(cleared)
