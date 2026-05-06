"""
main.py
-------
Entry point for the market digest.  Called by GitHub Actions workflows.

Usage:
    python src/main.py --market us
    python src/main.py --market kr
    python src/main.py --market jp
    python src/main.py --market in

Environment variables (set as GitHub Secrets):
    TELEGRAM_BOT_TOKEN  — from @BotFather
    TELEGRAM_CHAT_ID    — target chat or channel ID
"""

import argparse
import logging
import os
import sys
from datetime import datetime

import pytz

# ── Local imports ────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
import fetcher
import screener
import formatter
import telegram_bot

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Market timezone mapping ──────────────────────────────────────────────────
MARKET_TZ = {
    "us": "America/New_York",
    "kr": "Asia/Seoul",
    "jp": "Asia/Tokyo",
    "in": "Asia/Kolkata",
}


def run(market: str, token: str, chat_id: str) -> None:
    tz = pytz.timezone(MARKET_TZ.get(market, "UTC"))
    session_date = datetime.now(tz).date()

    logger.info(f"═══════════════════════════════════════")
    logger.info(f"  Market: {market.upper()}  |  Date: {session_date}")
    logger.info(f"═══════════════════════════════════════")

    # ── 1. Ticker discovery ──────────────────────────────────────────────────
    logger.info("Step 1/5  Fetching ticker list…")
    tickers = fetcher.get_tickers(market)
    logger.info(f"  Total tickers: {len(tickers)}")
    if not tickers:
        logger.error("No tickers found — aborting.")
        sys.exit(1)

    # ── 2. OHLCV batch download ──────────────────────────────────────────────
    logger.info("Step 2/5  Downloading OHLCV data…")
    df = fetcher.batch_download(tickers, period="5d")
    if df.empty:
        logger.error("No OHLCV data returned — aborting.")
        sys.exit(1)

    # Keep only rows from the most recent trading session
    latest_date = df["date"].max()
    df = df[df["date"] == latest_date].copy()
    logger.info(f"  Session date resolved to: {latest_date}  ({len(df)} tickers with data)")

    # ── 3. Market cap enrichment ─────────────────────────────────────────────
    logger.info("Step 3/5  Fetching market caps…")
    df = fetcher.enrich_market_cap(df, limit=100)

    # ── 4. Options OI (US only) ──────────────────────────────────────────────
    oi_dict: dict = {}
    if market == "us":
        logger.info("Step 4/5  Fetching options open interest…")
        oi_dict = fetcher.fetch_options_oi(df, limit=300)
    else:
        logger.info("Step 4/5  Skipping options OI (US only)")

    # ── 5. Rank + format + send ──────────────────────────────────────────────
    logger.info("Step 5/5  Ranking, formatting, and sending…")

    df_volume  = screener.top_by_volume(df)
    df_gainers = screener.top_gainers(df)
    df_losers  = screener.top_losers(df)
    df_mktcap  = screener.top_by_market_cap(df)
    df_oi      = screener.top_by_options_oi(df, oi_dict)

    sections = formatter.build_all_sections(
        market=market,
        session_date=latest_date,
        ticker_count=len(df),
        df_volume=df_volume,
        df_gainers=df_gainers,
        df_losers=df_losers,
        df_mktcap=df_mktcap,
        df_oi=df_oi,
    )

    telegram_bot.send_digest(token, chat_id, sections)
    logger.info(f"  Sent {len(sections)} message section(s) to Telegram ✓")
    logger.info("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Market digest → Telegram")
    parser.add_argument(
        "--market",
        required=True,
        choices=["us", "kr", "jp", "in"],
        help="Which market to run",
    )
    args = parser.parse_args()

    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.error(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set as environment variables."
        )
        sys.exit(1)

    run(market=args.market, token=token, chat_id=chat_id)


if __name__ == "__main__":
    main()
