"""Pipeline: baixa OHLCV, detecta compressão de volatilidade (Bollinger Squeeze),
os disparos e seu poder preditivo, e gera o painel único em docs/index.html.
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from data import load_ohlcv, read_tickers
from indicators import compute_all

HERE = Path(__file__).resolve().parent.parent
DOCS = HERE / "docs"
TEMPLATE = HERE / "templates" / "painel.template.html"

HORIZONS = [10, 20, 40]
FRESH_FIRE = 5        # "disparou" = disparo nos últimos N pregões
log = logging.getLogger("pipeline")


def _rs(s, nd=2):
    return [None if (v is None or (isinstance(v, float) and np.isnan(v))) else round(float(v), nd)
            for v in s]


def detect_and_eval(ind):
    close = ind["close"].to_numpy(float)
    sq = ind["squeeze"].fillna(False).to_numpy(bool)
    mom = ind["mom"].to_numpy(float)
    bw = ind["bw"].to_numpy(float)
    bw_pct = ind["bw_pct"].to_numpy(float)
    n = len(close)
    dates = [d.strftime("%Y-%m-%d") for d in ind.index]

    # dias consecutivos comprimidos terminando em cada barra
    run = np.zeros(n, int)
    for i in range(n):
        run[i] = run[i - 1] + 1 if (i > 0 and sq[i]) else (1 if sq[i] else 0)

    fires = []
    for t in range(1, n):
        if sq[t - 1] and not sq[t]:                      # a mola soltou
            direction = "up" if mom[t] > 0 else "down"
            sign = 1 if direction == "up" else -1
            fwd = {"scored": False}
            for H in HORIZONS:
                if t + H < n and close[t]:
                    r = close[t + H] / close[t] - 1.0
                    fwd[f"r{H}"] = round(r * 100, 2)
                    fwd[f"s{H}"] = round(sign * r * 100, 2)
                else:
                    fwd[f"r{H}"] = fwd[f"s{H}"] = None
            fwd["scored"] = fwd["s20"] is not None
            # a volatilidade realmente expandiu? (largura de banda subiu em 10d)
            fwd["expanded"] = bool(t + 10 < n and bw[t + 10] > bw[t])
            fires.append(dict(
                i=int(t), dir=direction, days=int(run[t - 1]),
                bw_pct=(None if np.isnan(bw_pct[t - 1]) else round(float(bw_pct[t - 1]), 1)),
                date=dates[t], fwd=fwd))
    return dates, fires, run


def process(ticker, start, end, use_cache):
    df = load_ohlcv(ticker, start, end, use_cache=use_cache)
    if df is None or len(df) < 200:
        return None, None
    ind = compute_all(df)
    dates, fires, run = detect_and_eval(ind)
    n = len(dates)
    sq = ind["squeeze"].fillna(False).to_numpy(bool)

    # status atual
    if sq[-1]:
        state, days = "comprimido", int(run[-1])
    elif fires and fires[-1]["i"] >= n - FRESH_FIRE:
        state, days = "disparou", 0
    else:
        state, days = "normal", 0
    last_fire = fires[-1] if fires else None
    bwp = ind["bw_pct"].to_numpy(float)
    cur_bwp = None if np.isnan(bwp[-1]) else round(float(bwp[-1]), 1)

    panel = dict(
        dates=dates,
        close=_rs(ind["close"].to_numpy(), 2),
        basis=_rs(ind["basis"].to_numpy(), 2),
        bb_up=_rs(ind["bb_up"].to_numpy(), 2), bb_lo=_rs(ind["bb_lo"].to_numpy(), 2),
        kc_up=_rs(ind["kc_up"].to_numpy(), 2), kc_lo=_rs(ind["kc_lo"].to_numpy(), 2),
        bw=_rs(ind["bw"].to_numpy(), 2), bw_pct=_rs(bwp, 1),
        squeeze="".join("1" if x else "0" for x in sq),
        fires=fires,
    )
    screen = dict(
        ticker=ticker, name=ticker.replace(".SA", ""),
        last_price=round(float(ind["close"].iloc[-1]), 2), last_date=dates[-1],
        state=state, days=days, bw_pct=cur_bwp,
        last_dir=(last_fire["dir"] if last_fire else None),
        last_fire_date=(last_fire["date"] if last_fire else None),
        n_fires=len(fires),
    )
    return panel, screen


def aggregate(all_fires, base):
    """Poder preditivo por direção do disparo (só disparos avaliáveis)."""
    stats = {}
    for d in ("up", "down"):
        scored = [f for f in all_fires if f["dir"] == d and f["fwd"]["scored"]]
        row = {"n": len(scored), "hit": {}, "avg": {}, "edge": {}, "expand": None}
        if scored:
            sign = 1 if d == "up" else -1
            for H in HORIZONS:
                s = np.array([f["fwd"][f"s{H}"] for f in scored if f["fwd"][f"s{H}"] is not None])
                if len(s):
                    row["hit"][H] = round(float((s > 0).mean()) * 100, 1)
                    row["avg"][H] = round(float(s.mean()), 2)
                    row["edge"][H] = round(float(s.mean()) - sign * base[H], 2)
            exp = [f for f in scored if "expanded" in f["fwd"]]
            row["expand"] = round(np.mean([f["fwd"]["expanded"] for f in exp]) * 100, 1) if exp else None
        stats[d] = row
    return stats


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
    p = argparse.ArgumentParser(description="Screening de compressão de volatilidade.")
    p.add_argument("--tickers", default=str(HERE / "tickers.txt"))
    p.add_argument("--start", default=start_default)
    p.add_argument("--end", default=end_default)
    p.add_argument("--no-cache", action="store_true")
    args = p.parse_args(argv)

    tickers = read_tickers(args.tickers)
    log.info("Tickers: %s", ", ".join(tickers))
    data, order, all_fires = {}, [], []
    for t in tickers:
        log.info("Processando %s ...", t)
        panel, screen = process(t, args.start, args.end, use_cache=not args.no_cache)
        if panel is None:
            continue
        data[t] = panel
        data[t]["screen"] = screen
        order.append(t)
        all_fires.extend(panel["fires"])

    base = baseline([np.array(data[t]["close"], float) for t in order])
    # ordena: comprimidos primeiro, depois por menor percentil de largura de banda
    prio = {"comprimido": 0, "disparou": 1, "normal": 2}
    order.sort(key=lambda t: (prio[data[t]["screen"]["state"]],
                              data[t]["screen"]["bw_pct"] if data[t]["screen"]["bw_pct"] is not None else 999))

    payload = dict(
        meta=dict(start=args.start, end=args.end,
                  generated=datetime.today().strftime("%Y-%m-%d %H:%M"),
                  horizons=HORIZONS, baseline=base, fresh_fire=FRESH_FIRE),
        tickers=order,
        screen=[data[t]["screen"] for t in order],
        data={t: {k: v for k, v in data[t].items() if k != "screen"} for t in order},
    )
    build_site(payload)
    log.info("Pronto. %d ativos, %d disparos.", len(order), len(all_fires))


if __name__ == "__main__":
    main()
