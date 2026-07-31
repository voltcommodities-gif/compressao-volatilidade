"""Detecção do VCP (Volatility Contraction Pattern) de Mark Minervini.

Um VCP é uma BASE dentro de uma tendência de alta (Stage 2) formada por uma
sequência de correções cada vez MENORES (contrações que apertam), com fundos
ASCENDENTES e volume secando. O ponto de compra é o PIVÔ = topo da última
(menor) contração; o sinal dispara quando o preço rompe o pivô, idealmente com
volume 40–50% acima da média.

Sem look-ahead: um pivô (topo/fundo) só é confirmado `order` barras depois; a
base só é "conhecida" quando o último topo está confirmado, e o rompimento
acionável só a partir daí.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def find_pivots(price: np.ndarray, order: int):
    """Pivôs locais alternados (H=topo, L=fundo)."""
    n = len(price)
    raw = []
    for i in range(order, n - order):
        w = price[i - order:i + order + 1]
        c = price[i]
        if c == w.max() and (w == c).sum() == 1:
            raw.append((i, "H"))
        elif c == w.min() and (w == c).sum() == 1:
            raw.append((i, "L"))
    alt = []
    for p in raw:
        if not alt or alt[-1][1] != p[1]:
            alt.append(p)
        else:  # mantém o mais extremo em repetições
            keep = (price[p[0]] > price[alt[-1][0]]) if p[1] == "H" else (price[p[0]] < price[alt[-1][0]])
            if keep:
                alt[-1] = p
    return alt


def detect_vcp(df, rs_pct=None, order=8, min_contractions=2, first_depth_max=0.35,
               last_depth_max=0.15, live_window=60, search=180):
    close = df["close"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    vol = df["volume"].to_numpy(float)
    vol50 = df["vol50"].to_numpy(float)
    stage2 = df["stage2"].to_numpy(bool)
    if rs_pct is None:
        rs_pct = np.full(len(close), np.nan)
    n = len(close)
    piv = find_pivots(close, order)
    # preço de cada pivô = extremo intradiário (topo=high, fundo=low)
    P = [(i, float(high[i] if k == "H" else low[i]), k) for i, k in piv]

    setups = []
    used_end = set()
    for e in range(len(P) - 1, -1, -1):
        if P[e][2] != "H":
            continue
        # estende a base para trás enquanto as contrações apertam e os fundos sobem
        Hs = [P[e]]
        Ls = []
        j = e - 1
        while j - 1 >= 0 and P[j][2] == "L" and P[j - 1][2] == "H":
            Hc, Lc = P[j - 1], P[j]
            d_new = (Hc[1] - Lc[1]) / Hc[1]
            if Ls:
                d_right = (Hs[0][1] - Ls[0][1]) / Hs[0][1]
                if not (d_new > d_right + 1e-6 and Lc[1] < Ls[0][1]):
                    break
            Hs.insert(0, Hc)
            Ls.insert(0, Lc)
            j -= 2
        if len(Ls) < min_contractions:
            continue
        depths = [round((Hs[i][1] - Ls[i][1]) / Hs[i][1] * 100, 1) for i in range(len(Ls))]
        d = [x / 100 for x in depths]
        pivot_i, pivot_p = Hs[-1][0], Hs[-1][1]
        if pivot_i in used_end:
            continue
        # regras do VCP
        if d[0] > first_depth_max or d[0] < 0.04:
            continue
        if d[-1] > last_depth_max:
            continue
        prior_high = max(h[1] for h in Hs[:-1])
        if pivot_p < prior_high * 0.97:          # pivô no topo da base
            continue
        # contração no TEMPO (estrutural): a última correção mais curta que a primeira
        durs = [Ls[i][0] - Hs[i][0] for i in range(len(Ls))]
        if durs[-1] > durs[0]:
            continue

        # --- métricas de qualidade (guardadas; viram FILTROS opcionais na UI) ---
        stage2_at = bool(stage2[pivot_i])
        rs_at = None if np.isnan(rs_pct[pivot_i]) else round(float(rs_pct[pivot_i]))
        base_lo = min(l[1] for l in Ls)
        base_i0 = Hs[0][0]
        seg = vol[base_i0:pivot_i + 1]           # volume secando: 1/3 final vs. inicial
        vdry = None
        if len(seg) >= 6:
            a, b = seg[:len(seg) // 3], seg[-len(seg) // 3:]
            if a.mean() > 0:
                vdry = round(float(b.mean() / a.mean()), 2)

        # rompimento acionável: 1º fechamento > pivô, a partir do pivô confirmado
        start = pivot_i + order
        brk, vol_ok = None, False
        for t in range(start, min(n, pivot_i + search)):
            if close[t] < base_lo:               # perdeu a base antes de romper
                break
            if close[t] > pivot_p:
                brk = t
                vol_ok = bool(vol50[t] > 0 and vol[t] >= 1.4 * vol50[t])
                break

        # status
        if brk is not None:
            status = "rompeu"
        elif close[-1] < base_lo:
            status = "falhou"
        elif pivot_i >= n - live_window and close[-1] <= pivot_p:
            status = "em_formacao"
        else:
            continue                              # base velha que não resolveu

        # avaliação forward (só rompimentos): retorno após o rompimento
        fwd = {"scored": False}
        if brk is not None:
            for H in (5, 10, 20, 40, 60):
                if brk + H < n:
                    fwd[f"r{H}"] = round((close[brk + H] / close[brk] - 1) * 100, 2)
                else:
                    fwd[f"r{H}"] = None
            fwd["scored"] = fwd["r20"] is not None

        used_end.add(pivot_i)
        setups.append(dict(
            points=[dict(i=int(h[0]), k="H") for h in Hs] + [dict(i=int(l[0]), k="L") for l in Ls],
            highs=[int(h[0]) for h in Hs], lows=[int(l[0]) for l in Ls],
            depths=depths, durations=[int(x) for x in durs], n_contractions=len(Ls),
            rs=rs_at, stage2=stage2_at, pivot_i=int(pivot_i), pivot=round(pivot_p, 2),
            base_lo=round(base_lo, 2), stop=round(pivot_p * 0.92, 2),
            target=round(pivot_p + (pivot_p - base_lo), 2),   # alvo ~ altura da base
            vol_dry=vdry, vol_ok=bool(vol_ok),
            brk_i=(int(brk) if brk is not None else None),
            status=status,
            last_i=int(brk if brk is not None else pivot_i),
            fwd=fwd, order=order))
    setups.sort(key=lambda s: s["pivot_i"])
    return setups
