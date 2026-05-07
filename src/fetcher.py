"""
fetcher.py
----------
Handles ticker discovery and OHLCV / market-cap / options-OI data fetching.

Markets:
  US  — All NYSE + NASDAQ tickers via NASDAQ Trader FTP (HTTP), SEC EDGAR fallback
  JP  — Nikkei 225 via Wikipedia (requests + UA header), hardcoded fallback
  KR  — KOSPI + KOSDAQ via KRX public data portal, hardcoded fallback
  IN  — NIFTY 500 via NSE archives CSV, hardcoded fallback

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
    """
    Fetch all NYSE + NASDAQ listed tickers.

    Sources tried in order:
      1. NASDAQ Trader FTP (HTTP — this server does NOT support HTTPS)
      2. SEC EDGAR company tickers (HTTPS fallback, ~10k companies)
      3. Hardcoded S&P 500 + NASDAQ 100 (last resort)
    """
    tickers: set[str] = set()

    # ── Source 1: NASDAQ Trader FTP (must be HTTP, not HTTPS) ────────────────
    NASDAQ_SOURCES = {
        "nasdaq": "http://ftp.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
        "other":  "http://ftp.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
    }
    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MarketDigest/1.0)"}

    for name, url in NASDAQ_SOURCES.items():
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            df = pd.read_csv(StringIO(r.text), sep="|")
            df = df.iloc[:-1]  # last row is file-creation metadata
            sym_col = "Symbol" if "Symbol" in df.columns else "ACT Symbol"
            if "Test Issue" in df.columns:
                df = df[df["Test Issue"] == "N"]
            syms = df[sym_col].dropna().astype(str).str.strip()
            syms = syms[syms.str.match(r"^[A-Z]{1,5}$")]
            tickers.update(syms.tolist())
            logger.info(f"  US {name}: {len(syms)} tickers loaded from NASDAQ FTP")
        except Exception as e:
            logger.error(f"  NASDAQ FTP failed for {name}: {e}")

    if tickers:
        return sorted(tickers)

    # ── Source 2: SEC EDGAR (HTTPS, always available) ────────────────────────
    logger.warning("NASDAQ FTP unavailable — trying SEC EDGAR...")
    try:
        r = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": "MarketDigest/1.0 contact@example.com"},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        syms = [v["ticker"] for v in data.values() if isinstance(v.get("ticker"), str)]
        syms = [s.strip() for s in syms if s.strip() and s.strip().isalpha() and len(s) <= 5]
        tickers.update(s.upper() for s in syms)
        logger.info(f"  US: {len(tickers)} tickers loaded from SEC EDGAR")
    except Exception as e:
        logger.error(f"  SEC EDGAR failed: {e}")

    if tickers:
        return sorted(tickers)

    # ── Source 3: Hardcoded S&P 500 + NASDAQ 100 ────────────────────────────
    logger.warning("All live sources failed — using hardcoded S&P 500 + NASDAQ 100 fallback")
    SP500_NDX100 = [
        # Mega cap / NASDAQ 100 core
        "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","TSLA","AVGO","COST",
        "NFLX","AMD","ADBE","QCOM","INTC","AMAT","MU","LRCX","KLAC","MRVL",
        "PANW","CRWD","SNPS","CDNS","FTNT","ORLY","PAYX","CTAS","FAST","BIIB",
        "GILD","VRTX","REGN","IDXX","ILMN","DXCM","ALGN","MRNA","ISRG","SGEN",
        "TEAM","ZS","OKTA","DDOG","NET","SNOW","ABNB","UBER","LYFT","DASH",
        # S&P 500 large caps
        "BRK-B","LLY","JPM","V","UNH","XOM","JNJ","PG","MA","HD",
        "CVX","MRK","ABBV","BAC","PFE","KO","PEP","TMO","CSCO","ACN",
        "ABT","WMT","MCD","CRM","TXN","DHR","NEE","PM","RTX","HON",
        "UPS","SPGI","LOW","GS","IBM","BLK","CAT","SYK","AXP","INTU",
        "ELV","CVS","MDT","ADP","BKNG","GILD","TJX","CI","NOW","ANET",
        "DE","MMC","ZTS","PLD","AMT","BDX","AON","ITW","MCO","EQIX",
        "DUK","SO","AEP","EXC","D","SRE","WEC","ES","ETR","XEL",
        "GE","MMM","EMR","ROK","PH","CMI","IR","ETN","DOV","AME",
        "FCX","NEM","GOLD","AA","CLF","X","NUE","STLD","RS","ATI",
        "WFC","C","MS","USB","PNC","TFC","COF","AIG","MET","PRU",
        "SPG","PSA","WELL","DLR","O","AVB","EQR","MAA","UDR","CPT",
        "LIN","APD","ECL","SHW","PPG","IFF","EMN","CE","DD","DOW",
        "UNP","CSX","NSC","KSU","CP","CNI","FDX","GD","LMT","NOC",
        "BA","HII","TDG","HEI","LDOS","SAIC","BAX","BIO","A","WAT",
        "DIS","CMCSA","CHTR","PARA","FOX","FOXA","WBD","NWSA","NYT","OMC",
        "T","VZ","TMUS","LUMN","FYBR","WBD","SIRI","DISH","ATUS","LBRDK",
        "TGT","DLTR","DG","KR","ACI","SFM","FIVE","ULTA","BBY","GPS",
        "NKE","VFC","PVH","RL","TPR","HBI","UA","UAA","LEVI","SKX",
        "CAR","HTZ","ABNB","H","HLT","MAR","WH","IHG","RCL","CCL",
        "MO","BTI","PM","SWMAY","VGR","STZ","TAP","BUD","SAM","BOOT",
        "SQ","PYPL","MA","V","FIS","FI","GPN","ADP","PAYX","WEX",
        "GOLD","GLD","SLV","IAU","GDX","GDXJ","RING","SIL","SILJ","PSLV",
    ]
    return sorted(set(SP500_NDX100))


def get_jp_tickers() -> list[str]:
    """
    Scrape Nikkei 225 constituents from Wikipedia.
    Uses requests + User-Agent header first (pd.read_html sends no UA and gets 403).
    Falls back to full hardcoded Nikkei 225 list if scrape fails.
    """
    url = "https://en.wikipedia.org/wiki/Nikkei_225"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        tables = pd.read_html(StringIO(r.text), attrs={"class": "wikitable"})
        for df in tables:
            cols = [c.lower() for c in df.columns]
            code_col = next((df.columns[i] for i, c in enumerate(cols) if "code" in c), None)
            if code_col is None:
                continue
            codes = df[code_col].dropna().astype(str).str.strip().str.zfill(4)
            codes = codes[codes.str.match(r"^\d{4}$")]
            if len(codes) < 100:   # sanity check — N225 has 225 entries
                continue
            tickers = [f"{c}.T" for c in codes]
            logger.info(f"  JP: {len(tickers)} tickers loaded from Wikipedia")
            return tickers
    except Exception as e:
        logger.error(f"Failed to fetch JP tickers from Wikipedia: {e}")

    # Full Nikkei 225 hardcoded fallback (as of 2024-Q4, minus known delisted)
    FALLBACK = [
        "1332","1333","1605","1721","1801","1802","1803","1808","1812","1925",
        "1928","1963","2002","2269","2282","2413","2432","2502","2503","2531",
        "2578","2579","2593","2695","2768","2801","2802","2871","2914","3086",
        "3092","3099","3289","3382","3401","3402","3407","3436","3659","3861",
        "3863","4004","4005","4021","4042","4043","4061","4063","4151","4183",
        "4188","4208","4307","4324","4452","4503","4507","4519","4523","4543",
        "4568","4578","4661","4689","4704","4751","4755","4901","4911","5020",
        "5101","5108","5201","5202","5214","5232","5233","5301","5332","5333",
        "5401","5406","5411","5541","5631","5703","5706","5711","5713","5714",
        "5801","5802","5803","5901","6098","6103","6113","6146","6178","6273",
        "6301","6302","6305","6326","6361","6367","6376","6448","6471","6472",
        "6473","6501","6504","6506","6532","6594","6645","6674","6702","6703",
        "6723","6724","6752","6753","6754","6758","6762","6770","6857","6861",
        "6902","6952","6954","6963","6971","6976","6981","7003","7004","7011",
        "7012","7013","7186","7201","7202","7203","7205","7211","7261","7267",
        "7269","7270","7272","7731","7733","7735","7741","7751","7752","7762",
        "7832","7911","7912","7951","7974","8001","8002","8003","8011","8015",
        "8031","8035","8053","8058","8233","8267","8306","8308","8309","8316",
        "8331","8354","8358","8411","8591","8601","8604","8630","8725","8750",
        "8766","8795","8801","8802","8804","8830","9001","9005","9007","9008",
        "9009","9020","9021","9022","9064","9101","9104","9107","9147","9202",
        "9301","9432","9433","9501","9502","9503","9531","9532","9602","9984",
    ]
    logger.warning(f"Using JP hardcoded fallback ({len(FALLBACK)} tickers)")
    return [f"{c}.T" for c in FALLBACK]


def get_kr_tickers() -> list[str]:
    """
    Fetch KOSPI + KOSDAQ tickers from the KRX public data portal (no login required).
    Uses POST requests to data.krx.co.kr — same source as the KRX website.
    Falls back to a hardcoded KOSPI 200 + KOSDAQ 150 list on failure.
    """
    KRX_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Referer": "https://data.krx.co.kr/",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    # mktId: STK = KOSPI, KSQ = KOSDAQ
    MARKETS = [("STK", ".KS"), ("KSQ", ".KQ")]
    all_tickers: list[str] = []

    for mkt_id, suffix in MARKETS:
        try:
            payload = {
                "bld": "dbms/MDC/STAT/standard/MDCSTAT01901",
                "locale": "en_US",
                "mktId": mkt_id,
                "segTpCd": "ALL",
                "share": "1",
                "money": "1",
                "csvxls_isNo": "false",
            }
            r = requests.post(KRX_URL, data=payload, headers=HEADERS, timeout=20)
            r.raise_for_status()
            data = r.json()
            # Response schema: {"OutBlock_1": [{"ISU_SRT_CD": "005930", ...}, ...]}
            rows = data.get("OutBlock_1", [])
            codes = [row["ISU_SRT_CD"].strip() for row in rows if "ISU_SRT_CD" in row]
            codes = [c for c in codes if c.isdigit() and len(c) == 6]
            all_tickers.extend([f"{c}{suffix}" for c in codes])
            logger.info(f"  KR {mkt_id}: {len(codes)} tickers loaded from KRX portal")
        except Exception as e:
            logger.error(f"  KRX portal failed for {mkt_id}: {e}")

    if all_tickers:
        return all_tickers

    # ── Comprehensive hardcoded fallback: KOSPI 200 + KOSDAQ 150 ─────────────
    logger.warning("Using KR hardcoded fallback (KRX portal unavailable)")
    KOSPI = [
        # Tech / semiconductors
        "005930","000660","035420","066570","009150","034220","000990","010130",
        "011070","042700","036570","047050","078935","079550","267260","240810",
        # Autos
        "005380","012330","000270","204320","007070","023810","005385","005387",
        # Financials
        "105560","055550","086790","024110","316140","175330","138930","015020",
        "032830","006800","039490","071050","003540","001045","001040","000810",
        # Energy / chemicals
        "051910","096770","011170","010950","006360","003670","011790","002380",
        "006400","047810","010060","004020","003520","011000","002710","025210",
        # Industrials / construction
        "034730","028260","000880","009830","047040","002380","001740","003690",
        "000720","008770","047050","001570","003160","014820","108670","018880",
        # Consumer / retail
        "139480","004170","271560","033780","000100","005300","097950","068400",
        "004990","003000","007310","008930","002240","004000","033530","145990",
        # Healthcare / bio
        "068270","207940","326030","128940","051900","000400","009420","006650",
        "185750","086280","003550","017670","032640","030200","017810","036460",
        # Telecom / media
        "030200","017670","032640","036490","053210","064350","035720","122870",
        # Steel / materials
        "005490","004020","010140","001060","000670","007310","004380","078930",
        # Shipping / logistics
        "011200","000120","001120","003490","006260","044820","117930","000100",
    ]
    KOSDAQ = [
        # Top KOSDAQ by market cap
        "247540","086520","041510","196170","112040","263750","009420","035760",
        "078340","091990","095340","095660","102940","145720","145210","187790",
        "214150","214370","226950","236810","251270","253450","263720","267270",
        "272210","285130","293490","298020","298380","302440","305090","314930",
        "322510","323990","336370","340570","347860","352820","357780","363260",
        "365550","370870","375500","377300","383310","389260","389270","393890",
        "394280","402340","403870","405640","406820","412500","418420","421190",
        "437080","443670","449740","950130","950140","950160","950180","950200",
        "033290","041190","041830","042040","042600","045060","048410","053800",
        "054040","058470","060280","060980","064760","067310","067630","068760",
        "069080","070900","073240","073490","074600","075130","078130","079160",
        "080220","083790","086040","086450","088790","091580","095500","096530",
        "099190","102120","107640","108490","112290","115440","119860","121600",
        "122310","122450","122780","123260","124370","126340","128940","131100",
        "131370","133750","138580","140410","141080","141080","143160","145020",
    ]
    # Deduplicate
    kospi_tickers  = list(dict.fromkeys([f"{c}.KS" for c in KOSPI]))
    kosdaq_tickers = list(dict.fromkeys([f"{c}.KQ" for c in KOSDAQ]))
    return kospi_tickers + kosdaq_tickers


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


# ─────────────────────────────────────────────
# COMPANY NAME LOOKUP
# ─────────────────────────────────────────────

def fetch_names(tickers: list[str]) -> dict[str, str]:
    """
    Fetch shortName for a small list of tickers (typically <= 100).
    Called only on the final ranked tickers, not the full universe.
    Returns dict {ticker: display_name}.
    """
    logger.info(f"  Fetching company names for {len(tickers)} tickers...")
    names: dict[str, str] = {}
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            name = (
                info.get("shortName")
                or info.get("longName")
                or ticker
            )
            # Trim common noisy suffixes for cleaner display
            for suffix in [
                " Co., Ltd.", " Co.,Ltd.", " Corporation", " Corp.",
                " Inc.", " Ltd.", " Co.", " Holdings", " Group",
                " Kabushiki Kaisha", " K.K.",
            ]:
                name = name.replace(suffix, "")
            names[ticker] = name.strip()
            time.sleep(0.1)
        except Exception:
            names[ticker] = ticker
    logger.info(f"  Names fetched: {len(names)}")
    return names
