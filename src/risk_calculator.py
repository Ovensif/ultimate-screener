"""
Position sizing, leverage, liquidation price for futures.
Beast-mode: confidence-based sizing, ATR-based adjustment, reduced max leverage.
"""
import logging
from dataclasses import dataclass
from typing import Optional

from . import config

logger = logging.getLogger(__name__)

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
    confidence: Optional[str] = None,
    atr_pct: Optional[float] = None,
) -> RiskResult:
    """
    Compute risk in USD, position size, and suggested leverage.
    Beast-mode:
    - Confidence-based sizing: HIGH = full risk%, MEDIUM = half risk%.
    - ATR-based adjustment: if ATR% > 4%, reduce position by 25%.
    - Max leverage from config (default 3x, was 5x).
    """
    account_size = account_size or config.ACCOUNT_SIZE
    risk_pct = risk_pct or config.RISK_PER_TRADE
    max_lev = getattr(config, "MAX_LEVERAGE", 3)

    # Beast-mode: confidence-based risk reduction
    if confidence == "MEDIUM":
        risk_pct = risk_pct * 0.5  # MEDIUM = half risk
        logger.debug("MEDIUM confidence: risk reduced to %.1f%%", risk_pct)

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

    # Position size so that (position_size * distance_pct) = risk_usd
    position_size_usd = risk_usd / distance_pct

    # Beast-mode: ATR-based reduction -- high volatility = smaller position
    if atr_pct is not None and atr_pct > 4.0:
        position_size_usd *= 0.75
        logger.debug("High ATR (%.2f%%): position reduced by 25%%", atr_pct)

    # Cap leverage
    lev = leverage
    if lev is None:
        lev = min(max_lev, max(1, int(position_size_usd / account_size)))
        lev = max(1, min(lev, max_lev))

    # Isolated margin liquidation approx
    if side.upper() == "LONG":
        liq = entry * (1 - 1.0 / lev)
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
