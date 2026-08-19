from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from backtest import run_backtest, prepare_prices
from event_study import load_prices_from_r2


STARTING_CAPITAL = 100_000.0
POSITION_SIZE = 5_000.0
MAX_OPEN_POSITIONS = 20
MIN_SIGNAL_PURCHASE_VALUE = 100_000.0
TRANSACTION_COST_RATE = 0.001  # 0.10% per buy/sell


def build_price_matrix(prices_df: pd.DataFrame) -> pd.DataFrame:
    """Create date x ticker price table for daily mark-to-market."""
    prices = prepare_prices(prices_df)

    price_matrix = (
        prices.pivot_table(
            index="date",
            columns="ticker",
            values="adjClose",
            aggfunc="last",
        )
        .sort_index()
        .ffill()
    )

    return price_matrix


def prepare_trades_for_portfolio(
    trades_df: pd.DataFrame,
    min_signal_purchase_value: float = MIN_SIGNAL_PURCHASE_VALUE,
) -> pd.DataFrame:
    """Clean and rank trades before portfolio simulation."""
    df = trades_df.copy()

    required_columns = [
        "ticker",
        "signal_date",
        "entry_date",
        "exit_date",
        "entry_price",
        "exit_price",
        "trade_return",
        "signal_purchase_value",
    ]

    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required trade columns: {missing_columns}")

    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    df["signal_date"] = pd.to_datetime(df["signal_date"], errors="coerce")
    df["entry_date"] = pd.to_datetime(df["entry_date"], errors="coerce")
    df["exit_date"] = pd.to_datetime(df["exit_date"], errors="coerce")
    df["signal_purchase_value"] = pd.to_numeric(
        df["signal_purchase_value"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "ticker",
            "signal_date",
            "entry_date",
            "exit_date",
            "signal_purchase_value",
        ]
    )

    df = df[df["signal_purchase_value"] >= min_signal_purchase_value].copy()

    # if multiple signals happen, pick the biggest insider
    df = df.sort_values(
        ["entry_date", "signal_purchase_value"],
        ascending=[True, False],
    ).reset_index(drop=True)

    df["trade_id"] = np.arange(len(df))

    return df


def get_price(price_matrix: pd.DataFrame, date: pd.Timestamp, ticker: str) -> float:
    """get ticker price on date"""
    if ticker not in price_matrix.columns:
        return np.nan

    try:
        price = price_matrix.at[pd.Timestamp(date), ticker]
    except KeyError:
        return np.nan

    return float(price) if pd.notna(price) else np.nan


def compute_cagr(equity_df: pd.DataFrame, starting_capital: float) -> float:
    years = (equity_df["date"].iloc[-1] - equity_df["date"].iloc[0]).days / 365.25

    if years <= 0:
        return np.nan

    return (equity_df["equity"].iloc[-1] / starting_capital) ** (1 / years) - 1


def compute_max_drawdown(equity_df: pd.DataFrame) -> float:
    running_max = equity_df["equity"].cummax()
    drawdown = (equity_df["equity"] - running_max) / running_max
    return drawdown.min()


def compute_sharpe(equity_df: pd.DataFrame, risk_free_rate: float = 0.0) -> float:
    daily_returns = equity_df["equity"].pct_change().dropna()

    if daily_returns.empty or daily_returns.std() == 0:
        return np.nan

    excess = daily_returns - (risk_free_rate / 252)

    return (excess.mean() / excess.std()) * np.sqrt(252)


