"""
01_clean_data.py
----------------
Cleans the four raw CSV files of the Pet Store analytics project and
writes the cleaned versions to data/clean/.

Run from the project root:
    python scripts/01_clean_data.py
"""

import re
from pathlib import Path

import pandas as pd

# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
CLEAN_DIR = ROOT / "data" / "clean"

# ----------------------------------------------------------------------
# Reference data: full state name -> 2-letter abbreviation.
# Used to standardize the messy "Order State" values in dim_customers.
# ----------------------------------------------------------------------
STATE_NAME_TO_ABBR = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT",
    "DELAWARE": "DE", "DISTRICT OF COLUMBIA": "DC", "FLORIDA": "FL",
    "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL",
    "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS", "KENTUCKY": "KY",
    "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
    "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN",
    "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT",
    "NEBRASKA": "NE", "NEVADA": "NV", "NEW HAMPSHIRE": "NH",
    "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY",
    "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH",
    "OKLAHOMA": "OK", "OREGON": "OR", "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT",
    "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI", "WYOMING": "WY", "PUERTO RICO": "PR",
    "VIRGIN ISLANDS": "VI", "ARMED FORCES EUROPE": "AE",
}


# ----------------------------------------------------------------------
# Load the four raw files.
# dim_products.csv is not UTF-8 (it contains "é"), so it needs cp1252.
# ----------------------------------------------------------------------
def load_raw():
    sales = pd.read_csv(RAW_DIR / "fact_sales.csv")
    customers = pd.read_csv(RAW_DIR / "dim_customers.csv", dtype={"Order Postal": str})
    products = pd.read_csv(RAW_DIR / "dim_products.csv", encoding="cp1252", dtype={"Stock Code": str})
    mapping = pd.read_csv(RAW_DIR / "state_region_mapping.csv")
    return sales, customers, products, mapping


# ----------------------------------------------------------------------
# Standardize one state value to an UPPERCASE 2-letter abbreviation.
# Handles: lower/mixed case, dots ("N.Y.", "AZ."), and full names.
# Returns None when the value cannot be recognized.
# ----------------------------------------------------------------------
def normalize_state(value, valid_abbrs):
    if pd.isna(value):
        return None
    text = re.sub(r"\s+", " ", str(value).strip().upper())
    no_dots = text.replace(".", "")
    if no_dots in valid_abbrs:
        return no_dots
    return STATE_NAME_TO_ABBR.get(no_dots)


# ----------------------------------------------------------------------
# Build a clean state -> region table (one row per state abbreviation).
# The raw mapping has many spelling variants per state, so we keep one
# row per abbreviation. Also reports variant rows that point to the
# wrong state (a data error in the raw file).
# ----------------------------------------------------------------------
def clean_state_region(mapping):
    m = mapping.copy()
    m["State Abbreviations"] = m["State Abbreviations"].str.strip().str.upper()
    m["State"] = m["State"].str.strip()
    m["Region"] = m["Region"].str.strip()

    clean = (
        m[["State Abbreviations", "State", "Region"]]
        .drop_duplicates(subset="State Abbreviations")
        .sort_values("State Abbreviations")
        .reset_index(drop=True)
    )

    # Variant rows whose own text points to a different state than the
    # abbreviation they were assigned (e.g. "Arkansas" -> AK).
    valid = set(clean["State Abbreviations"])
    expected = m["Order State"].apply(lambda v: normalize_state(v, valid))
    bad = m[expected.notna() & (expected != m["State Abbreviations"])]
    return clean, bad[["Order State", "State Abbreviations", "State"]]


# ----------------------------------------------------------------------
# Clean fact_sales:
#   - drop rows with a null Invoice No (decision #1)
#   - keep rows with a null Customer ID (decision #2: they still count
#     toward sales/profit/market basket; they are excluded only from
#     customer-level metrics later)
#   - keep zero/negative quantity rows (decision #3)
#   - parse dates and fix numeric types
# ----------------------------------------------------------------------
def clean_sales(sales):
    df = sales.dropna(subset=["Invoice No"]).copy()
    df["Invoice No"] = df["Invoice No"].astype("int64")
    df["Customer ID"] = df["Customer ID"].astype("Int64")
    df["Transaction Date"] = pd.to_datetime(
        df["Transaction Date"], format="%m/%d/%Y %H:%M", errors="coerce"
    )
    df["Description"] = df["Description"].str.strip()
    df["Stock Code"] = df["Stock Code"].astype(str).str.strip()
    return df.reset_index(drop=True)


