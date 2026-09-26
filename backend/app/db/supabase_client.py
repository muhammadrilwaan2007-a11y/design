"""
backend/app/db/supabase_client.py
Supabase async client singleton for SafeRoute AI.

Uses supabase-py v2 AsyncClient.
The client is created once per application lifetime and cached.

Design decisions:
  - Service role key is used (not anon key) so that RLS does not block
    backend writes to live_data_snapshots / incident_observations etc.
  - The client is intentionally NOT exposed outside this module.
    All database access goes through live_snapshot_service.py.
  - If SUPABASE_URL or SUPABASE_SERVICE_KEY are missing, the client
    returns None and callers must fall back to local file storage.
  - We never log the service key.
"""

from __future__ import annotations

import logging
from typing import Optional

from supabase import AClient, acreate_client

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

_client: Optional[AClient] = None
_client_initialized: bool = False


async def get_supabase() -> Optional[AClient]:
    """
    Return the shared Supabase AsyncClient instance.

    Returns None if SUPABASE_URL / SUPABASE_SERVICE_KEY are not configured,
    allowing callers to fall back to local file storage.

    The client is created on the first call and cached for all subsequent calls.
    """
    global _client, _client_initialized

    if _client_initialized:
        return _client  # May be None if config is missing

    settings = get_settings()

    if not settings.supabase_url or not settings.supabase_service_key:
        logger.warning(
            "SUPABASE_URL or SUPABASE_SERVICE_KEY not set. "
            "Live snapshot storage will fall back to local files. "
            "Set both in .env for production use."
        )
        _client_initialized = True
        _client = None
        return None

    try:
        _client = await acreate_client(
            settings.supabase_url,
            settings.supabase_service_key,
        )
        logger.info(
            "Supabase client initialized for project: %s",
            settings.supabase_url.split("//")[-1].split(".")[0],  # log project ref only
        )
    except Exception as exc:
        logger.error("Failed to initialize Supabase client: %s", exc, exc_info=True)
        _client = None

    _client_initialized = True
    return _client


def reset_client() -> None:
    """
    Reset the cached client. Useful for testing only.
    Not called in production.
    """
    global _client, _client_initialized
    _client = None
    _client_initialized = False
