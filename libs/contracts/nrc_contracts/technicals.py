"""Technical indicators computed from adjusted prices."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from .common import Scrip, TradingDate


class IndicatorSet(BaseModel):
    """Per-scrip per-date set of indicators. Maps 1:1 to gold.indicators_daily."""
    model_config = ConfigDict(extra="forbid")

    scrip: Scrip
    date: TradingDate
    close: float                                    # adjusted_close used for computation

    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None

    ema_12: float | None = None
    ema_26: float | None = None

    rsi_14: float | None = None

    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None

    bollinger_upper: float | None = None
    bollinger_middle: float | None = None
    bollinger_lower: float | None = None

    atr_14: float | None = None
    adx_14: float | None = None

    volume_sma_20: float | None = None

    computed_at: datetime
