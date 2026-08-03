"""Pipeline VCP (Minervini): baixa OHLCV, detecta bases de contração de
volatilidade, os rompimentos e seu poder preditivo, e gera docs/index.html."""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from data import load_ohlcv, read_tickers
from indicators import compute_all
from vcp import detect_vcp

HERE = Path(__file__).resolve().parent.parent
DOCS = HERE / "docs"
TEMPLATE = HERE / "templates" / "painel.template.html"
HORIZONS = [5, 10, 20, 40, 60]
ORDER = 8
log = logging.getLogger("pipeline")


def _rs(a, nd=2):
    return [None if (v is None or (isinstance(v, float) and np.isnan(v))) else round(float(v), nd) for v in a]


def _ri(a):
    return [None if (v is None or (isinstance(v, float) and np.isnan(v))) else int(v) for v in a]


def process(ticker, ind, rs_pct, mkt):
    setups = detect_vcp(ind, rs_pct=rs_pct.to_numpy(float), order=ORDER)
    dates = [d.strftime("%Y-%m-%d") for d in ind.index]
    n = len(dates)
    close = ind["close"].to_numpy(float)
    for s in setups:
        s["base_date"] = dates[s["highs"][0]]
        s["pivot_date"] = dates[s["pivot_i"]]
        s["brk_date"] = dates[s["brk_i"]] if s["brk_i"] is not None else None
        s["market_ok"] = bool(mkt[s["brk_i"] if s["brk_i"] is not None else s["pivot_i"]])
        if s["brk_i"] is not None:                 # alvo × stop após o rompimento
            b, oc = s["brk_i"], "sem_dados"
            endw = min(n, b + 1 + 60)
            for t in range(b + 1, endw):
                if close[t] >= s["target"]:
                    oc = "alvo"; break
                if close[t] <= s["stop"]:
                    oc = "stop"; break
            else:
                oc = "aberto" if endw >= b + 1 + 60 else "sem_dados"
            s["fwd"]["outcome"] = oc

    panel = dict(
        dates=dates,
        close=_rs(close, 2),
        sma50=_rs(ind["sma50"].to_numpy(), 2),
        sma150=_rs(ind["sma150"].to_numpy(), 2),
        sma200=_rs(ind["sma200"].to_numpy(), 2),
        volume=_ri(ind["volume"].to_numpy()),
        vol50=_ri(ind["vol50"].to_numpy()),
        setups=setups,
    )
    # o STATE por ativo (em formação / rompeu / nenhum) é derivado no painel,
    # porque depende dos FILTROS de qualidade que o usuário liga/desliga.
    screen = dict(
        ticker=ticker, name=ticker.replace(".SA", ""),
        last_price=round(float(close[-1]), 2), last_date=dates[-1],
        n_setups=len(setups), stage2_today=bool(ind["stage2"].iloc[-1]),
        rs_today=(None if np.isnan(rs_pct.iloc[-1]) else round(float(rs_pct.iloc[-1]))),
        market_today=bool(mkt[-1]),
    )
    return panel, screen


def baseline(closes):
    out = {}
    for H in HORIZONS:
        rs = [c[H:] / c[:-H] - 1.0 for c in closes if len(c) > H]
        allr = np.concatenate(rs) if rs else np.array([0.0])
        out[H] = round(float(np.mean(allr)) * 100, 2)
    return out


def build_site(payload):
    tpl = TEMPLATE.read_text()
    data = json.dumps(payload).replace("</", "<\\/")
    (DOCS / "index.html").write_text(tpl.replace("__DATA__", data))
    log.info("Painel escrito (%.0f KB)", len((DOCS / "index.html").read_text().encode()) / 1024)


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    end_default = datetime.today().strftime("%Y-%m-%d")
    start_default = (datetime.today() - timedelta(days=365 * 10 + 5)).strftime("%Y-%m-%d")
    p = argparse.ArgumentParser(description="Screening VCP (Minervini).")
    p.add_argument("--tickers", default=str(HERE / "tickers.txt"))
    p.add_argument("--start", default=start_default)
    p.add_argument("--end", default=end_default)
    p.add_argument("--no-cache", action="store_true")
    args = p.parse_args(argv)

    import pandas as pd
    tickers = read_tickers(args.tickers)
    log.info("Tickers: %s", ", ".join(tickers))

    # fase 1: baixa e calcula indicadores de todos
    inds = {}
    for t in tickers:
        log.info("Baixando %s ...", t)
        df = load_ohlcv(t, args.start, args.end, use_cache=not args.no_cache)
        if df is not None and len(df) >= 260:
            inds[t] = compute_all(df)

    # RS transversal: percentil da força relativa entre os ativos, por data
    rs_mat = pd.DataFrame({t: inds[t]["rs_raw"] for t in inds})
    rs_pct_mat = rs_mat.rank(axis=1, pct=True) * 100.0

    # ambiente de mercado: índice (SPY/QQQ) acima da sua média mensal de 10 períodos.
    # Sem look-ahead: uso a EMA até o mês ANTERIOR (shift) para os dias do mês corrente.
    bench = "SPY" if "SPY" in inds else ("QQQ" if "QQQ" in inds else None)
    if bench:
        bc = inds[bench]["close"]
        monthly = bc.resample("ME").last()
        ema10 = monthly.ewm(span=10, adjust=False).mean().shift(1)
        fav = (bc >= ema10.reindex(bc.index, method="ffill")).fillna(False)
    else:
        fav = None

    # fase 2: detecta o VCP com RS e ambiente de mercado disponíveis
    data, order = {}, []
    for t in inds:
        rs_pct = rs_pct_mat[t].reindex(inds[t].index)
        if fav is not None:
            mkt = fav.reindex(inds[t].index, method="ffill").fillna(False).to_numpy(bool)
        else:
            mkt = np.ones(len(inds[t]), bool)
        panel, screen = process(t, inds[t], rs_pct, mkt)
        panel["screen"] = screen
        data[t] = panel
        order.append(t)

    base = baseline([np.array(data[t]["close"], float) for t in order])
    payload = dict(
        meta=dict(start=args.start, end=args.end,
                  generated=datetime.today().strftime("%Y-%m-%d %H:%M"),
                  horizons=HORIZONS, baseline=base, order=ORDER),
        tickers=order,
        screen=[data[t]["screen"] for t in order],
        data={t: {k: v for k, v in data[t].items() if k != "screen"} for t in order},
    )
    build_site(payload)
    nb = sum(len(data[t]["setups"]) for t in order)
    log.info("Pronto. %d ativos, %d VCPs.", len(order), nb)


if __name__ == "__main__":
    main()
