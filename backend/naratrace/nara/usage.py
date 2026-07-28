from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from naratrace.core.config import get_settings
from naratrace.database.models import ApplicationSetting
from naratrace.database.session import session_scope

USAGE_SETTING_KEY = "nara_api_usage"
DEFAULT_MONTHLY_REQUEST_LIMIT = 10_000


@dataclass(frozen=True)
class NaraApiUsage:
    request_count: int
    request_limit: int
    percent_used: float
    period: str
    reset_at: datetime
    counted_locally: bool = True


def record_nara_api_request(api_key: str | None, now: datetime | None = None) -> None:
    if not api_key:
        return
    now = now or datetime.now(timezone.utc)
    try:
        with session_scope() as session:
            state = load_usage_state(session.get(ApplicationSetting, USAGE_SETTING_KEY))
            state = normalized_state(state, api_key, now)
            state["request_count"] = int(state.get("request_count", 0)) + 1
            setting = session.get(ApplicationSetting, USAGE_SETTING_KEY)
            if setting is None:
                setting = ApplicationSetting(key=USAGE_SETTING_KEY)
                session.add(setting)
            setting.value = json.dumps(state, separators=(",", ":"))
    except SQLAlchemyError:
        return


def get_nara_api_usage(api_key: str | None, now: datetime | None = None) -> NaraApiUsage:
    now = now or datetime.now(timezone.utc)
    request_limit = get_nara_monthly_request_limit()
    if not api_key:
        return build_usage_response(0, request_limit, current_period(now), next_reset_at(now))

    try:
        with session_scope() as session:
            state = load_usage_state(session.get(ApplicationSetting, USAGE_SETTING_KEY))
            state = normalized_state(state, api_key, now)
    except SQLAlchemyError:
        state = {"request_count": 0, "period": current_period(now)}
    return build_usage_response(int(state.get("request_count", 0)), request_limit, str(state["period"]), next_reset_at(now))


def normalized_state(state: dict, api_key: str, now: datetime) -> dict:
    period = current_period(now)
    fingerprint = key_fingerprint(api_key)
    if state.get("api_key_fingerprint") != fingerprint or state.get("period") != period:
        return {
            "api_key_fingerprint": fingerprint,
            "period": period,
            "request_count": 0,
        }
    state["request_count"] = max(0, int(state.get("request_count", 0)))
    return state


def load_usage_state(setting: ApplicationSetting | None) -> dict:
    if setting is None or not setting.value:
        return {}
    try:
        data = json.loads(setting.value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def build_usage_response(request_count: int, request_limit: int, period: str, reset_at: datetime) -> NaraApiUsage:
    percent_used = (request_count / request_limit * 100) if request_limit > 0 else 0.0
    return NaraApiUsage(
        request_count=request_count,
        request_limit=request_limit,
        percent_used=round(percent_used, 2),
        period=period,
        reset_at=reset_at,
    )


def get_nara_monthly_request_limit() -> int:
    return max(1, get_settings().nara_monthly_request_limit)


def current_period(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m")


def next_reset_at(now: datetime) -> datetime:
    utc_now = now.astimezone(timezone.utc)
    if utc_now.month == 12:
        return datetime(utc_now.year + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(utc_now.year, utc_now.month + 1, 1, tzinfo=timezone.utc)


def key_fingerprint(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()
