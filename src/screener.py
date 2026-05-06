"""
screener.py
-----------
Pure ranking functions that operate on a pandas DataFrame produced by fetcher.py.
Expected DataFrame columns: ticker, open, high, low, close, volume, pct_change, date
"""

import pandas as pd


def top_by_volume(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Top N tickers by trading volume (descending)."""
    return (
        df.dropna(subset=["volume"])
        .sort_values("volume", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )


def top_gainers(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Top N tickers by % change (highest positive first)."""
    return (
        df.dropna(subset=["pct_change"])
        .sort_values("pct_change", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )


def top_losers(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Top N tickers by % change (most negative first)."""
    return (
        df.dropna(subset=["pct_change"])
        .sort_values("pct_change", ascending=True)
        .head(n)
        .reset_index(drop=True)
    )


def top_by_market_cap(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Top N tickers by market cap (descending). Requires a 'market_cap' column."""
    if "market_cap" not in df.columns:
        return pd.DataFrame()
    return (
        df.dropna(subset=["market_cap"])
        .sort_values("market_cap", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )


def top_by_options_oi(df: pd.DataFrame, oi_dict: dict, n: int = 20) -> pd.DataFrame:
    """
    Merge options OI data (dict: {ticker -> total_oi}) into df and rank.
    Only meaningful for US markets.
    """
    if not oi_dict:
        return pd.DataFrame()
    oi_df = pd.DataFrame(list(oi_dict.items()), columns=["ticker", "options_oi"])
    merged = df.merge(oi_df, on="ticker", how="inner")
    return (
        merged.dropna(subset=["options_oi"])
        .sort_values("options_oi", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )
