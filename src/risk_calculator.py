"""
Position sizing, leverage, liquidation price for futures.
"""
import logging
from dataclasses import dataclass
from typing import Optional

from . import config

logger = logging.getLogger(__name__)

# Max leverage to recommend in alerts
MAX_LEVERAGE = 5
# Warn if liquidation is within this fraction of entry
LIQUIDATION_WARN_PCT = 0.20


@dataclass
class RiskResult:
    risk_usd: float
    position_size_usd: float
    suggested_leverage: int
    liquidation_price: Optional[float]
    liquidation_warning: bool


def calculate(
    entry: float,
    stop: float,
    side: str,
    account_size: Optional[float] = None,
    risk_pct: Optional[float] = None,
    leverage: Optional[int] = None,
) -> RiskResult:
    """
    Compute risk in USD, position size, and suggested leverage.
    For perpetuals, liquidation (isolated) approx: long liq = entry * (1 - 1/leverage), short liq = entry * (1 + 1/leverage).
    """
    account_size = account_size or config.ACCOUNT_SIZE
    risk_pct = risk_pct or config.RISK_PER_TRADE
    risk_usd = account_size * (risk_pct / 100.0)
    distance_pct = abs(entry - stop) / entry if entry else 0
    if distance_pct <= 0:
        return RiskResult(
            risk_usd=risk_usd,
            position_size_usd=0,
            suggested_leverage=1,
            liquidation_price=None,
            liquidation_warning=False,
        )
    # Position size so that (position_size * distance_pct) = risk_usd -> position_size = risk_usd / distance_pct
    position_size_usd = risk_usd / distance_pct
    # Cap leverage so we don't suggest 100x
    lev = leverage
    if lev is None:
        lev = min(MAX_LEVERAGE, max(1, int(position_size_usd / account_size)))
        lev = max(1, min(lev, MAX_LEVERAGE))
    # Isolated margin liquidation approx
    if side.upper() == "LONG":
        liq = entry * (1 - 1.0 / lev)  # simplified
    else:
        liq = entry * (1 + 1.0 / lev)
    dist_to_liq = abs(entry - liq) / entry
    liquidation_warning = dist_to_liq <= LIQUIDATION_WARN_PCT
    return RiskResult(
        risk_usd=risk_usd,
        position_size_usd=position_size_usd,
        suggested_leverage=lev,
        liquidation_price=liq,
        liquidation_warning=liquidation_warning,
    )
