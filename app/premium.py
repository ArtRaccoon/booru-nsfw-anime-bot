from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from aiogram import Bot
from aiogram.types import LabeledPrice


@dataclass(frozen=True)
class PremiumPlan:
    code: str
    title: str
    days: int
    stars: int


@dataclass
class PremiumState:
    user_id: int
    premium_until: datetime
    plan: str
    created_at: datetime


@dataclass
class PendingPremiumPlan:
    user_id: int
    plan: str
    created_at: datetime


PREMIUM_PLANS: dict[str, PremiumPlan] = {
    "day": PremiumPlan(code="day", title="1 день", days=1, stars=50),
    "week": PremiumPlan(code="week", title="7 дней", days=7, stars=250),
    "month": PremiumPlan(code="month", title="30 дней", days=30, stars=700),
}

premium_states: dict[int, PremiumState] = {}
pending_premium_plans: dict[str, PendingPremiumPlan] = {}


class PremiumInvoiceService(Protocol):
    async def create_invoice(
        self, bot: Bot, user_id: int, plan: PremiumPlan, payload: str
    ) -> None: ...


class TelegramStarsInvoiceService:
    async def create_invoice(self, bot: Bot, user_id: int, plan: PremiumPlan, payload: str) -> None:
        await bot.send_invoice(
            chat_id=user_id,
            title=f"Енот Ищейка Premium — {plan.title}",
            description="Доступ к взрослому режиму поиска Енота Ищейки.",
            payload=payload,
            currency="XTR",
            prices=[LabeledPrice(label=f"Premium {plan.title}", amount=plan.stars)],
            provider_token=None,
        )


def utc_now() -> datetime:
    return datetime.now(UTC)


def premium_payload(user_id: int, plan_code: str, created_at: datetime | None = None) -> str:
    timestamp = int((created_at or utc_now()).timestamp())
    return f"premium:{user_id}:{plan_code}:{timestamp}"


def store_pending_premium_plan(user_id: int, plan_code: str, payload: str) -> None:
    pending_premium_plans[payload] = PendingPremiumPlan(
        user_id=user_id,
        plan=plan_code,
        created_at=utc_now(),
    )


def activate_premium(user_id: int, plan_code: str, now: datetime | None = None) -> PremiumState:
    current_time = now or utc_now()
    plan = PREMIUM_PLANS[plan_code]
    state = PremiumState(
        user_id=user_id,
        premium_until=current_time + timedelta(days=plan.days),
        plan=plan_code,
        created_at=current_time,
    )
    premium_states[user_id] = state
    return state


def activate_pending_premium(payload: str, user_id: int | None = None) -> PremiumState | None:
    pending = pending_premium_plans.pop(payload, None)
    if pending is None:
        return None
    if user_id is not None and pending.user_id != user_id:
        return None
    return activate_premium(pending.user_id, pending.plan)


def is_premium_active(user_id: int) -> bool:
    state = premium_states.get(user_id)
    return state is not None and state.premium_until > utc_now()
