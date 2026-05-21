"""Seed sample attorney data for development and demo deployments."""
import asyncio
import json
import logging
import uuid

import aiosqlite

from src.config import settings

logger = logging.getLogger(__name__)

ATTORNEYS = [
    {
        "id": str(uuid.uuid4()),
        "name": "Sarah Chen",
        "email": "schen@firm.com",
        "practice_areas": json.dumps(["personal_injury", "medical_malpractice"]),
        "bar_admissions": json.dumps(["CA", "NY"]),
        "max_active_cases": 25,
        "current_active_cases": 18,
    },
    {
        "id": str(uuid.uuid4()),
        "name": "Marcus Rivera",
        "email": "mrivera@firm.com",
        "practice_areas": json.dumps(["family_law", "divorce", "child_custody"]),
        "bar_admissions": json.dumps(["CA", "TX"]),
        "max_active_cases": 20,
        "current_active_cases": 12,
    },
    {
        "id": str(uuid.uuid4()),
        "name": "Priya Patel",
        "email": "ppatel@firm.com",
        "practice_areas": json.dumps(["immigration", "employment"]),
        "bar_admissions": json.dumps(["CA", "WA", "OR"]),
        "max_active_cases": 30,
        "current_active_cases": 8,
    },
    {
        "id": str(uuid.uuid4()),
        "name": "James O'Brien",
        "email": "jobrien@firm.com",
        "practice_areas": json.dumps(["criminal_defense", "DUI"]),
        "bar_admissions": json.dumps(["CA"]),
        "max_active_cases": 15,
        "current_active_cases": 11,
    },
    {
        "id": str(uuid.uuid4()),
        "name": "Linda Okafor",
        "email": "lokafor@firm.com",
        "practice_areas": json.dumps(["real_estate", "estate_planning", "probate"]),
        "bar_admissions": json.dumps(["CA", "NV"]),
        "max_active_cases": 25,
        "current_active_cases": 5,
    },
]


async def seed_attorneys(db: aiosqlite.Connection) -> None:
    """Insert sample attorneys into an open connection. Safe to call repeatedly (INSERT OR IGNORE)."""
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


async def seed() -> None:
    """Standalone seed: init DB then insert attorneys."""
    from src.db.database import init_db

    await init_db()
    async with aiosqlite.connect(settings.database_url) as db:
        await seed_attorneys(db)
    print(f"Seeded {len(ATTORNEYS)} attorneys.")


if __name__ == "__main__":
    asyncio.run(seed())
