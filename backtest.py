"""The idea of back testing is to determine if the strategy of buying x stock following an insider trading (Purchase-only) event
yields a positive return """

from __future__ import annotations
import numpy as np
import pandas as pd
from event_study import load_events_from_r2, load_prices_from_r2
from storage import write_parquet, upload_to_r2

HOLDING_DAYS = 20  # best time window as far as significance
MAX_FILING_LAG_DAYS = 5                            
MIN_PURCHASE_VALUE = 0.0

DEDUP_KEYS = ["join_ticker", "filing_date", "transaction_code", "transaction_acquired_disposed_code","transaction_price_per_share", "transaction_shares"]


def prepare_prices(prices_df: pd.DataFrame) -> pd.DataFrame:
    """Clean price data for backtesting"""
    df = prices_df.copy()

    if "ticker" not in df.columns:
        if "join_ticker" in df.columns:
            df["ticker"] = df["join_ticker"]
        elif "issuer_ticker" in df.columns:
            df["ticker"] = df["issuer_ticker"]
        else:
            raise ValueError("prices_df needs ticker, join_ticker, or issuer_ticker column")

    required_columns = ["ticker", "date", "adjClose"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required price columns: {missing_columns}")

    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["adjClose"] = pd.to_numeric(df["adjClose"], errors="coerce")

    df = df.dropna(subset=["ticker", "date", "adjClose"])
    df = df[df["adjClose"] > 0]
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)

    return df


