"""Comparative analysis engine — computes price indices, fee differentials, and coverage metrics."""

import pandas as pd
import numpy as np
from typing import Any


PLATFORMS = ["rappi", "ubereats", "didifood"]
PLATFORM_LABELS = {"rappi": "Rappi", "ubereats": "Uber Eats", "didifood": "DiDi Food"}


def load_dataframe(csv_path: str) -> pd.DataFrame:
    """Load a processed CSV into a DataFrame with correct dtypes."""
    df = pd.read_csv(csv_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    numeric_cols = [
        "product_price_mxn", "delivery_fee_mxn", "service_fee_mxn",
        "total_price_mxn", "estimated_delivery_min", "estimated_delivery_max",
        "discount_amount_mxn",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def compute_price_index(df: pd.DataFrame) -> pd.DataFrame:
    """Compute price index by platform where Rappi = 100.

    Args:
        df: Full dataset with product_price_mxn column.

    Returns:
        DataFrame with columns: platform, avg_price, price_index
    """
    success = df[df["scraping_status"] == "success"].copy()
    avg_prices = success.groupby("platform")["product_price_mxn"].mean()

    rappi_avg = avg_prices.get("rappi", avg_prices.mean())
    index = pd.DataFrame({
        "platform": avg_prices.index,
        "avg_price_mxn": avg_prices.values,
        "price_index": (avg_prices.values / rappi_avg * 100).round(1),
    })
    index["platform_label"] = index["platform"].map(PLATFORM_LABELS)
    return index.reset_index(drop=True)


def compute_price_index_by_zone(df: pd.DataFrame) -> pd.DataFrame:
    """Price index per platform × zone_type heatmap data."""
    success = df[df["scraping_status"] == "success"].copy()
    pivot = (
        success.groupby(["zone_type", "platform"])["product_price_mxn"]
        .mean()
        .unstack("platform")
        .round(2)
    )
    # Normalize so Rappi = 100 within each zone
    if "rappi" in pivot.columns:
        for col in pivot.columns:
            pivot[col + "_idx"] = (pivot[col] / pivot["rappi"] * 100).round(1)
    return pivot.reset_index()


def compute_delivery_fee_by_zone(df: pd.DataFrame) -> pd.DataFrame:
    """Average delivery fee per platform × zone_type."""
    success = df[df["scraping_status"] == "success"].copy()
    result = (
        success.groupby(["zone_type", "platform"])["delivery_fee_mxn"]
        .mean()
        .round(2)
        .reset_index()
    )
    result["platform_label"] = result["platform"].map(PLATFORM_LABELS)
    return result


def compute_delivery_fee_by_city(df: pd.DataFrame) -> pd.DataFrame:
    """Average delivery fee per platform × city."""
    success = df[df["scraping_status"] == "success"].copy()
    result = (
        success.groupby(["city", "platform"])["delivery_fee_mxn"]
        .mean()
        .round(2)
        .reset_index()
    )
    result["platform_label"] = result["platform"].map(PLATFORM_LABELS)
    return result


def compute_delivery_time_comparison(df: pd.DataFrame) -> pd.DataFrame:
    """Average estimated delivery time (midpoint) per platform × city."""
    success = df[df["scraping_status"] == "success"].copy()
    success = success.dropna(subset=["estimated_delivery_min", "estimated_delivery_max"])
    success["delivery_midpoint"] = (
        success["estimated_delivery_min"] + success["estimated_delivery_max"]
    ) / 2
    result = (
        success.groupby(["city", "platform"])["delivery_midpoint"]
        .mean()
        .round(1)
        .reset_index()
    )
    result["platform_label"] = result["platform"].map(PLATFORM_LABELS)
    return result


def compute_coverage(df: pd.DataFrame) -> pd.DataFrame:
    """Coverage = % of records where restaurant_available == True, per platform × zone."""
    result = (
        df.groupby(["zone_type", "platform"])
        .apply(lambda g: (g["restaurant_available"].sum() / len(g) * 100).round(1))
        .reset_index(name="availability_pct")
    )
    result["platform_label"] = result["platform"].map(PLATFORM_LABELS)
    return result


def compute_promotional_aggressiveness(df: pd.DataFrame) -> pd.DataFrame:
    """Discount frequency and average discount amount per platform."""
    success = df[df["scraping_status"] == "success"].copy()
    discount_freq = (
        success.groupby("platform")["active_discount"]
        .mean()
        .mul(100)
        .round(1)
        .reset_index(name="discount_frequency_pct")
    )
    avg_discount = (
        success[success["active_discount"]]
        .groupby("platform")["discount_amount_mxn"]
        .mean()
        .round(2)
        .reset_index(name="avg_discount_mxn")
    )
    result = discount_freq.merge(avg_discount, on="platform", how="left")
    result["platform_label"] = result["platform"].map(PLATFORM_LABELS)
    return result


def compute_total_cost_comparison(df: pd.DataFrame) -> pd.DataFrame:
    """Total cost (product + delivery + service fee) per platform × product."""
    success = df[df["scraping_status"] == "success"].copy()
    result = (
        success.groupby(["product_name", "platform"])["total_price_mxn"]
        .mean()
        .round(2)
        .reset_index()
    )
    result["platform_label"] = result["platform"].map(PLATFORM_LABELS)
    return result


def compute_rappi_competitiveness_gap(df: pd.DataFrame) -> dict[str, Any]:
    """Identify zones where Rappi is least competitive vs competitors.

    Returns a dict with the worst gap zone and the numeric gap.
    """
    fee_by_zone = compute_delivery_fee_by_zone(df)
    rappi_fees = fee_by_zone[fee_by_zone["platform"] == "rappi"][["zone_type", "delivery_fee_mxn"]]
    best_competitor = (
        fee_by_zone[fee_by_zone["platform"] != "rappi"]
        .groupby("zone_type")["delivery_fee_mxn"]
        .min()
        .reset_index(name="min_competitor_fee")
    )
    merged = rappi_fees.merge(best_competitor, on="zone_type")
    merged["gap_mxn"] = (merged["delivery_fee_mxn"] - merged["min_competitor_fee"]).round(2)
    worst = merged.loc[merged["gap_mxn"].idxmax()]
    return {
        "worst_zone": worst["zone_type"],
        "rappi_fee": worst["delivery_fee_mxn"],
        "competitor_fee": worst["min_competitor_fee"],
        "gap_mxn": worst["gap_mxn"],
        "gap_pct": round(worst["gap_mxn"] / worst["min_competitor_fee"] * 100, 1),
    }


def run_full_analysis(df: pd.DataFrame) -> dict[str, Any]:
    """Run all comparative analyses and return a single results dict."""
    return {
        "price_index": compute_price_index(df),
        "price_index_by_zone": compute_price_index_by_zone(df),
        "delivery_fee_by_zone": compute_delivery_fee_by_zone(df),
        "delivery_fee_by_city": compute_delivery_fee_by_city(df),
        "delivery_time": compute_delivery_time_comparison(df),
        "coverage": compute_coverage(df),
        "promotions": compute_promotional_aggressiveness(df),
        "total_cost": compute_total_cost_comparison(df),
        "competitiveness_gap": compute_rappi_competitiveness_gap(df),
        "record_count": len(df),
        "success_count": len(df[df["scraping_status"] == "success"]),
        "scraping_mode": df["scraping_mode"].iloc[0] if len(df) > 0 else "unknown",
    }
