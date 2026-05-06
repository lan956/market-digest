"""
fetcher.py
----------
Handles ticker discovery and OHLCV / market-cap / options-OI data fetching.

Markets:
  US  — All NYSE + NASDAQ tickers via NASDAQ Trader FTP (~7,000–8,000 symbols)
  JP  — Nikkei 225 via Wikipedia table, .T suffix
  KR  — KOSPI + KOSDAQ via pykrx library, .KS / .KQ suffix
  IN  — NIFTY 500 via NSE archives CSV, .NS suffix

Notes:
  - Options OI is US-only (Yahoo Finance has limited Asian options data).
  - Market cap is fetched only for the top-N-by-volume stocks to save time.
  - yfinance batch downloads in chunks of CHUNK_SIZE to avoid rate-limit errors.
"""

import time
import logging
from io import StringIO

import requests
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

CHUNK_SIZE = 200          # tickers per yfinance batch call
OI_CANDIDATE_LIMIT = 300  # fetch options OI for the top-N-by-volume stocks only
MKTCAP_LIMIT = 100        # fetch market cap for top-N-by-volume stocks


# ─────────────────────────────────────────────
# TICKER DISCOVERY
# ─────────────────────────────────────────────

def get_us_tickers() -> list[str]:
    """Fetch all NYSE + NASDAQ listed tickers from NASDAQ Trader FTP."""
    tickers: set[str] = set()
    sources = {
        "nasdaq": "https://ftp.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
        "other":  "https://ftp.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
    }
    for name, url in sources.items():
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            df = pd.read_csv(StringIO(r.text), sep="|")
            df = df.iloc[:-1]  # last row is file-creation metadata

            sym_col = "Symbol" if "Symbol" in df.columns else "ACT Symbol"

            # Drop test issues (warrants, when-issued, etc.)
            if "Test Issue" in df.columns:
                df = df[df["Test Issue"] == "N"]

            syms = (
                df[sym_col]
                .dropna()
                .astype(str)
                .str.strip()
            )
            # Keep only clean alphabetic symbols (1–5 chars); drop ETNs/warrants/units
            syms = syms[syms.str.match(r"^[A-Z]{1,5}$")]
            tickers.update(syms.tolist())
            logger.info(f"  {name}: {len(syms)} tickers loaded")
        except Exception as e:
            logger.error(f"Failed to fetch {name} tickers: {e}")

    return sorted(tickers)


def get_jp_tickers() -> list[str]:
    """Scrape Nikkei 225 constituents from Wikipedia and append .T suffix."""
    url = "https://en.wikipedia.org/wiki/Nikkei_225"
    try:
        tables = pd.read_html(url, attrs={"class": "wikitable"})
        for df in tables:
            cols = [c.lower() for c in df.columns]
            code_col = next((df.columns[i] for i, c in enumerate(cols) if "code" in c), None)
            if code_col is None:
                continue
            codes = df[code_col].dropna().astype(str).str.strip().str.zfill(4)
            codes = codes[codes.str.match(r"^\d{4}$")]
            tickers = [f"{c}.T" for c in codes]
            logger.info(f"  JP: {len(tickers)} tickers loaded")
            return tickers
    except Exception as e:
        logger.error(f"Failed to fetch JP tickers: {e}")

    # Fallback: hardcoded Nikkei 225 sample (top 50 by weight)
    FALLBACK = [
        "7203","9984","6758","8306","6861","6954","4063","7974","9432","8035",
        "9433","9984","6502","4523","8316","2914","4661","6367","5108","8802",
        "4503","7267","9022","8411","4568","6301","1925","6501","4452","8001",
        "7751","2802","7741","3382","4901","7269","6702","5401","6857","8830",
        "7733","4543","9020","9009","2503","4507","6770","7735","9613","3659",
    ]
    logger.warning("Using JP fallback ticker list (Wikipedia scrape failed)")
    return [f"{c}.T" for c in FALLBACK]


def get_kr_tickers() -> list[str]:
    """Fetch KOSPI + KOSDAQ tickers via pykrx. Appends .KS / .KQ suffix."""
    try:
        from pykrx import stock  # type: ignore
        kospi  = stock.get_market_ticker_list(market="KOSPI")
        kosdaq = stock.get_market_ticker_list(market="KOSDAQ")
        tickers = [f"{t}.KS" for t in kospi] + [f"{t}.KQ" for t in kosdaq]
        logger.info(f"  KR: {len(tickers)} tickers loaded via pykrx")
        return tickers
    except Exception as e:
        logger.error(f"pykrx failed: {e}")

    # Fallback: KOSPI 200 major tickers
    FALLBACK_KS = [
        "005930","000660","035420","005380","051910","068270","035720","003550",
        "028260","096770","017670","000270","012330","009150","018260","011200",
        "034730","032830","086790","033780","015760","000810","010130","055550",
        "316140","024110","003490","010950","034020","011070",
    ]
    logger.warning("Using KR fallback ticker list (pykrx failed)")
    return [f"{t}.KS" for t in FALLBACK_KS]


