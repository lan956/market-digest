"""
formatter.py
------------
Builds Telegram-ready HTML message sections from ranked DataFrames.
Each section is a self-contained string ≤ ~3800 chars (safe buffer below 4096).
"""

import pandas as pd
from datetime import date as Date

MARKET_META = {
    "us": {"flag": "🇺🇸", "label": "US Market",      "exchange": "NYSE + NASDAQ",    "currency": "$",  "currency_after": False},
    "kr": {"flag": "🇰🇷", "label": "Korean Market",   "exchange": "KOSPI + KOSDAQ",   "currency": "₩",  "currency_after": False},
    "jp": {"flag": "🇯🇵", "label": "Japanese Market", "exchange": "TSE (Nikkei 225)", "currency": "¥",  "currency_after": False},
    "in": {"flag": "🇮🇳", "label": "Indian Market",   "exchange": "NSE (NIFTY 500)",  "currency": "₹",  "currency_after": False},
}


def _fmt_volume(vol) -> str:
    try:
        v = float(vol)
        if v >= 1e9:
            return f"{v/1e9:.2f}B"
        if v >= 1e6:
            return f"{v/1e6:.2f}M"
        if v >= 1e3:
            return f"{v/1e3:.1f}K"
        return str(int(v))
    except Exception:
        return "—"


def _fmt_price(val, currency: str = "$", decimals: int = 2) -> str:
    """Format a price with the correct currency symbol. Auto-reduces decimals for large values."""
    try:
        v = float(val)
        # For KRW/JPY whole-number currencies, show 0 decimal places
        if currency in ("₩", "¥") or v >= 1000:
            return f"{currency}{v:,.0f}"
        return f"{currency}{v:,.{decimals}f}"
    except Exception:
        return "—"


def _fmt_cap(cap, currency: str = "$") -> str:
    try:
        v = float(cap)
        if v >= 1e12:
            return f"{currency}{v/1e12:.2f}T"
        if v >= 1e9:
            return f"{currency}{v/1e9:.2f}B"
        if v >= 1e6:
            return f"{currency}{v/1e6:.2f}M"
        return f"{currency}{v:,.0f}"
    except Exception:
        return "—"


def _pct_str(pct) -> str:
    try:
        p = float(pct)
        arrow = "▲" if p >= 0 else "▼"
        sign = "+" if p >= 0 else ""
        return f"{arrow} {sign}{p:.2f}%"
    except Exception:
        return "—"


def _divider(title: str) -> str:
    return f"\n<b>{'─' * 22}</b>\n<b>{title}</b>\n<b>{'─' * 22}</b>\n"


def build_header(market: str, session_date: Date, ticker_count: int) -> str:
    meta = MARKET_META.get(market, {"flag": "📊", "label": market.upper(), "exchange": ""})
    return (
        f"{meta['flag']} <b>{meta['label']} Daily Digest</b>\n"
        f"📅 {session_date.strftime('%A, %b %d, %Y')}\n"
        f"<i>{meta['exchange']} — {ticker_count:,} stocks analyzed</i>"
    )


NAME_MAX = 16   # max chars for company name display


def _name(ticker: str, names: dict) -> str:
    """Return truncated company name, or empty string if not available."""
    n = names.get(ticker, "")
    if not n or n == ticker:
        return ""
    return n[:NAME_MAX].strip()


def build_volume_section(df: pd.DataFrame, names: dict, currency: str = "$") -> str:
    if df.empty:
        return ""
    lines = [_divider("📦  TOP 20 BY VOLUME")]
    for i, row in df.iterrows():
        pct = _pct_str(row.get("pct_change"))
        vol = _fmt_volume(row.get("volume"))
        close = _fmt_price(row.get("close"), currency)
        name = _name(row["ticker"], names)
        name_str = f"  <i>{name}</i>" if name else ""
        lines.append(
            f"<code>{i+1:>2}.</code> <b>{row['ticker']}</b>{name_str}\n"
            f"     {close}  {pct}  Vol: {vol}"
        )
    return "\n".join(lines)


