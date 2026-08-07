"""Read access to time-sensitive reference data."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from opportunity_finder.db.models import ExchangeRate, FeeRule, ShippingRate


class ReferenceDataRepository:
    """Look up the reference-data record applicable at a point in time."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_latest_exchange_rate(
        self,
        base_currency: str,
        quote_currency: str,
        as_of: datetime | None = None,
    ) -> ExchangeRate | None:
        """Return the most recent rate whose effective time is not after ``as_of``."""
        effective_at = self._exchange_rate_as_of(as_of)
        statement = (
            select(ExchangeRate)
            .where(
                ExchangeRate.base_currency == base_currency,
                ExchangeRate.quote_currency == quote_currency,
                ExchangeRate.effective_at <= effective_at,
            )
            .order_by(ExchangeRate.effective_at.desc(), ExchangeRate.id.desc())
            .limit(1)
        )
        return self._session.scalar(statement)

    def get_shipping_rate(
        self,
        profile_code: str,
        destination_country: str,
        weight_g: int,
        as_of: date | datetime | None = None,
    ) -> ShippingRate | None:
        """Return the newest active shipping rate covering ``weight_g`` inclusively."""
        effective_on = self._effective_date(as_of)
        statement = (
            select(ShippingRate)
            .where(
                ShippingRate.profile_code == profile_code,
                ShippingRate.destination_country == destination_country,
                ShippingRate.min_weight_g <= weight_g,
                ShippingRate.max_weight_g >= weight_g,
                ShippingRate.effective_from <= effective_on,
                or_(
                    ShippingRate.effective_to.is_(None),
                    ShippingRate.effective_to >= effective_on,
                ),
            )
            .order_by(ShippingRate.effective_from.desc(), ShippingRate.id.desc())
            .limit(1)
        )
        return self._session.scalar(statement)

    def get_fee_rule(
        self,
        profile_code: str,
        marketplace: str,
        category_code: str | None = None,
        as_of: date | datetime | None = None,
    ) -> FeeRule | None:
        """Return the newest active fee rule matching the requested category exactly."""
        effective_on = self._effective_date(as_of)
        statement: Select[tuple[FeeRule]] = select(FeeRule).where(
            FeeRule.profile_code == profile_code,
            FeeRule.marketplace == marketplace,
            FeeRule.effective_from <= effective_on,
            or_(FeeRule.effective_to.is_(None), FeeRule.effective_to >= effective_on),
        )
        if category_code is None:
            statement = statement.where(FeeRule.category_code.is_(None))
        else:
            statement = statement.where(FeeRule.category_code == category_code)

        statement = statement.order_by(FeeRule.effective_from.desc(), FeeRule.id.desc()).limit(1)
        return self._session.scalar(statement)

    @staticmethod
    def _exchange_rate_as_of(as_of: datetime | None) -> datetime:
        if as_of is None:
            return datetime.now(UTC).replace(tzinfo=None)
        if as_of.tzinfo is not None:
            return as_of.astimezone(UTC).replace(tzinfo=None)
        return as_of

    @staticmethod
    def _effective_date(as_of: date | datetime | None) -> date:
        if as_of is None:
            return datetime.now(UTC).date()
        if isinstance(as_of, datetime):
            return as_of.date()
        return as_of
