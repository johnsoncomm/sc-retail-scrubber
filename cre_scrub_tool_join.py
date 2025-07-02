
import re
from io import BytesIO
from pathlib import Path
import pandas as pd
import streamlit as st

# ---------- Column mapping ----------
COLUMN_MAP = {
    "Property Name": "property_name",
    "Name": "property_name",
    "Property": "property_name",
    "Property Address": "address",
    "Address": "address",
    "Street Address": "address",
    "City": "city",
    "State": "state",
    "State / Country": "state",
    "Property Type": "property_type",
    "Type": "property_type",
    "Property Subtype": "property_type",
    "Primary Use": "property_type",
    "Building Size (SF)": "size_sf",
    "RBA": "size_sf",
    "Total Available Space (SF)": "size_sf",
    "Rentable Building Area": "size_sf",
    "Owner Name": "owner_name",
    "Owner Phone": "owner_phone",
    "Company Name": "company_name",
    "Company Address": "company_address",
    "Company Phone": "company_phone",
    "Phone": "company_phone",
}

OUTPUT_COLS = [
    "property_name",
    "address",
    "city",
    "state",
    "size_sf",
    "property_type",
    "owner_name",
    "owner_phone",
    "company_name",
    "company_address",
    "company_phone",
]

# ---------- Helpers ----------
def _clean_numeric(val):
    try:
        if pd.isna(val):
            return pd.NA
        return pd.to_numeric(re.sub(r"[^0-9.]", "", str(val)), errors="coerce")
    except Exception:
        return pd.NA


def make_key(addr, city):
    if pd.isna(addr) or pd.isna(city):
        return ""
    key = f"{addr} {city}".lower()
    key = re.sub(r"[^a-z0-9]", "", key)
    return key


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    # rename headers
    df = df.rename(columns={c: COLUMN_MAP.get(c, c) for c in df.columns})

    # ensure size column
    if "size_sf" not in df.columns:
        df["size_sf"] = pd.NA
    df["size_sf"] = df["size_sf"].apply(_clean_numeric)

    # ensure address/city columns
    if "address" not in df.columns:
        df["address"] = pd.NA
    if "city" not in df.columns:
        df["city"] = pd.NA

    # join key
    df["join_key"] = df.apply(lambda r: make_key(r["address"], r["city"]), axis=1)
    return df


def load_excel(file) -> pd.DataFrame:
    """Load every sheet in an Excel file into one DataFrame."""
    xl = pd.read_excel(file, sheet_name=None)
    frames = [normalise(s) for s in xl.values()]
    return pd.concat(frames, ignore_index=True)


# ---------- Streamlit UI ----------
st.set_page_config(page_title="SC CRE Join Scrubber", layout="wide")
st.title("South Carolina CRE – Property + Owner Combined")

files = st.file_uploader(
    "Upload exactly **two** CoStar exports (one property sheet, one ownership sheet)",
    type=["xlsx", "xls"],
    accept_multiple_files=True,
)

if files and len(files) == 2:
    st.info("Processing… please wait ⌛")

    # Load & normalise both files
    df_prop = load_excel(files[0])
    df_owner = load_excel(files[1])

    # Left‑join owner info onto properties via join_key
    owner_cols = ["join_key", "company_name", "company_address", "company_phone"]
    df_owner = df_owner[owner_cols].drop_duplicates("join_key")

    merged = df_prop.merge(df_owner, on="join_key", how="left")

    # Guarantee required cols
    for col in ["property_type", "state", "size_sf"]:
        if col not in merged.columns:
            merged[col] = pd.NA

    merged["size_sf"] = pd.to_numeric(merged["size_sf"], errors="coerce")

    # Apply SC retail + size filter
    filtered = merged[
        merged["property_type"].astype(str).str.contains("retail", case=False, na=False)
        & (merged["state"].str.upper() == "SC")
        & merged["size_sf"].between(1500, 30000, inclusive="both")
    ]

    # Ensure all output columns exist
    for col in OUTPUT_COLS:
        if col not in filtered.columns:
            filtered[col] = pd.NA

    filtered = filtered[OUTPUT_COLS]

    st.success(f"Done! {len(filtered)} matching properties found.")
    st.dataframe(filtered, use_container_width=True)

    # Download button
    out = BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        filtered.to_excel(writer, index=False, sheet_name="Filtered")
    out.seek(0)

    st.download_button(
        "📥 Download Excel",
        data=out.getvalue(),
        file_name="SC_CoStar_Joined.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
elif files:
    st.warning("Please upload **exactly two** Excel files to begin.")
