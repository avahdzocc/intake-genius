from src.db.queries import get_attorneys
from src.models.attorney import Attorney
from src.models.case import Case


def _score_attorney(attorney: Attorney, case: Case) -> int:
    score = 0

    if case.case_type and case.case_type in attorney.practice_areas:
        score += 40

    if case.jurisdiction:
        state = case.jurisdiction.split()[0][:2].upper()
        if state in [s.upper() for s in attorney.bar_admissions]:
            score += 30

    # Capacity: 20 points scaled by available capacity
    score += int(20 * (1 - attorney.capacity_ratio))

    # Complexity/seniority match (simple heuristic on caseload)
    if case.complexity == "complex" and attorney.current_active_cases < 10:
        score += 10
    elif case.complexity in ("simple", "moderate"):
        score += 10

    # TODO: Add Google Calendar availability check (Phase 2)

    return score


async def route_to_attorney(case: Case) -> Attorney | None:
    attorneys = await get_attorneys()
    if not attorneys:
        return None

    scored = [(attorney, _score_attorney(attorney, case)) for attorney in attorneys]
    scored.sort(key=lambda x: x[1], reverse=True)

    best_attorney, best_score = scored[0]
    if best_score < 50:
        return None

    return best_attorney