def build_gainers_section(df: pd.DataFrame, names: dict, currency: str = "$") -> str:
    if df.empty:
        return ""
    lines = [_divider("📈  TOP 20 GAINERS")]
    for i, row in df.iterrows():
        pct = _pct_str(row.get("pct_change"))
        vol = _fmt_volume(row.get("volume"))
        close = _fmt_price(row.get("close"), currency)
        name = _name(row["ticker"], names)
        name_str = f"  <i>{name}</i>" if name else ""
        lines.append(
            f"<code>{i+1:>2}.</code> <b>{row['ticker']}</b>{name_str}\n"
            f"     {close}  <b>{pct}</b>  Vol: {vol}"
        )
    return "\n".join(lines)


def build_losers_section(df: pd.DataFrame, names: dict, currency: str = "$") -> str:
    if df.empty:
        return ""
    lines = [_divider("📉  TOP 20 LOSERS")]
    for i, row in df.iterrows():
        pct = _pct_str(row.get("pct_change"))
        vol = _fmt_volume(row.get("volume"))
        close = _fmt_price(row.get("close"), currency)
        name = _name(row["ticker"], names)
        name_str = f"  <i>{name}</i>" if name else ""
        lines.append(
            f"<code>{i+1:>2}.</code> <b>{row['ticker']}</b>{name_str}\n"
            f"     {close}  <b>{pct}</b>  Vol: {vol}"
        )
    return "\n".join(lines)


def build_mktcap_section(df: pd.DataFrame, names: dict, currency: str = "$") -> str:
    if df.empty:
        return ""
    lines = [_divider("💰  TOP 20 BY MARKET CAP")]
    for i, row in df.iterrows():
        cap = _fmt_cap(row.get("market_cap"), currency)
        pct = _pct_str(row.get("pct_change"))
        close = _fmt_price(row.get("close"), currency)
        name = _name(row["ticker"], names)
        name_str = f"  <i>{name}</i>" if name else ""
        lines.append(
            f"<code>{i+1:>2}.</code> <b>{row['ticker']}</b>{name_str}\n"
            f"     {close}  {pct}  Cap: {cap}"
        )
    return "\n".join(lines)


def build_oi_section(df: pd.DataFrame, names: dict, currency: str = "$") -> str:
    if df.empty:
        return ""
    lines = [_divider("⚡  TOP 20 OPTIONS OPEN INTEREST  (US only)")]
    for i, row in df.iterrows():
        oi = _fmt_volume(row.get("options_oi"))
        pct = _pct_str(row.get("pct_change"))
        close = _fmt_price(row.get("close"), currency)
        name = _name(row["ticker"], names)
        name_str = f"  <i>{name}</i>" if name else ""
        lines.append(
            f"<code>{i+1:>2}.</code> <b>{row['ticker']}</b>{name_str}\n"
            f"     {close}  {pct}  OI: {oi}"
        )
    return "\n".join(lines)


def build_all_sections(
    market: str,
    session_date: Date,
    ticker_count: int,
    df_volume: pd.DataFrame,
    df_gainers: pd.DataFrame,
    df_losers: pd.DataFrame,
    df_mktcap: pd.DataFrame,
    df_oi: pd.DataFrame,
    names: dict | None = None,
) -> list[str]:
    """
    Returns a list of Telegram message strings, one per section.
    """
    if names is None:
        names = {}
    currency = MARKET_META.get(market, {}).get("currency", "$")
    header = build_header(market, session_date, ticker_count)
    sections = [
        header,
        build_volume_section(df_volume, names, currency),
        build_gainers_section(df_gainers, names, currency),
        build_losers_section(df_losers, names, currency),
        build_mktcap_section(df_mktcap, names, currency),
        build_oi_section(df_oi, names, currency),
    ]
    return [s for s in sections if s.strip()]

