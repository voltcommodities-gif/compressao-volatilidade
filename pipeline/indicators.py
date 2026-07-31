"""Indicadores de compressão de volatilidade (Bollinger Band Squeeze / TTM).

Compressão = Bandas de Bollinger (20, 2σ) DENTRO dos Canais de Keltner (20,
1,5×ATR). A "mola" solta quando as bandas voltam a sair do Keltner (disparo).

Tudo usa janelas móveis (fecham no dia t com dados até t): sem look-ahead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BB_LEN = 20
BB_MULT = 2.0
KC_LEN = 20
KC_MULT = 1.5
BW_PCT_WIN = 126     # janela p/ o percentil da largura de banda (~6 meses)


def bollinger(close: pd.Series):
    basis = close.rolling(BB_LEN).mean()
    sd = close.rolling(BB_LEN).std(ddof=0)
    upper = basis + BB_MULT * sd
    lower = basis - BB_MULT * sd
    return basis, upper, lower


def atr(high, low, close, length=KC_LEN):
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()],
                   axis=1).max(axis=1)
    return tr.rolling(length).mean()


def keltner(close, high, low):
    basis = close.rolling(KC_LEN).mean()
    rng = atr(high, low, close, KC_LEN)
    return basis, basis + KC_MULT * rng, basis - KC_MULT * rng


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    basis, bb_up, bb_lo = bollinger(out["close"])
    _, kc_up, kc_lo = keltner(out["close"], out["high"], out["low"])
    out["basis"] = basis
    out["bb_up"], out["bb_lo"] = bb_up, bb_lo
    out["kc_up"], out["kc_lo"] = kc_up, kc_lo
    # largura de banda (%) = amplitude das Bandas / média
    out["bw"] = (bb_up - bb_lo) / basis * 100.0
    # squeeze ON: Bollinger inteiramente dentro do Keltner
    out["squeeze"] = (bb_up < kc_up) & (bb_lo > kc_lo)
    # percentil da largura de banda na janela móvel (0 = mais comprimido que nunca)
    out["bw_pct"] = out["bw"].rolling(BW_PCT_WIN).apply(
        lambda w: (w <= w[-1]).mean() * 100.0, raw=True)
    # momento p/ direção do disparo: preço vs. base (SMA20)
    out["mom"] = out["close"] - out["basis"]
    return out
