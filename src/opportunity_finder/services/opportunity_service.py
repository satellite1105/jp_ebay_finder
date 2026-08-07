"""Application service for deterministic opportunity calculations."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_finder.db.models import FeeRule, MarketQuery, Product, ShippingRate
from opportunity_finder.db.repositories.market_repository import MarketRepository
from opportunity_finder.db.repositories.opportunity_repository import OpportunityRepository
from opportunity_finder.db.repositories.product_repository import ProductRepository
from opportunity_finder.db.repositories.reference_data_repository import ReferenceDataRepository
from opportunity_finder.db.repositories.supplier_repository import SupplierRepository
from opportunity_finder.domain.decisions import determine_decision
from opportunity_finder.domain.models import (
    ComplianceDecision,
    OpportunityResult,
    ProfitInput,
    Scenario,
    ScenarioMultipliers,
)
from opportunity_finder.domain.profit import calculate_scenario
from opportunity_finder.domain.scoring import (
    calculate_confidence_score,
    calculate_opportunity_score,
)

SCENARIOS: tuple[Scenario, ...] = ("optimistic", "base", "conservative")
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RULES_PATH = PROJECT_ROOT / "config" / "candidate_rules.yaml"
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.example.yaml"
ZERO = Decimal(0)


class OpportunityService:
    """Coordinate repository reads, domain calculations, and snapshot writes.

    The caller owns the SQLAlchemy transaction. Reference profile codes may be
    supplied by a CLI or test; when omitted, the newest applicable database row
    is selected deterministically.
    """

    def __init__(
        self,
        session: Session,
        *,
        rules_path: Path | str = DEFAULT_RULES_PATH,
        settings_path: Path | str = DEFAULT_SETTINGS_PATH,
        shipping_profile_code: str | None = None,
        fee_profile_code: str | None = None,
        destination_country: str | None = None,
        fee_base_is_item_price_only: bool = False,
        as_of: datetime | None = None,
        calculator_version: str = "opportunity-service-v1",
    ) -> None:
        self._session = session
        self._product_repository = ProductRepository(session)
        self._supplier_repository = SupplierRepository(session)
        self._market_repository = MarketRepository(session)
        self._reference_repository = ReferenceDataRepository(session)
        self._opportunity_repository = OpportunityRepository(session)
        self._rules_path = Path(rules_path)
        self._settings_path = Path(settings_path)
        self._shipping_profile_code = shipping_profile_code
        self._fee_profile_code = fee_profile_code
        self._destination_country = destination_country
        self._fee_base_is_item_price_only = fee_base_is_item_price_only
        self._as_of = _as_utc_naive(as_of) if as_of is not None else None
        self._calculator_version = calculator_version

    def calculate_opportunities(self) -> list[OpportunityResult]:
        """Calculate and persist all products having enough pricing inputs.

        A single :class:`OpportunityResult` contains all three scenarios, while
        the database receives one immutable row per scenario. Products lacking
        an input needed even to perform the arithmetic (for example, no selling
        price or exchange rate) are left uncalculated. Nullable demand fields are
        retained as missing and therefore produce ``MISSING_DATA``.
        """
        thresholds, multipliers = self._load_calculation_rules()
        calculated_at = self._as_of or datetime.now(UTC).replace(tzinfo=None)
        results: list[OpportunityResult] = []

        product_ids = self._session.scalars(select(Product.id).order_by(Product.id)).all()
        for product_id in product_ids:
            product = self._product_repository.get_by_id(product_id)
            if product is None:
                continue
            result = self._calculate_product(
                product,
                thresholds=thresholds,
                multipliers=multipliers,
                calculated_at=calculated_at,
            )
            if result is not None:
                results.append(result)

        return results

    def _calculate_product(
        self,
        product: Product,
        *,
        thresholds: dict[str, Any],
        multipliers: dict[Scenario, ScenarioMultipliers],
        calculated_at: datetime,
    ) -> OpportunityResult | None:
        supplier_choice = self._latest_available_supplier_price(product.id)
        market_choice = self._latest_market_metric(product.id)
        if supplier_choice is None or market_choice is None or product.weight_g is None:
            return None

        supplier_item, source_price = supplier_choice
        query, market_metric = market_choice
        market_price = market_metric.median_sold_price or market_metric.average_sold_price
        if market_price is None:
            return None

        exchange_rate = self._reference_repository.get_latest_exchange_rate(
            market_metric.currency,
            "JPY",
            as_of=calculated_at,
        )
        if exchange_rate is None:
            return None

        destination_country = self._destination_country or _marketplace_country(query.marketplace)
        shipping_profile = self._shipping_profile_code or self._find_shipping_profile(
            destination_country=destination_country,
            weight_g=product.weight_g,
            as_of=calculated_at.date(),
        )
        if shipping_profile is None:
            return None
        shipping_rate = self._reference_repository.get_shipping_rate(
            shipping_profile,
            destination_country,
            product.weight_g,
            as_of=calculated_at.date(),
        )
        if shipping_rate is None:
            return None

        fee_category, fee_profile = self._resolve_fee_profile(
            query=query,
            product=product,
            as_of=calculated_at.date(),
        )
        if fee_profile is None:
            return None
        fee_rule = self._reference_repository.get_fee_rule(
            fee_profile,
            query.marketplace,
            category_code=fee_category,
            as_of=calculated_at.date(),
        )
        if fee_rule is None:
            return None

        fixed_fee_jpy = self._fixed_fee_jpy(
            fee_rule=fee_rule,
            market_currency=market_metric.currency,
            market_exchange_rate=exchange_rate.rate,
            as_of=calculated_at,
        )
        if fixed_fee_jpy is None:
            return None

        source_item_cost = (
            source_price.item_price_jpy
            - source_price.points_value_jpy
            - source_price.coupon_value_jpy
        )
        capital_required = source_price.effective_cost_jpy + shipping_rate.shipping_jpy
        if capital_required <= ZERO:
            return None

        profit_input = ProfitInput(
            item_price_usd=market_price,
            buyer_shipping_usd=market_metric.average_shipping or ZERO,
            exchange_rate_jpy_per_usd=exchange_rate.rate,
            source_item_cost_jpy=source_item_cost,
            source_domestic_shipping_jpy=source_price.domestic_shipping_jpy,
            international_shipping_jpy=shipping_rate.shipping_jpy,
            marketplace_fee_rate=fee_rule.variable_fee_rate,
            marketplace_fixed_fee_jpy=fixed_fee_jpy,
            international_fee_rate=fee_rule.international_fee_rate,
            fee_base_is_item_price_only=self._fee_base_is_item_price_only,
            ad_rate=fee_rule.ad_rate,
            return_reserve_rate=fee_rule.return_reserve_rate,
            cash_required_before_sale_jpy=capital_required,
            target_profit_jpy=Decimal(str(thresholds["minimum_base_profit_jpy"])),
        )
        scenarios = {
            scenario: calculate_scenario(profit_input, multipliers[scenario], scenario)
            for scenario in SCENARIOS
        }

        source_age_days = _age_days(calculated_at, source_price.captured_at)
        market_age_days = _age_days(calculated_at, market_metric.researched_at)
        risk_flags = _compliance_flags(product.compliance_flags)
        confidence_score, confidence_breakdown = calculate_confidence_score(
            match_method=supplier_item.match_method,
            title_similarity=supplier_item.match_confidence,
            market_data_count=market_metric.sold_count or 0,
            source_data_age_days=source_age_days,
            weight_is_measured=product.weight_g is not None,
            origin_confirmed=product.origin_country is not None,
            condition_mismatch=_contains_flag(risk_flags, "condition_mismatch"),
            unit_count_mismatch=_contains_flag(risk_flags, "unit_count_mismatch"),
            model_number_ambiguous=_contains_flag(risk_flags, "model_number_ambiguous"),
        )
        base = scenarios["base"]
        conservative = scenarios["conservative"]
        opportunity_score, score_breakdown = calculate_opportunity_score(
            base_profit_jpy=base.net_profit_jpy,
            base_margin=base.net_margin,
            sold_90d=market_metric.sold_count or 0,
            sell_through_rate=market_metric.sell_through_rate or ZERO,
            capital_efficiency=base.capital_efficiency,
            conservative_profit_jpy=conservative.net_profit_jpy,
            confidence_score=confidence_score,
            is_replenishable=product.repeatable_supply,
            risk_flags=risk_flags,
        )

        compliance = ComplianceDecision(
            compliance_status=_normalize_compliance_status(product.compliance_status),
            flags=risk_flags,
        )
        has_required_data = (
            market_metric.sold_count is not None
            and market_metric.sell_through_rate is not None
            and market_metric.average_shipping is not None
        )
        decision, reason_codes = determine_decision(
            compliance=compliance,
            has_required_data=has_required_data,
            source_data_age_days=source_age_days,
            market_data_age_days=market_age_days,
            sold_90d=market_metric.sold_count,
            sell_through_rate=market_metric.sell_through_rate,
            base_profit_jpy=base.net_profit_jpy,
            base_margin=base.net_margin,
            conservative_profit_jpy=conservative.net_profit_jpy,
            confidence_score=confidence_score,
            is_first_purchase=True,
            has_test_purchase_history=False,
            has_replenish_history=False,
            thresholds=thresholds,
        )

        input_snapshot = _json_safe(
            {
                "product": {
                    "id": product.id,
                    "weight_g": product.weight_g,
                    "origin_country": product.origin_country,
                    "repeatable_supply": product.repeatable_supply,
                    "compliance_status": product.compliance_status,
                    "compliance_flags": risk_flags,
                },
                "supplier": {
                    "supplier_item_id": supplier_item.id,
                    "price_snapshot_id": source_price.id,
                    "item_price_jpy": source_price.item_price_jpy,
                    "domestic_shipping_jpy": source_price.domestic_shipping_jpy,
                    "points_value_jpy": source_price.points_value_jpy,
                    "coupon_value_jpy": source_price.coupon_value_jpy,
                    "effective_cost_jpy": source_price.effective_cost_jpy,
                    "captured_at": source_price.captured_at,
                    "age_days": source_age_days,
                    "match_method": supplier_item.match_method,
                    "match_confidence": supplier_item.match_confidence,
                },
                "market": {
                    "query_id": query.id,
                    "metric_id": market_metric.id,
                    "marketplace": query.marketplace,
                    "currency": market_metric.currency,
                    "median_sold_price": market_metric.median_sold_price,
                    "average_sold_price": market_metric.average_sold_price,
                    "average_shipping": market_metric.average_shipping,
                    "sold_count": market_metric.sold_count,
                    "sell_through_rate": market_metric.sell_through_rate,
                    "researched_at": market_metric.researched_at,
                    "age_days": market_age_days,
                },
                "exchange_rate": {
                    "id": exchange_rate.id,
                    "base_currency": exchange_rate.base_currency,
                    "quote_currency": exchange_rate.quote_currency,
                    "rate": exchange_rate.rate,
                    "source": exchange_rate.source,
                    "effective_at": exchange_rate.effective_at,
                },
                "shipping_rate": {
                    "id": shipping_rate.id,
                    "profile_code": shipping_rate.profile_code,
                    "destination_country": shipping_rate.destination_country,
                    "shipping_jpy": shipping_rate.shipping_jpy,
                    "effective_from": shipping_rate.effective_from,
                    "effective_to": shipping_rate.effective_to,
                },
                "fee_rule": {
                    "id": fee_rule.id,
                    "profile_code": fee_rule.profile_code,
                    "category_code": fee_rule.category_code,
                    "variable_fee_rate": fee_rule.variable_fee_rate,
                    "international_fee_rate": fee_rule.international_fee_rate,
                    "fixed_fee_currency": fee_rule.fixed_fee_currency,
                    "fixed_fee_amount": fee_rule.fixed_fee_amount,
                    "fixed_fee_jpy": fixed_fee_jpy,
                    "ad_rate": fee_rule.ad_rate,
                    "return_reserve_rate": fee_rule.return_reserve_rate,
                    "fee_base_is_item_price_only": self._fee_base_is_item_price_only,
                    "effective_from": fee_rule.effective_from,
                    "effective_to": fee_rule.effective_to,
                },
                "candidate_rules": thresholds,
                "scenario_multipliers": multipliers,
            }
        )

        result = OpportunityResult(
            product_id=product.id,
            query_id=query.id,
            scenarios=scenarios,
            opportunity_score=opportunity_score,
            score_breakdown=score_breakdown,
            confidence_score=confidence_score,
            confidence_breakdown=confidence_breakdown,
            decision=decision,
            reason_codes=reason_codes,
            input_snapshot=input_snapshot,
        )
        self._save_scenario_snapshots(
            result=result,
            profit_input=profit_input,
            fee_rule=fee_rule,
            shipping_rate=shipping_rate,
            market_currency=market_metric.currency,
            base_exchange_rate=exchange_rate.rate,
            multipliers=multipliers,
            calculated_at=calculated_at,
        )
        return result

    def _latest_available_supplier_price(self, product_id: int) -> tuple[Any, Any] | None:
        candidates: list[tuple[Any, Any]] = []
        for item in self._supplier_repository.list_supplier_items_for_product(product_id):
            price = self._supplier_repository.get_latest_price_snapshot(item.id)
            if price is not None and price.available:
                candidates.append((item, price))
        if not candidates:
            return None
        return min(
            candidates, key=lambda candidate: (candidate[1].effective_cost_jpy, candidate[0].id)
        )

    def _latest_market_metric(self, product_id: int) -> tuple[MarketQuery, Any] | None:
        query_ids = self._session.scalars(
            select(MarketQuery.id)
            .where(MarketQuery.product_id == product_id, MarketQuery.enabled.is_(True))
            .order_by(MarketQuery.id)
        ).all()
        candidates: list[tuple[MarketQuery, Any]] = []
        for query_id in query_ids:
            query = self._market_repository.get_query(query_id)
            metric = self._market_repository.get_latest_research_metric(query_id)
            if query is not None and metric is not None:
                candidates.append((query, metric))
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: (candidate[1].researched_at, candidate[1].id))

    def _find_shipping_profile(
        self, *, destination_country: str, weight_g: int, as_of: date
    ) -> str | None:
        return self._session.scalar(
            select(ShippingRate.profile_code)
            .where(
                ShippingRate.destination_country == destination_country,
                ShippingRate.min_weight_g <= weight_g,
                ShippingRate.max_weight_g >= weight_g,
                ShippingRate.effective_from <= as_of,
                (ShippingRate.effective_to.is_(None) | (ShippingRate.effective_to >= as_of)),
            )
            .order_by(ShippingRate.effective_from.desc(), ShippingRate.id.desc())
            .limit(1)
        )

    def _resolve_fee_profile(
        self, *, query: MarketQuery, product: Product, as_of: date
    ) -> tuple[str | None, str | None]:
        categories = list(dict.fromkeys((query.category_id, product.category, None)))
        if self._fee_profile_code is not None:
            for category in categories:
                rule = self._reference_repository.get_fee_rule(
                    self._fee_profile_code,
                    query.marketplace,
                    category_code=category,
                    as_of=as_of,
                )
                if rule is not None:
                    return category, self._fee_profile_code
            return None, None

        for category in categories:
            statement = select(FeeRule.profile_code).where(
                FeeRule.marketplace == query.marketplace,
                FeeRule.effective_from <= as_of,
                (FeeRule.effective_to.is_(None) | (FeeRule.effective_to >= as_of)),
            )
            if category is None:
                statement = statement.where(FeeRule.category_code.is_(None))
            else:
                statement = statement.where(FeeRule.category_code == category)
            profile = self._session.scalar(
                statement.order_by(FeeRule.effective_from.desc(), FeeRule.id.desc()).limit(1)
            )
            if profile is not None:
                return category, profile
        return None, None

    def _fixed_fee_jpy(
        self,
        *,
        fee_rule: FeeRule,
        market_currency: str,
        market_exchange_rate: Decimal,
        as_of: datetime,
    ) -> Decimal | None:
        if fee_rule.fixed_fee_currency == "JPY":
            return fee_rule.fixed_fee_amount
        if fee_rule.fixed_fee_currency == market_currency:
            return fee_rule.fixed_fee_amount * market_exchange_rate
        rate = self._reference_repository.get_latest_exchange_rate(
            fee_rule.fixed_fee_currency,
            "JPY",
            as_of=as_of,
        )
        return None if rate is None else fee_rule.fixed_fee_amount * rate.rate

    def _save_scenario_snapshots(
        self,
        *,
        result: OpportunityResult,
        profit_input: ProfitInput,
        fee_rule: FeeRule,
        shipping_rate: ShippingRate,
        market_currency: str,
        base_exchange_rate: Decimal,
        multipliers: dict[Scenario, ScenarioMultipliers],
        calculated_at: datetime,
    ) -> None:
        for scenario in SCENARIOS:
            scenario_result = result.scenarios[scenario]
            scenario_multiplier = multipliers[scenario]
            international_fee = (
                scenario_result.recognized_revenue_jpy * fee_rule.international_fee_rate
            )
            self._opportunity_repository.save_snapshot(
                product_id=result.product_id,
                query_id=result.query_id,
                scenario=scenario,
                source_cost_jpy=(
                    profit_input.source_item_cost_jpy + profit_input.source_domestic_shipping_jpy
                ),
                buyer_total_market_currency=scenario_result.buyer_total_usd,
                market_currency=market_currency,
                exchange_rate=(base_exchange_rate * scenario_multiplier.exchange_rate_multiplier),
                revenue_jpy=scenario_result.recognized_revenue_jpy,
                marketplace_fees_jpy=(scenario_result.marketplace_fee_jpy + international_fee),
                advertising_reserve_jpy=scenario_result.promoted_listing_jpy,
                return_reserve_jpy=scenario_result.return_reserve_jpy,
                duty_processing_jpy=(profit_input.duty_jpy + profit_input.import_processing_jpy),
                international_shipping_jpy=(
                    shipping_rate.shipping_jpy * scenario_multiplier.shipping_multiplier
                ),
                packaging_jpy=profit_input.packaging_jpy,
                other_costs_jpy=(
                    profit_input.source_transport_jpy
                    + profit_input.currency_conversion_jpy
                    + profit_input.payment_fee_jpy
                    + profit_input.labor_cost_jpy
                    + profit_input.other_cost_jpy
                ),
                total_cost_jpy=scenario_result.total_cost_jpy,
                net_profit_jpy=scenario_result.net_profit_jpy,
                net_margin=scenario_result.net_margin,
                break_even_buyer_total=scenario_result.break_even_buyer_total_usd,
                capital_required_jpy=profit_input.cash_required_before_sale_jpy,
                capital_efficiency=scenario_result.capital_efficiency,
                opportunity_score=result.opportunity_score,
                data_confidence=result.confidence_score,
                decision=result.decision,
                reason_codes=result.reason_codes,
                input_snapshot=result.input_snapshot,
                calculated_at=calculated_at,
                calculator_version=self._calculator_version,
            )

    def _load_calculation_rules(
        self,
    ) -> tuple[dict[str, Any], dict[Scenario, ScenarioMultipliers]]:
        rules_document = _load_simple_yaml(self._rules_path)
        settings_document = _load_simple_yaml(self._settings_path)
        thresholds = rules_document.get("candidate_rules")
        scenario_values = rules_document.get("scenario_multipliers") or settings_document.get(
            "scenario_multipliers"
        )
        if not isinstance(thresholds, dict):
            raise TypeError(f"candidate_rules mapping is missing from {self._rules_path}")
        if not isinstance(scenario_values, dict):
            raise TypeError("scenario_multipliers mapping is missing from configured YAML")

        missing_thresholds = {
            "minimum_base_profit_jpy",
            "minimum_base_margin",
            "minimum_conservative_profit_jpy",
            "minimum_sold_90d",
            "minimum_sell_through_rate",
            "maximum_source_data_age_days",
            "maximum_market_data_age_days",
            "minimum_confidence_score",
        } - thresholds.keys()
        if missing_thresholds:
            names = ", ".join(sorted(missing_thresholds))
            raise ValueError(f"candidate_rules is missing required values: {names}")

        parsed_multipliers: dict[Scenario, ScenarioMultipliers] = {}
        for scenario in SCENARIOS:
            values = scenario_values.get(scenario)
            if not isinstance(values, dict):
                raise TypeError(f"scenario_multipliers.{scenario} mapping is missing")
            parsed_multipliers[scenario] = ScenarioMultipliers.model_validate(values)
        return dict(thresholds), parsed_multipliers


def _load_simple_yaml(path: Path) -> dict[str, Any]:
    """Parse the project's mapping-only YAML without an undeclared dependency."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if "\t" in raw_line:
            raise ValueError(f"Tabs are not supported in {path}:{line_number}")
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        content = raw_line.strip()
        if ":" not in content:
            raise ValueError(f"Expected a mapping entry in {path}:{line_number}")
        key, raw_value = content.split(":", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Empty mapping key in {path}:{line_number}")
        while stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]
        value_text = raw_value.strip()
        if not value_text:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_yaml_scalar(value_text)
    return root