def get_in_tickers() -> list[str]:
    """Fetch NIFTY 500 tickers from NSE archives. Appends .NS suffix."""
    url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MarketDigest/1.0)"}
    try:
        r = requests.get(url, timeout=30, headers=headers)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        syms = df["Symbol"].dropna().astype(str).str.strip()
        tickers = [f"{s}.NS" for s in syms]
        logger.info(f"  IN: {len(tickers)} tickers loaded")
        return tickers
    except Exception as e:
        logger.error(f"Failed to fetch IN tickers: {e}")

    # Fallback: NIFTY 50 major tickers
    FALLBACK_NS = [
        "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","ITC","KOTAKBANK",
        "LT","AXISBANK","SBIN","BAJFINANCE","BHARTIARTL","ASIANPAINT","MARUTI",
        "TITAN","WIPRO","ULTRACEMCO","NESTLEIND","POWERGRID","TECHM","HCLTECH",
        "SUNPHARMA","M&M","JSWSTEEL","TATASTEEL","NTPC","ONGC","COALINDIA","ADANIENT",
    ]
    logger.warning("Using IN fallback ticker list (NSE fetch failed)")
    return [f"{t}.NS" for t in FALLBACK_NS]


def get_tickers(market: str) -> list[str]:
    dispatch = {"us": get_us_tickers, "jp": get_jp_tickers, "kr": get_kr_tickers, "in": get_in_tickers}
    fn = dispatch.get(market)
    if not fn:
        raise ValueError(f"Unknown market: {market}")
    return fn()


# ─────────────────────────────────────────────
# OHLCV BATCH DOWNLOAD
# ─────────────────────────────────────────────

def batch_download(tickers: list[str], period: str = "5d") -> pd.DataFrame:
    """
    Download OHLCV for all tickers in chunks.
    Returns a flat DataFrame:
      ticker | open | high | low | close | volume | pct_change | date
    """
    rows: list[dict] = []
    total_chunks = (len(tickers) + CHUNK_SIZE - 1) // CHUNK_SIZE

    for chunk_idx in range(0, len(tickers), CHUNK_SIZE):
        chunk = tickers[chunk_idx : chunk_idx + CHUNK_SIZE]
        chunk_num = chunk_idx // CHUNK_SIZE + 1
        logger.info(f"  Downloading chunk {chunk_num}/{total_chunks} ({len(chunk)} tickers)…")
        try:
            raw = yf.download(
                chunk,
                period=period,
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
            )

            for ticker in chunk:
                try:
                    # yfinance returns MultiIndex if multiple tickers, flat if single
                    df_t = raw[ticker] if len(chunk) > 1 else raw
                    df_t = df_t.dropna(subset=["Close"])
                    if len(df_t) < 2:
                        continue

                    last = df_t.iloc[-1]
                    prev = df_t.iloc[-2]
                    pct = ((last["Close"] - prev["Close"]) / prev["Close"]) * 100

                    rows.append({
                        "ticker":     ticker,
                        "open":       round(float(last["Open"]), 4),
                        "high":       round(float(last["High"]), 4),
                        "low":        round(float(last["Low"]), 4),
                        "close":      round(float(last["Close"]), 4),
                        "volume":     float(last["Volume"]),
                        "pct_change": round(float(pct), 2),
                        "date":       df_t.index[-1].date(),
                    })
                except Exception:
                    continue  # skip individual ticker errors silently

        except Exception as e:
            logger.error(f"Chunk {chunk_num} download error: {e}")

        time.sleep(0.5)  # polite rate limiting

    logger.info(f"  Downloaded {len(rows)} tickers successfully")
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────
# MARKET CAP ENRICHMENT
# ─────────────────────────────────────────────

def enrich_market_cap(df: pd.DataFrame, limit: int = MKTCAP_LIMIT) -> pd.DataFrame:
    """
    Fetch market cap for the top-`limit` tickers by volume and merge into df.
    Adds a 'market_cap' column.
    """
    candidates = (
        df.sort_values("volume", ascending=False)
        .head(limit)["ticker"]
        .tolist()
    )
    logger.info(f"  Fetching market cap for {len(candidates)} candidates…")
    caps: dict[str, float | None] = {}

    for ticker in candidates:
        try:
            fi = yf.Ticker(ticker).fast_info
            caps[ticker] = getattr(fi, "market_cap", None)
            time.sleep(0.15)
        except Exception:
            caps[ticker] = None

    cap_df = pd.DataFrame(list(caps.items()), columns=["ticker", "market_cap"])
    return df.merge(cap_df, on="ticker", how="left")


# ─────────────────────────────────────────────
# OPTIONS OPEN INTEREST  (US only)
# ─────────────────────────────────────────────

def fetch_options_oi(df: pd.DataFrame, limit: int = OI_CANDIDATE_LIMIT) -> dict[str, int]:
    """
    For the top-`limit` stocks by volume, fetch options open interest
    (calls + puts, nearest 3 expiries) and return a dict {ticker: total_oi}.
    US market only — Yahoo Finance options data is sparse for Asian markets.
    """
    candidates = (
        df.sort_values("volume", ascending=False)
        .head(limit)["ticker"]
        .tolist()
    )
    logger.info(f"  Fetching options OI for {len(candidates)} candidates…")
    oi_data: dict[str, int] = {}

    for ticker in candidates:
        try:
            t = yf.Ticker(ticker)
            expirations = t.options  # list of expiry date strings
            if not expirations:
                continue
            total_oi = 0
            for exp in expirations[:3]:  # nearest 3 expiries only
                try:
                    chain = t.option_chain(exp)
                    total_oi += int(chain.calls["openInterest"].fillna(0).sum())
                    total_oi += int(chain.puts["openInterest"].fillna(0).sum())
                except Exception:
                    continue
            if total_oi > 0:
                oi_data[ticker] = total_oi
            time.sleep(0.25)
        except Exception:
            continue

    logger.info(f"  Options OI fetched for {len(oi_data)} tickers")
    return oi_data
