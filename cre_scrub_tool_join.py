import re
from io import BytesIO
from pathlib import Path
import pandas as pd
import streamlit as st

COLUMN_MAP = {
    "Property Name": "property_name",
    "Name": "property_name",
    "Property": "property_name",
    "Property Address": "address",
    "Address": "address",
    "Street Address": "address",
    "City": "city",
    "State": "state",
    "Market": "market",
    "Property Type": "property_type",
    "Type": "property_type",
    "Building Size (SF)": "size_sf",
    "Gross Leasable Area": "size_sf",
    "GLA": "size_sf",
    "Size (SF)": "size_sf",
    "Owner Name": "owner_name",
    "Owner": "owner_name",
    "Ownership": "owner_name",
    "Owner Phone": "owner_phone",
    "Owner Primary Phone": "owner_phone",
    "Contact Number": "owner_phone",
    "Primary Contact": "contact_name",
    "Contact Name": "contact_name",
    "Contact Phone": "contact_phone",
    "Company Name": "company_name",
    "Company Address": "company_address",
    "Company Phone": "company_phone",
}

KEY_COLUMNS_OUTPUT = [
    "property_name",
    "address",
    "city",
    "state",
    "size_sf",
    "owner_name",
    "owner_phone",
    "contact_name",
    "contact_phone",
    "company_name",
    "company_address",
    "company_phone",
]

def _clean_numeric(val):
    if pd.isna(val):
        return pd.NA
    return pd.to_numeric(re.sub(r"[^0-9.]", "", str(val)), errors="coerce")

def normalise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: COLUMN_MAP.get(c, c) for c in df.columns})

    if "size_sf" not in df.columns:
        for alt in ["RBA", "Total Available Space (SF)", "Rentable Building Area"]:
            if alt in df.columns:
                df["size_sf"] = df[alt]
                break
        else:
            df["size_sf"] = pd.NA

    df["size_sf"] = df["size_sf"].apply(_clean_numeric)

    if "address" in df.columns and df["address"].notna().any():
        df["address_key"] = df["address"].astype(str).str.strip().str.lower()
    elif "property_name" in df.columns:
        df["address_key"] = df["property_name"].astype(str).str.strip().str.lower()
    else:
        df["address_key"] = ""

    return df

def load_and_normalise(file):
    xl = pd.read_excel(file, sheet_name=None)
    all_frames = []
    for sheet in xl.values():
        sheet = normalise(sheet)
        all_frames.append(sheet)
    return pd.concat(all_frames, ignore_index=True)

st.set_page_config(page_title="SC CRE Join Scrubber", layout="wide")
st.title("South Carolina CRE: Property + Ownership Join Tool")

uploaded_files = st.file_uploader(
    "Upload your two CoStar export files (property + ownership)",
    type=["xlsx", "xls"],
    accept_multiple_files=True
)

if uploaded_files and len(uploaded_files) == 2:
    st.info("Processing… please wait ⌛")

    df1 = load_and_normalise(uploaded_files[0])
    df2 = load_and_normalise(uploaded_files[1])

    merged = pd.merge(df1, df2, on="address_key", suffixes=("_left", "_right"), how="outer")

    if "property_type" not in merged.columns:
        merged["property_type"] = ""

    if "state" not in merged.columns:
        merged["state"] = ""

    if "size_sf" not in merged.columns:
        merged["size_sf"] = pd.NA

    merged = merged[
        merged["property_type"].str.lower().str.contains("retail", na=False)
        & (merged["state"].str.upper() == "SC")
        & pd.to_numeric(merged["size_sf"], errors="coerce").between(1500, 30000, inclusive="both")
    ]

    for col in KEY_COLUMNS_OUTPUT:
        if col not in merged.columns:
            merged[col] = pd.NA

    merged = merged[KEY_COLUMNS_OUTPUT]

    st.success(f"Done! {len(merged)} matching properties found.")
    st.dataframe(merged, use_container_width=True)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        merged.to_excel(writer, index=False, sheet_name="Filtered")
    output.seek(0)

    st.download_button(
        label="📥 Download matched Excel",
        data=output.getvalue(),
        file_name="SC_CoStar_Joined.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

elif uploaded_files:
    st.warning("Please upload exactly two Excel files to begin.")
