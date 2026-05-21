"""Asana task board integration via REST API.

Setup:
  1. Create a Personal Access Token at https://app.asana.com/0/developer-console
  2. Find your Workspace GID: GET https://app.asana.com/api/1.0/workspaces
  3. Create (or find) the "New Intakes" project, note its GID
  4. Set ASANA_ACCESS_TOKEN, ASANA_WORKSPACE_GID, ASANA_PROJECT_GID in .env

Falls back to console logging if not configured.
"""
import logging
from typing import Optional

import httpx

from src.config import settings
from src.utils.retry import retry_async

logger = logging.getLogger(__name__)

_BASE = "https://app.asana.com/api/1.0"
_PRIORITY_TAGS = {"high": "🔴 HIGH PRIORITY", "normal": "", "low": ""}


def _is_configured() -> bool:
    return bool(settings.asana_access_token and settings.asana_workspace_gid)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.asana_access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


async def create_task(
    title: str,
    description: str,
    assignee_email: str,
    priority: str = "normal",
    project_gid: Optional[str] = None,
) -> dict:
    """Create an Asana task. Returns dict with 'task_gid' key."""
    if not _is_configured():
        prefix = _PRIORITY_TAGS.get(priority, "")
        display = f"{prefix} {title}".strip()
        logger.warning("[ASANA STUB] %s\nAssignee: %s\n%s", display, assignee_email, description)
        return {"task_gid": "STUB", "title": title, "url": ""}

    project = project_gid or settings.asana_project_gid
    assignee_gid = await _resolve_user_gid(assignee_email)

    async def _do_create() -> dict:
        body: dict = {
            "data": {
                "name": title,
                "notes": description,
                "workspace": settings.asana_workspace_gid,
            }
        }
        if assignee_gid:
            body["data"]["assignee"] = assignee_gid
        if project:
            body["data"]["projects"] = [project]

        async with httpx.AsyncClient(timeout=10, headers=_headers()) as client:
            resp = await client.post(f"{_BASE}/tasks", json=body)
        resp.raise_for_status()
        task = resp.json()["data"]
        logger.info("Asana task created: gid=%s title=%s", task["gid"], title)
        return {
            "task_gid": task["gid"],
            "title": title,
            "url": f"https://app.asana.com/0/{project}/{task['gid']}",
        }

    try:
        return await retry_async(_do_create, label="asana.create_task")
    except Exception as exc:
        logger.error("Asana create_task failed after retries: %s", exc)
        return {"task_gid": None, "title": title, "url": "", "error": str(exc)}


async def update_task(task_gid: str, completed: bool = False, notes: Optional[str] = None) -> dict:
    """Update an existing Asana task's completion state or notes."""
    if not _is_configured() or task_gid == "STUB":
        logger.warning("[ASANA STUB] update_task gid=%s completed=%s", task_gid, completed)
        return {"task_gid": task_gid, "updated": True}

    body: dict = {"data": {"completed": completed}}
    if notes:
        body["data"]["notes"] = notes

    async with httpx.AsyncClient(timeout=10, headers=_headers()) as client:
        resp = await client.put(f"{_BASE}/tasks/{task_gid}", json=body)

    if resp.status_code != 200:
        logger.error("Asana update_task failed: %s %s", resp.status_code, resp.text)
        return {"task_gid": task_gid, "updated": False}

    return {"task_gid": task_gid, "updated": True}


async def _resolve_user_gid(email: str) -> Optional[str]:
    """Look up an Asana user GID by email within the workspace."""
    if not email or not _is_configured():
        return None
    try:
        async with httpx.AsyncClient(timeout=10, headers=_headers()) as client:
            resp = await client.get(
                f"{_BASE}/workspaces/{settings.asana_workspace_gid}/users",
                params={"opt_fields": "email,gid"},
            )
        if resp.status_code != 200:
            return None
        users = resp.json().get("data", [])
        for user in users:
            if user.get("email", "").lower() == email.lower():
                return user["gid"]
    except Exception as exc:
        logger.warning("Asana user lookup failed for %s: %s", email, exc)
    return None
