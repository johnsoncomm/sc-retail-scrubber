
import os
os.environ["STREAMLIT_SERVER_ADDRESS"] = "0.0.0.0"
os.environ["STREAMLIT_SERVER_PORT"] = os.environ.get("PORT", "8501")

import re
from io import BytesIO
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title="SC Retail Property Scrubber & Owner Join", layout="wide")
st.title("SC Retail Property Scrubber — Property + Owner Join")

st.markdown("""**Upload two CoStar exports**:
* **Property export** (with columns like *Property Address*, *Property Type*, *RBA*)
* **Owner export** (with columns like *Property Address*, *Company Name*, *Phone*)

The app will:
1. Normalise column names
2. Join owner ↔︎ property rows on normalised *Property Address*
3. Filter for **Retail** in **South Carolina**, **1,500–30,000 SF (RBA)**
4. Give you a single Excel download with *Company Name*, *Company Phone*, etc.
""")

uploaded_files = st.file_uploader(
    "Upload CoStar export files",
    type=["csv", "xlsx", "xls"],
    accept_multiple_files=True,
    help="Drag‑and‑drop or click to browse — you can upload up to two files.",
)

COLUMN_MAP = {
    "Property Name": "property_name",
    "Name": "property_name",
    "Property": "property_name",
    "Address": "address",
    "Street Address": "address",
    "Property Address": "address",
    "City": "city",
    "State": "state",
    "State/Province": "state",
    "Property Type": "property_type",
    "Type": "property_type",
    "Property Subtype": "property_type",
    "Primary Use": "property_type",
    "RBA": "size_sf",
    "Rentable Building Area": "size_sf",
    "Building Size (SF)": "size_sf",
    "GLA": "size_sf",
    "Gross Leasable Area": "size_sf",
    "Total Available Space (SF)": "size_sf",
    "Company Name": "company_name",
    "Company Address": "company_address",
    "Phone": "company_phone",
    "Owner Phone": "company_phone",
}

DEF_SIZE_COLS = [
    "size_sf",
]

OUT_COLS = [
    "property_name",
    "address",
    "city",
    "state",
    "size_sf",
    "company_name",
    "company_address",
    "company_phone",
]

def _clean_numeric(val):
    try:
        if pd.isna(val): return pd.NA
        return pd.to_numeric(re.sub(r"[^0-9.]", "", str(val)), errors="coerce")
    except Exception: return pd.NA

 def normalise(df: pd.DataFrame) -> pd.DataFrame:
    # Rename columns to our standard names
    df = df.rename(columns={c: COLUMN_MAP.get(c, c) for c in df.columns})

    # Make sure 'size_sf' exists
    if "size_sf" not in df.columns:
        for alt in ["RBA", "Total Available Space (SF)", "Rentable Building Area"]:
            if alt in df.columns:
                df["size_sf"] = df[alt]
                break
        else:
            df["size_sf"] = pd.NA

    df["size_sf"] = df["size_sf"].apply(_clean_numeric)

    # Create a join key (fallback to property name if address missing)
    if "address" in df.columns and df["address"].notna().any():
        df["address_key"] = df["address"].astype(str).str.strip().str.lower()
    elif "property_name" in df.columns:
        df["address_key"] = df["property_name"].astype(str).str.strip().str.lower()
    else:
        df["address_key"] = ""

    return df

    # ------------------------------------------------------------------
    # NEW: create a robust join key
    # ------------------------------------------------------------------
    if "address" in df.columns and df["address"].notna().any():
        df["address_key"] = df["address"].astype(str).str.strip().str.lower()
    elif "property_name" in df.columns:
        df["address_key"] = df["property_name"].astype(str).str.strip().str.lower()
    else:
        # sheet has no joinable info → drop it
        df["address_key"] = ""
    return df


def load_all_sheets(file):
    if Path(file.name).suffix.lower().startswith(".csv"):
        return [pd.read_csv(file)]
    else:
        return list(pd.read_excel(file, sheet_name=None).values())

if uploaded_files:
    st.info("Processing…")
    prop_frames, owner_frames = [], []

    for f in uploaded_files:
        for sheet in load_all_sheets(f):
            sheet = normalise(sheet)
            if {"company_name", "company_phone"}.intersection(sheet.columns):
                owner_frames.append(sheet)
            else:
                prop_frames.append(sheet)

    if not prop_frames:
        st.error("No property sheet detected (needs columns like Property Type / RBA).")
        st.stop()

    prop_df = pd.concat(prop_frames, ignore_index=True)
    owners_df = pd.concat(owner_frames, ignore_index=True) if owner_frames else pd.DataFrame(columns=["address_key"])

    merged = prop_df.merge(
        owners_df[["address_key", "company_name", "company_address", "company_phone"]],
        on="address_key",
        how="left"
    )

    # Retail SC filter
    mask = (
        merged["property_type"].astype(str).str.contains("retail", case=False, na=False)
        & (merged["state"].str.upper() == "SC")
        & pd.to_numeric(merged["size_sf"], errors="coerce").between(1500, 30000, inclusive="both")

    )
    filtered = merged.loc[mask]

    # Final ordering
    for col in OUT_COLS:
        if col not in filtered: filtered[col] = pd.NA
    filtered = filtered[OUT_COLS]

    st.success(f"Done! {len(filtered)} matching rows.")
    st.dataframe(filtered, use_container_width=True)

    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="xlsxwriter") as w:
        filtered.to_excel(w, index=False, sheet_name="Merged")
    bio.seek(0)

    st.download_button("📥 Download merged Excel", data=bio.getvalue(),
                       file_name="SC_Retail_Merged.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
else:
    st.info("👋 Upload your Property and Owner CoStar exports to get started.")
