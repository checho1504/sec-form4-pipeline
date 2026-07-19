import pandas as pd


def clean_dataframe(rows: list) -> pd.DataFrame:
#converting data to the right format
    df = pd.DataFrame(rows)

    df["transaction_date"]  = pd.to_datetime(df["transaction_date"])
    df["period_of_report"]  = pd.to_datetime(df["period_of_report"])
    df["filing_date"] = pd.to_datetime(df["filing_date"])

    df["transaction_shares"]  = pd.to_numeric(df["transaction_shares"])
    df["transaction_price_per_share"]   = pd.to_numeric(df["transaction_price_per_share"])
    df["shares_owned_following_transaction"] = pd.to_numeric(df["shares_owned_following_transaction"])

    bool_columns = [
        "is_director", "is_officer", "is_ten_percent_owner",
        "is_other", "equity_swap_involved", "not_subject_to_section16",
    ]
    for col in bool_columns:
        df[col] = df[col].map({"1": True, "0": False})

    df["transaction_value"] = df["transaction_shares"] * df["transaction_price_per_share"]

    return df