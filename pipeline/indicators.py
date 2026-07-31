"""Indicadores para o VCP (Volatility Contraction Pattern) — Minervini.

Inclui as médias 50/150/200, o "trend template" (Stage 2), máx/mín de 52 semanas
e o volume médio. Tudo em janelas passadas (fecham no dia t): sem look-ahead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s, n):
    return s.rolling(n).mean()


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c = out["close"]
    out["sma50"] = sma(c, 50)
    out["sma150"] = sma(c, 150)
    out["sma200"] = sma(c, 200)
    out["vol50"] = out["volume"].rolling(50).mean()
    out["hi52"] = out["high"].rolling(252).max()
    out["lo52"] = out["low"].rolling(252).min()

    # força relativa (RS) estilo IBD: performance ponderada (mais peso no 3M).
    # O RANK percentil entre os ativos é calculado no main (transversal por data).
    r = lambda k: c / c.shift(k) - 1.0
    out["rs_raw"] = 0.4 * r(63) + 0.2 * r(126) + 0.2 * r(189) + 0.2 * r(252)

    s50, s150, s200 = out["sma50"], out["sma150"], out["sma200"]
    # trend template de Minervini (Stage 2), versão baseada em médias/52 semanas
    rising = lambda s, k=22: s > s.shift(k)
    out["stage2"] = (
        (c > s150) & (c > s200) & (s150 > s200) & (s50 > s150) & (c > s50)
        & rising(s200) & rising(s150) & rising(s50)
        & (c >= 1.30 * out["lo52"])         # >=30% acima da mínima de 52s
        & (c >= 0.75 * out["hi52"])         # <=25% abaixo da máxima de 52s
    ).fillna(False)
    return out
