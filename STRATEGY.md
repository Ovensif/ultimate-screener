# Trading Strategy

The screener uses a **trend-following breakout + retest** philosophy: ride trends, wait for breakouts, enter on retests, with high R:R and volume confirmation.

## Philosophy

- Don't fight trends; trade in the direction of the higher timeframe.
- Wait for breakouts, then enter on retests to avoid chasing.
- Only take setups with minimum 1:2 risk:reward.
- Volume must confirm moves.
- Multi-timeframe confluence (1D trend + 4H setup).

## Primary approach: Liquidity sweep + momentum continuation

1. **Identify trending coins** – Not ranging or choppy; 1D and 4H structure and EMAs align.
2. **Wait for liquidity sweep or breakout retest** – Fake breakdown/breakout that reverses, or clean retest of a broken level.
3. **Enter on confirmation** – Momentum shift (volume, candle close, RSI/MACD).
4. **Targets** – Previous highs/lows with tight stops below/above structure.

## Signal types (priority order)

### 1. Breakout retest (highest win rate)

- Price breaks resistance (or support for short) with volume &gt; 1.5× average.
- Pulls back to test that level as new support (or resistance).
- Bounces with a bullish (or bearish) candle and volume.
- **Entry**: On retest; **Stop**: Below retest level; **Target**: Next resistance (or support).

### 2. Liquidity sweep

- Price sweeps below key support (long wick, stop hunt), then reverses and closes above support with strong volume.
- For shorts: sweep above resistance, then close below with volume.
- **Entry**: On reversal; **Stop**: Tight below the swept low (or above the swept high); **Target**: Previous high (or low).

### 3. Trend continuation

- Clear trend on 4H (and 1D).
- Healthy pullback to 50% fib or EMA21.
- RSI reset (e.g. 40–50 for longs, 45–60 for shorts), not overstretched.
- **Entry**: On bounce at the level; **Stop**: Below pullback low (or above pullback high); **Target**: Trend continuation (next structure level).

## Timeframes

- **1D**: Trend direction only (price vs 50 EMA, higher lows / lower highs).
- **4H**: All setup detection (breakout retest, liquidity sweep, trend continuation) and confluence (volume, RSI, MACD, levels).
- **15m**: Optional for finer entry timing; not required for signal generation.

## Confluence (at least 2)

- Volume spike in direction.
- RSI &gt; 50 (long) or &lt; 50 (short), or divergence.
- MACD histogram turning positive (long) or negative (short).
- Price at major support/resistance or in a fair value gap (FVG).

## Confidence and filtering

- **3+ confluence factors** → HIGH confidence.
- **2 confluence factors** → MEDIUM confidence.
- By default only **HIGH** confidence signals are sent (configurable via `CONFIDENCE_THRESHOLD`).
- **R:R** must be ≥ 2.0 (configurable); otherwise the trade is skipped.
- **Stop** distance from entry is capped at 2–3% to limit risk per trade.

## Risk management

- Stop loss: Below recent low (long) or above recent high (short), with max distance cap.
- Targets: Next resistance (long) or support (short); second target can be the level after.
- Position size is derived from account size and risk % so that if stop is hit, loss equals the chosen risk (e.g. 2% of account).
- Leverage in alerts is suggested and capped (e.g. 2–5×) to avoid over-leveraging.
