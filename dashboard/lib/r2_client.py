"""Shared Cloudflare R2 client + cached parquet loaders.

Every dashboard page should pull data through this module instead of
talking to boto3 directly, so caching and credential handling stay
in one place.
"""
from __future__ import annotations

import io
import os

import boto3
import pandas as pd
import streamlit as st


def _secret(key: str) -> str | None:
    """Read a credential from st.secrets first, falling back to env vars
    so the same code works locally (.env) and on Streamlit Cloud (secrets)."""
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key)


@st.cache_resource(show_spinner=False)
def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=_secret("R2_ENDPOINT_URL"),
        aws_access_key_id=_secret("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_secret("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )


def _bucket() -> str:
    bucket = _secret("R2_BUCKET_NAME")
    if not bucket:
        raise RuntimeError("R2_BUCKET_NAME is not set in secrets or env vars")
    return bucket


@st.cache_data(ttl=3600, show_spinner=False)
def load_parquet(key: str) -> pd.DataFrame:
    """Load a single parquet object from R2. Returns an empty df on failure
    instead of raising, so one missing ticker doesn't crash a page."""
    client = get_r2_client()
    try:
        response = client.get_object(Bucket=_bucket(), Key=key)
        body = response["Body"].read()
        return pd.read_parquet(io.BytesIO(body))
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def list_available_tickers(dataset: str = "signals") -> list[str]:
    """List tickers that have data under a given dataset prefix
    (form4, prices, events, signals, insider_panel)."""
    client = get_r2_client()
    prefix = f"{dataset}/ticker="
    tickers: set[str] = set()

    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=_bucket(), Prefix=prefix, Delimiter="/"):
            for common_prefix in page.get("CommonPrefixes", []):
                ticker = common_prefix["Prefix"].removeprefix(prefix).rstrip("/")
                if ticker:
                    tickers.add(ticker)
    except Exception as e:
        st.error(f"Could not list tickers from R2: {e}")

    return sorted(tickers)


@st.cache_data(ttl=3600, show_spinner=False)
def load_dataset(dataset: str, tickers: tuple[str, ...]) -> pd.DataFrame:
    """Load and concat parquet files for many tickers under a dataset prefix.

    tickers must be a tuple (not a list) so Streamlit's cache can hash it.
    """
    frames = []
    for ticker in tickers:
        key = f"{dataset}/ticker={ticker}/{dataset}_{ticker.lower()}.parquet"
        df = load_parquet(key)
        if not df.empty:
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