def _parse_yaml_scalar(value: str) -> Any:
    if value.startswith(('"', "'")):
        if value.startswith('"'):
            return json.loads(value)
        return value[1:-1].replace("''", "'")
    normalized = value.casefold()
    if normalized in {"true", "false"}:
        return normalized == "true"
    if normalized in {"null", "~"}:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _marketplace_country(marketplace: str) -> str:
    suffix = marketplace.rsplit("_", 1)[-1].upper()
    if len(suffix) != 2 or not suffix.isalpha():
        raise ValueError(f"Cannot derive destination country from marketplace: {marketplace}")
    return suffix


def _normalize_compliance_status(status: str) -> str:
    normalized = status.strip().casefold()
    if normalized in {"approved", "review", "blocked", "needs_review"}:
        return normalized
    return "needs_review"


def _compliance_flags(value: Any) -> list[str]:
    if isinstance(value, list):
        return sorted({str(flag) for flag in value})
    if isinstance(value, dict):
        return sorted(str(flag) for flag, enabled in value.items() if enabled)
    return []


def _contains_flag(flags: list[str], expected: str) -> bool:
    normalized_expected = expected.casefold()
    return any(flag.strip().casefold() == normalized_expected for flag in flags)


def _age_days(as_of: datetime, observed_at: datetime) -> int:
    delta = _as_utc_naive(as_of) - _as_utc_naive(observed_at)
    return max(delta.days, 0)


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