# ----------------------------------------------------------------------
# Clean dim_customers:
#   - standardize Order State to UPPERCASE 2-letter abbreviations (#4)
#   - leave null Latitude/Longitude as they are (#5)
# ----------------------------------------------------------------------
def clean_customers(customers, valid_abbrs):
    df = customers.copy()
    df["Order State"] = df["Order State"].apply(lambda v: normalize_state(v, valid_abbrs))
    return df


# ----------------------------------------------------------------------
# Clean dim_products:
#   - fix the "Cleanig" typo in Category (#7)
#   - trim whitespace in text columns
# ----------------------------------------------------------------------
def clean_products(products):
    df = products.copy()
    for col in ["Stock Code", "Description", "Category"]:
        df[col] = df[col].str.strip()
    df["Category"] = df["Category"].replace({"Cleanig Supplies": "Cleaning Supplies"})
    return df


# ----------------------------------------------------------------------
# Print a validation report so every cleaning decision can be verified.
# ----------------------------------------------------------------------
def print_report(raw_sales, sales, raw_customers, customers, products, state_region, bad_map_rows):
    print("=" * 60)
    print("DATA QUALITY REPORT")
    print("=" * 60)

    print("\n[fact_sales]")
    print(f"  raw rows: {len(raw_sales):,} | after dropping null Invoice No: {len(sales):,}")
    print(f"  null Customer ID kept: {sales['Customer ID'].isna().sum():,}")
    print(f"  Quantity <= 0 rows kept: {(sales['Quantity'] <= 0).sum():,}")
    print(f"  Sales <= 0 rows kept: {(sales['Sales'] <= 0).sum():,}")
    print(f"  unparsed dates: {sales['Transaction Date'].isna().sum():,}")
    print(f"  total Sales: {sales['Sales'].sum():,.2f}")

    print("\n[dim_customers]")
    print(f"  distinct raw states: {raw_customers['Order State'].nunique()} -> clean: {customers['Order State'].nunique()}")
    print(f"  unrecognized states (now null): {customers['Order State'].isna().sum()}")
    print(f"  states with no region: {len(set(customers['Order State'].dropna()) - set(state_region['State Abbreviations']))}")
    print(f"  null Latitude/Longitude (left as is): {customers['Latitude'].isna().sum()}")

    print("\n[dim_products]")
    print(f"  products: {len(products)} | categories: {sorted(products['Category'].unique())}")
    sales_codes = set(sales["Stock Code"])
    print(f"  Stock Codes in sales missing from products: {sorted(sales_codes - set(products['Stock Code']))}")

    # Description mismatches between sales and products for the same Stock Code
    joined = sales[["Stock Code", "Description"]].drop_duplicates().merge(
        products[["Stock Code", "Description"]], on="Stock Code", suffixes=("_sales", "_products")
    )
    diff = joined[joined["Description_sales"] != joined["Description_products"]]
    print(f"  Description mismatches (same Stock Code): {len(diff)}")
    for _, r in diff.iterrows():
        print(f"    {r['Stock Code']}: '{r['Description_sales']}' vs '{r['Description_products']}'")

    print("\n[state_region_mapping]")
    print(f"  raw rows: 192 -> clean rows: {len(state_region)}")
    print(f"  variant rows pointing to the wrong state: {len(bad_map_rows)}")
    for _, r in bad_map_rows.iterrows():
        print(f"    '{r['Order State']}' -> {r['State Abbreviations']} ({r['State']})")

    orphan = set(sales["Customer ID"].dropna().astype(int)) - set(customers["Customer ID"])
    print(f"\n[relationships] Customer IDs in sales missing from dim_customers: {len(orphan)}")


# ----------------------------------------------------------------------
# Main: load -> clean -> report -> save.
# ----------------------------------------------------------------------
def main():
    raw_sales, raw_customers, raw_products, raw_mapping = load_raw()

    state_region, bad_map_rows = clean_state_region(raw_mapping)
    valid_abbrs = set(state_region["State Abbreviations"])

    sales = clean_sales(raw_sales)
    customers = clean_customers(raw_customers, valid_abbrs)
    products = clean_products(raw_products)

    print_report(raw_sales, sales, raw_customers, customers, products, state_region, bad_map_rows)

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    # utf-8-sig keeps special characters (like "é") readable in Power BI/Excel
    sales.to_csv(CLEAN_DIR / "fact_sales_clean.csv", index=False, encoding="utf-8-sig")
    customers.to_csv(CLEAN_DIR / "dim_customers_clean.csv", index=False, encoding="utf-8-sig")
    products.to_csv(CLEAN_DIR / "dim_products_clean.csv", index=False, encoding="utf-8-sig")
    state_region.to_csv(CLEAN_DIR / "dim_state_region_clean.csv", index=False, encoding="utf-8-sig")
    print(f"\nClean files saved to: {CLEAN_DIR}")


if __name__ == "__main__":
    main()