def simulate_portfolio(
    trades_df: pd.DataFrame,
    prices_df: pd.DataFrame,
    starting_capital: float = STARTING_CAPITAL,
    position_size: float = POSITION_SIZE,
    max_open_positions: int = MAX_OPEN_POSITIONS,
    transaction_cost_rate: float = TRANSACTION_COST_RATE,
    min_signal_purchase_value: float = MIN_SIGNAL_PURCHASE_VALUE,
    benchmark_ticker: str = "SPY",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Simulate a simple capital-constrained insider purchase portfolio.

    Rules:
    - Start with fixed capital
    - Fixed dollar position size per trade
    - Max open positions
    - Larger signal_purchase_value gets priority when signals collide
    - Skip same ticker if already held
    - Enter on entry_date and exit on exit_date
    """

    trades = prepare_trades_for_portfolio(
        trades_df,
        min_signal_purchase_value=min_signal_purchase_value,
    )

    if trades.empty:
        raise ValueError("No trades available after portfolio filters")

    price_matrix = build_price_matrix(prices_df)

    start_date = trades["entry_date"].min()
    end_date = trades["exit_date"].max()

    trading_days = price_matrix.loc[
        (price_matrix.index >= start_date)
        & (price_matrix.index <= end_date)
    ].index

    if len(trading_days) == 0:
        raise ValueError("No trading days available for portfolio simulation")

    trades_by_entry_date = {
        date: group.copy()
        for date, group in trades.groupby("entry_date", sort=False)
    }

    cash = starting_capital
    open_positions = []
    daily_rows = []
    closed_trades = []
    skipped_trades = []

    benchmark_ticker = benchmark_ticker.upper()

    for current_date in trading_days:
        current_date = pd.Timestamp(current_date)

        # 1. Exit positions whose holding period is done.
        still_open = []

        for position in open_positions:
            ticker = position["ticker"]

            if current_date >= position["exit_date"]:
                exit_price = get_price(price_matrix, current_date, ticker)

                if np.isnan(exit_price):
                    exit_price = position["last_price"]

                gross_exit_value = position["shares"] * exit_price
                sell_cost = gross_exit_value * transaction_cost_rate
                net_exit_value = gross_exit_value - sell_cost

                cash += net_exit_value

                pnl = net_exit_value - position["entry_cost"]
                net_trade_return = pnl / position["entry_cost"]

                closed_trades.append(
                    {
                        "trade_id": position["trade_id"],
                        "ticker": ticker,
                        "entry_date": position["entry_date"],
                        "exit_date": current_date,
                        "entry_price": position["entry_price"],
                        "exit_price": exit_price,
                        "shares": position["shares"],
                        "entry_cost": position["entry_cost"],
                        "net_exit_value": net_exit_value,
                        "pnl": pnl,
                        "net_trade_return": net_trade_return,
                        "signal_purchase_value": position["signal_purchase_value"],
                    }
                )
            else:
                still_open.append(position)

        open_positions = still_open

        # 2. Enter new trades for today, ranked by signal size.
        today_trades = trades_by_entry_date.get(current_date)

        if today_trades is not None:
            for _, trade in today_trades.iterrows():
                ticker = trade["ticker"]
                held_tickers = {pos["ticker"] for pos in open_positions}

                if ticker in held_tickers:
                    skipped_trades.append(
                        {
                            "trade_id": trade["trade_id"],
                            "ticker": ticker,
                            "entry_date": current_date,
                            "reason": "same_ticker_already_held",
                            "signal_purchase_value": trade["signal_purchase_value"],
                        }
                    )
                    continue

                if len(open_positions) >= max_open_positions:
                    skipped_trades.append(
                        {
                            "trade_id": trade["trade_id"],
                            "ticker": ticker,
                            "entry_date": current_date,
                            "reason": "max_open_positions",
                            "signal_purchase_value": trade["signal_purchase_value"],
                        }
                    )
                    continue

                entry_price = get_price(price_matrix, current_date, ticker)

                if np.isnan(entry_price) or entry_price <= 0:
                    skipped_trades.append(
                        {
                            "trade_id": trade["trade_id"],
                            "ticker": ticker,
                            "entry_date": current_date,
                            "reason": "missing_entry_price",
                            "signal_purchase_value": trade["signal_purchase_value"],
                        }
                    )
                    continue

                buy_cost = position_size * transaction_cost_rate
                entry_cost = position_size + buy_cost

                if cash < entry_cost:
                    skipped_trades.append(
                        {
                            "trade_id": trade["trade_id"],
                            "ticker": ticker,
                            "entry_date": current_date,
                            "reason": "not_enough_cash",
                            "signal_purchase_value": trade["signal_purchase_value"],
                        }
                    )
                    continue

                shares = position_size / entry_price
                cash -= entry_cost

                open_positions.append(
                    {
                        "trade_id": trade["trade_id"],
                        "ticker": ticker,
                        "entry_date": current_date,
                        "exit_date": trade["exit_date"],
                        "entry_price": entry_price,
                        "shares": shares,
                        "entry_cost": entry_cost,
                        "signal_purchase_value": trade["signal_purchase_value"],
                        "last_price": entry_price,
                    }
                )

        # 3. Mark open positions to market.
        positions_value = 0.0

        for position in open_positions:
            ticker = position["ticker"]
            price = get_price(price_matrix, current_date, ticker)

            if not np.isnan(price):
                position["last_price"] = price
            else:
                price = position["last_price"]

            positions_value += position["shares"] * price

        equity = cash + positions_value

        daily_rows.append(
            {
                "date": current_date,
                "cash": cash,
                "positions_value": positions_value,
                "equity": equity,
                "open_positions": len(open_positions),
            }
        )

    daily_equity_df = pd.DataFrame(daily_rows)
    closed_trades_df = pd.DataFrame(closed_trades)
    skipped_trades_df = pd.DataFrame(skipped_trades)

    # Add SPY buy-and-hold benchmark equity.
    if benchmark_ticker in price_matrix.columns:
        benchmark_prices = price_matrix.loc[
            daily_equity_df["date"],
            benchmark_ticker,
        ]

        benchmark_start_price = benchmark_prices.iloc[0]

        if pd.notna(benchmark_start_price) and benchmark_start_price > 0:
            daily_equity_df["benchmark_equity"] = (
                starting_capital
                * (benchmark_prices.values / benchmark_start_price)
            )
        else:
            daily_equity_df["benchmark_equity"] = np.nan
    else:
        daily_equity_df["benchmark_equity"] = np.nan

    daily_equity_df["daily_return"] = daily_equity_df["equity"].pct_change()
    daily_equity_df["running_max"] = daily_equity_df["equity"].cummax()
    daily_equity_df["drawdown"] = (
        daily_equity_df["equity"] - daily_equity_df["running_max"]
    ) / daily_equity_df["running_max"]

    return daily_equity_df, closed_trades_df, skipped_trades_df


def summarize_portfolio(
    daily_equity_df: pd.DataFrame,
    closed_trades_df: pd.DataFrame,
    skipped_trades_df: pd.DataFrame,
    starting_capital: float = STARTING_CAPITAL,
) -> pd.DataFrame:
    """Create portfolio-level performance summary."""
    final_equity = daily_equity_df["equity"].iloc[-1]
    total_return = (final_equity / starting_capital) - 1

    summary = {
        "starting_capital": starting_capital,
        "final_equity": final_equity,
        "total_return": total_return,
        "cagr": compute_cagr(daily_equity_df, starting_capital),
        "sharpe": compute_sharpe(daily_equity_df),
        "max_drawdown": compute_max_drawdown(daily_equity_df),
        "closed_trades": len(closed_trades_df),
        "skipped_trades": len(skipped_trades_df),
        "max_open_positions": daily_equity_df["open_positions"].max(),
    }

    if not closed_trades_df.empty:
        summary["trade_win_rate"] = (
            closed_trades_df["net_trade_return"] > 0
        ).mean()
        summary["avg_net_trade_return"] = closed_trades_df[
            "net_trade_return"
        ].mean()
    else:
        summary["trade_win_rate"] = np.nan
        summary["avg_net_trade_return"] = np.nan

    if "benchmark_equity" in daily_equity_df.columns:
        benchmark_final = daily_equity_df["benchmark_equity"].iloc[-1]
        benchmark_return = (benchmark_final / starting_capital) - 1

        summary["benchmark_final_equity"] = benchmark_final
        summary["benchmark_total_return"] = benchmark_return
        summary["excess_return_vs_benchmark"] = total_return - benchmark_return

    return pd.DataFrame([summary])


def plot_equity_curve(daily_equity_df: pd.DataFrame) -> None:
    """Plot strategy equity curve versus SPY benchmark."""
    plt.figure(figsize=(12, 6))

    plt.plot(
        daily_equity_df["date"],
        daily_equity_df["equity"],
        label="Insider portfolio",
    )

    if "benchmark_equity" in daily_equity_df.columns:
        if daily_equity_df["benchmark_equity"].notna().any():
            plt.plot(
                daily_equity_df["date"],
                daily_equity_df["benchmark_equity"],
                label="SPY buy-and-hold",
            )

    plt.title("Capital-Constrained Insider Purchase Portfolio")
    plt.xlabel("Date")
    plt.ylabel("Portfolio Value")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()


def run_portfolio_backtest() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run full portfolio simulation from existing trade-level backtest."""
    prices_df = load_prices_from_r2()

    spy_df = load_prices_from_r2(tickers=["SPY"])
    if not spy_df.empty:
        prices_df = pd.concat([prices_df, spy_df], ignore_index=True)
    else:
        print("Warning: SPY prices not found. Benchmark will be NaN.")

    trades_df, trade_summary_df = run_backtest(prices_df=prices_df)

    print("\nTrade-level summary from backtest.py:")
    print(trade_summary_df.to_string(index=False))

    daily_equity_df, closed_trades_df, skipped_trades_df = simulate_portfolio(
        trades_df=trades_df,
        prices_df=prices_df,
        starting_capital=STARTING_CAPITAL,
        position_size=POSITION_SIZE,
        max_open_positions=MAX_OPEN_POSITIONS,
        transaction_cost_rate=TRANSACTION_COST_RATE,
        min_signal_purchase_value=MIN_SIGNAL_PURCHASE_VALUE,
    )

    portfolio_summary_df = summarize_portfolio(
        daily_equity_df=daily_equity_df,
        closed_trades_df=closed_trades_df,
        skipped_trades_df=skipped_trades_df,
        starting_capital=STARTING_CAPITAL,
    )

    return daily_equity_df, closed_trades_df, skipped_trades_df, portfolio_summary_df


if __name__ == "__main__":
    pd.options.display.float_format = "{:,.4f}".format

    print("Running capital-constrained insider portfolio backtest...")

    daily_equity_df, closed_trades_df, skipped_trades_df, summary_df = (
        run_portfolio_backtest()
    )

    print("\nPortfolio summary:")
    print(summary_df.to_string(index=False))

    print("\nClosed trades sample:")
    print(
        closed_trades_df[
            [
                "ticker",
                "entry_date",
                "exit_date",
                "entry_price",
                "exit_price",
                "pnl",
                "net_trade_return",
                "signal_purchase_value",
            ]
        ]
        .head(20)
        .to_string(index=False)
    )

    print("\nSkipped trade reasons:")
    if skipped_trades_df.empty:
        print("No skipped trades")
    else:
        print(skipped_trades_df["reason"].value_counts().to_string())

    print("\nEquity curve sample:")
    print(daily_equity_df.tail(10).to_string(index=False))

    plot_equity_curve(daily_equity_df)