def get_clean_purchase_signals(events_df: pd.DataFrame, min_purchase_value: float = MIN_PURCHASE_VALUE,
                                max_filing_lag_days: int = MAX_FILING_LAG_DAYS, cluster_threshold: int = 3) -> pd.DataFrame:
    """Create one insider purchase signal per ticker/filing date"""
    df = events_df.copy()

    if "join_ticker" not in df.columns:
        df["join_ticker"] = df["issuer_ticker"]

    required_columns = ["join_ticker", "filing_date", "transaction_date", "transaction_code","transaction_acquired_disposed_code", "transaction_price_per_share","transaction_value", "reporting_owner_name"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required event columns: {missing_columns}")

    df["join_ticker"] = df["join_ticker"].astype(str).str.upper().str.strip()
    df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
    df["transaction_value"] = pd.to_numeric(df["transaction_value"], errors="coerce")
    df["transaction_price_per_share"] = pd.to_numeric(df["transaction_price_per_share"], errors="coerce")

    if "filing_lag_days" not in df.columns:
        df["filing_lag_days"] = (df["filing_date"] - df["transaction_date"]).dt.days

    code = df["transaction_code"].fillna("").astype(str).str.upper().str.strip()
    acq_disp = df["transaction_acquired_disposed_code"].fillna("").astype(str).str.upper().str.strip()

    # this is the key. We're filtering for purchase-only events
    is_clean_purchase = ((code == "P") & (acq_disp == "A") & (df["transaction_price_per_share"] > 0)
                          & (df["transaction_value"] > min_purchase_value)
                          & df["filing_date"].notna() & df["join_ticker"].notna())

    df = df[is_clean_purchase].copy()
    df = df[df["filing_lag_days"].between(0, max_filing_lag_days, inclusive="both")].copy()

    if "transaction_shares" in df.columns:
        before = len(df)
        df = df.drop_duplicates(subset=DEDUP_KEYS, keep="first")
        if len(df) != before:
            print(f"Warning: collapsed {before - len(df)} duplicate joint-filer rows before building signals")
    else:
        print("Warning: transaction_shares not in events_df, skipping joint-filer dedup - "
              "signal_purchase_value/signal_insider_count may be inflated by co-filed trades")

    df = df.sort_values("transaction_value", ascending=False)

    agg_dict = {"transaction_value": ["sum", "max", "count"], "reporting_owner_name": "nunique", "transaction_date": "min"}
    if "role_flag" in df.columns:
        agg_dict["role_flag"] = "first"

    signals = df.groupby(["join_ticker", "filing_date"], as_index=False).agg(agg_dict)

    signals.columns = ["join_ticker", "filing_date", "signal_purchase_value", "max_single_purchase_value",
                        "purchase_transaction_count", "signal_insider_count", "first_transaction_date"] + (["role_flag"] if "role_flag" in df.columns else [])

    signals["cluster_buying_at_signal"] = signals["signal_insider_count"] >= cluster_threshold

    return signals.sort_values(["filing_date", "join_ticker"]).reset_index(drop=True)


def build_price_lookup(prices_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """previously prepared prices are stored in a dic"""
    prices = prepare_prices(prices_df)
    return {ticker: group.sort_values("date").reset_index(drop=True) for ticker, group in prices.groupby("ticker", sort=False)}


def get_entry_exit_trade(ticker_prices: pd.DataFrame, signal_date: pd.Timestamp, holding_days: int = HOLDING_DAYS) -> dict | None:
    """Enter next trading day after filing date and exit after holding 20 days"""
    dates, closes = ticker_prices["date"].to_numpy(dtype="datetime64[ns]"), ticker_prices["adjClose"].to_numpy(dtype=float)

    entry_idx = np.searchsorted(dates, np.datetime64(signal_date), side="right")
    exit_idx = entry_idx + holding_days

    if entry_idx >= len(ticker_prices) or exit_idx >= len(ticker_prices):
        return None

    entry_price, exit_price = closes[entry_idx], closes[exit_idx]
    if entry_price <= 0 or np.isnan(entry_price) or np.isnan(exit_price):
        return None

    return {"entry_date": pd.Timestamp(dates[entry_idx]), "exit_date": pd.Timestamp(dates[exit_idx]),"entry_price": entry_price, "exit_price": exit_price, "trade_return": (exit_price / entry_price) - 1,}


def build_insider_purchase_trades(signals_df: pd.DataFrame, prices_df: pd.DataFrame, holding_days: int = HOLDING_DAYS) -> pd.DataFrame:
    """Turn insider purchase signals into backtest trades """

    price_lookup = build_price_lookup(prices_df)
    trades = []

    for _, signal in signals_df.iterrows():
        ticker = signal["join_ticker"]
        if ticker not in price_lookup:
            continue

        trade = get_entry_exit_trade(ticker_prices=price_lookup[ticker], signal_date=signal["filing_date"], holding_days=holding_days)
        if trade is None:
            continue

        trades.append({
            "ticker": ticker, "signal_date": signal["filing_date"], "entry_date": trade["entry_date"], "exit_date": trade["exit_date"],
            "entry_price": trade["entry_price"], "exit_price": trade["exit_price"], "trade_return": trade["trade_return"],
            "signal_purchase_value": signal["signal_purchase_value"], "max_single_purchase_value": signal["max_single_purchase_value"],
            "purchase_transaction_count": signal["purchase_transaction_count"], "signal_insider_count": signal["signal_insider_count"],
            "cluster_buying_at_signal": signal["cluster_buying_at_signal"], "role_flag": signal.get("role_flag", np.nan),
        })

    return pd.DataFrame(trades)


def get_benchmark_return(benchmark_prices: pd.DataFrame, entry_date: pd.Timestamp, exit_date: pd.Timestamp) -> float:
    """Calculate benchmark return over the same entry/exit window."""
    dates, closes = benchmark_prices["date"].to_numpy(dtype="datetime64[ns]"), benchmark_prices["adjClose"].to_numpy(dtype=float)

    entry_idx = np.searchsorted(dates, np.datetime64(entry_date), side="left")
    exit_idx = np.searchsorted(dates, np.datetime64(exit_date), side="left")

    if entry_idx >= len(closes) or exit_idx >= len(closes):
        return np.nan

    entry_price, exit_price = closes[entry_idx], closes[exit_idx]
    if entry_price <= 0 or np.isnan(entry_price) or np.isnan(exit_price):
        return np.nan

    return (exit_price / entry_price) - 1


def add_benchmark_returns(trades_df: pd.DataFrame, prices_df: pd.DataFrame, benchmark_ticker: str = "SPY") -> pd.DataFrame:
    """Add SPY return and abnormal return to each trade."""
    trades = trades_df.copy()
    price_lookup = build_price_lookup(prices_df)
    benchmark_ticker = benchmark_ticker.upper()

    if benchmark_ticker not in price_lookup:
        print(f"Benchmark ticker {benchmark_ticker} not found in prices_df")
        trades["benchmark_return"], trades["abnormal_return"] = np.nan, np.nan
        return trades

    benchmark_prices = price_lookup[benchmark_ticker]
    trades["benchmark_return"] = trades.apply(
        lambda row: get_benchmark_return(benchmark_prices=benchmark_prices, entry_date=row["entry_date"], exit_date=row["exit_date"]), axis=1)
    trades["abnormal_return"] = trades["trade_return"] - trades["benchmark_return"]

    return trades


def summarize_trades(trades_df: pd.DataFrame) -> pd.DataFrame:
    """Summarize trade-level backtest performance"""
    df = trades_df.copy()
    if df.empty:
        return pd.DataFrame()

    summary = {
        "trade_count": len(df), "avg_return": df["trade_return"].mean(), "median_return": df["trade_return"].median(),
        "win_rate": (df["trade_return"] > 0).mean(), "best_trade": df["trade_return"].max(), "worst_trade": df["trade_return"].min(),
    }

    if "benchmark_return" in df.columns:
        summary["avg_benchmark_return"] = df["benchmark_return"].mean()
    if "abnormal_return" in df.columns:
        summary["avg_abnormal_return"] = df["abnormal_return"].mean()
        summary["median_abnormal_return"] = df["abnormal_return"].median()
        summary["abnormal_win_rate"] = (df["abnormal_return"] > 0).mean()

    return pd.DataFrame([summary])


def run_backtest(events_df: pd.DataFrame | None = None, prices_df: pd.DataFrame | None = None, holding_days: int = HOLDING_DAYS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the simple insider purchase 20-day backtest."""
    if events_df is None:
        events_df = load_events_from_r2()
    if prices_df is None:
        prices_df = load_prices_from_r2()
        spy_df = load_prices_from_r2(tickers=["SPY"])
        if spy_df.empty:
            print("Warning: SPY prices not found in R2 - benchmark/abnormal returns will be NaN")
        else:
            prices_df = pd.concat([prices_df, spy_df], ignore_index=True)

    signals_df = get_clean_purchase_signals(events_df)
    trades_df = build_insider_purchase_trades(signals_df=signals_df, prices_df=prices_df, holding_days=holding_days)
    trades_df = add_benchmark_returns(trades_df=trades_df, prices_df=prices_df, benchmark_ticker="SPY")
    summary_df = summarize_trades(trades_df)

    return trades_df, summary_df


if __name__ == "__main__":
    print("Running insider purchase backtest...")

    trades_df, summary_df = run_backtest()
    if trades_df.empty:
        print("No trades generated")
        raise SystemExit

    print("\nBacktest summary:")
    print(summary_df.to_string(index=False))

    sample_cols = ["ticker", "signal_date", "entry_date", "exit_date", "trade_return", "benchmark_return",
                   "abnormal_return", "signal_purchase_value", "signal_insider_count", "cluster_buying_at_signal", "role_flag"]
    top_worst_cols = [c for c in sample_cols if c != "benchmark_return"]

    print("\nSample trades:")
    print(trades_df[sample_cols].head(30).to_string(index=False))

    print("\nTop 20 trades:")
    print(trades_df.sort_values("trade_return", ascending=False)[top_worst_cols].head(20).to_string(index=False))

    print("\nWorst 20 trades:")
    print(trades_df.sort_values("trade_return", ascending=True)[top_worst_cols].head(20).to_string(index=False))