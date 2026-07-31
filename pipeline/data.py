"""Download e cache de dados OHLCV via yfinance (preços ajustados)."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent.parent
CACHE = HERE / "cache"

log = logging.getLogger(__name__)


def read_tickers(path: str | Path) -> list[str]:
    """Lê tickers.txt (um por linha, '#' comenta)."""
    out: list[str] = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def load_ohlcv(ticker: str, start: str, end: str,
               use_cache: bool = True) -> pd.DataFrame | None:
    """Retorna OHLCV diário (open, high, low, close, volume) com preços
    AJUSTADOS (auto_adjust=True) para lidar com splits/dividendos.

    Cacheia em parquet. Retorna None se o ticker não existir / sem dados.
    """
    CACHE.mkdir(exist_ok=True)
    cache_file = CACHE / f"{ticker}.parquet"

    if use_cache and cache_file.exists():
        try:
            df = pd.read_parquet(cache_file)
            if not df.empty:
                return df
        except Exception as exc:
            log.warning("Cache inválido para %s (%s); rebaixando.", ticker, exc)

    try:
        raw = yf.download(ticker, start=start, end=end, auto_adjust=True,
                          progress=False, threads=False)
    except Exception as exc:
        log.error("Falha ao baixar %s: %s", ticker, exc)
        return None

    if raw is None or raw.empty:
        log.error("Sem dados para %s (ticker inexistente ou sem histórico).", ticker)
        return None

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = raw.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    df = df.dropna(subset=["close"])
    if df.empty:
        log.error("Dados vazios após limpeza para %s.", ticker)
        return None

    df.to_parquet(cache_file)
    return df
