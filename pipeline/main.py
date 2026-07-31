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


def process(ticker, start, end, use_cache):
    df = load_ohlcv(ticker, start, end, use_cache=use_cache)
    if df is None or len(df) < 260:
        return None, None
    ind = compute_all(df)
    setups = detect_vcp(ind, order=ORDER)
    dates = [d.strftime("%Y-%m-%d") for d in ind.index]
    n = len(dates)
    close = ind["close"].to_numpy(float)
    for s in setups:
        s["base_date"] = dates[s["highs"][0]]
        s["pivot_date"] = dates[s["pivot_i"]]
        s["brk_date"] = dates[s["brk_i"]] if s["brk_i"] is not None else None
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
    live = next((s for s in reversed(setups) if s["status"] == "em_formacao"), None)
    recent = next((s for s in reversed(setups) if s["status"] == "rompeu" and s["brk_i"] >= n - 10), None)
    if live:
        state = "em_formacao"; ref = live
    elif recent:
        state = "rompeu"; ref = recent
    else:
        state = "nenhum"; ref = None

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
    screen = dict(
        ticker=ticker, name=ticker.replace(".SA", ""),
        last_price=round(float(close[-1]), 2), last_date=dates[-1],
        state=state, stage2=bool(ind["stage2"].iloc[-1]),
        n_contractions=(ref["n_contractions"] if ref else None),
        depths=(ref["depths"] if ref else None),
        last_depth=(ref["depths"][-1] if ref else None),
        pivot=(ref["pivot"] if ref else None),
        dist_pivot=(round((ref["pivot"] / float(close[-1]) - 1) * 100, 2) if ref else None),
        n_setups=len(setups),
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

    tickers = read_tickers(args.tickers)
    log.info("Tickers: %s", ", ".join(tickers))
    data, order = {}, []
    for t in tickers:
        log.info("Processando %s ...", t)
        panel, screen = process(t, args.start, args.end, use_cache=not args.no_cache)
        if panel is None:
            continue
        panel["screen"] = screen
        data[t] = panel
        order.append(t)

    base = baseline([np.array(data[t]["close"], float) for t in order])
    prio = {"em_formacao": 0, "rompeu": 1, "nenhum": 2}
    order.sort(key=lambda t: (prio[data[t]["screen"]["state"]],
                              data[t]["screen"]["dist_pivot"] if data[t]["screen"]["dist_pivot"] is not None else 999))

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
