
import os
os.environ["STREAMLIT_SERVER_ADDRESS"] = "0.0.0.0"
os.environ["STREAMLIT_SERVER_PORT"] = os.environ.get("PORT", "8501")

import re
from io import BytesIO
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title="SC Retail Property Scrubber", layout="wide")
st.title("South Carolina Retail Property Scrubber")

st.markdown(
    """Upload **Crexi** or **CoStar** export files (CSV or Excel).  
    The app will unify column headers, filter for *retail* assets in **South Carolina** between
    **1,500 – 30,000 SF**, and return a cleaned Excel file containing:

    • Property name & address  
    • Size (SF) & asking price (if provided)  
    • Owner name & phone number (if provided)  
    • Company name, address, and phone (if provided)  
    • Broker / primary contact details (if provided)"""
)

uploaded_files = st.file_uploader(
    "Upload Crexi or CoStar export(s)",
    type=["csv", "xlsx", "xls"],
    accept_multiple_files=True,
    help="Drag‑and‑drop or click to browse — you can upload several files at once.",
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
    "Market": "market",
    "Property Type": "property_type",
    "Type": "property_type",
    "Property Subtype": "property_type",
    "Primary Use": "property_type",
    "Owner Name": "owner_name",
    "Owner": "owner_name",
    "Ownership": "owner_name",
    "Owner Phone": "owner_phone",
    "Owner Primary Phone": "owner_phone",
    "Contact Number": "owner_phone",
    "Primary Contact": "contact_name",
    "Contact Name": "contact_name",
    "Contact Phone": "contact_phone",
    "Asking Price": "asking_price",
    "Price": "asking_price",
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
    "asking_price",
    "owner_name",
    "owner_phone",
    "contact_name",
    "contact_phone",
    "company_name",
    "company_address",
    "company_phone",
]

def _clean_numeric(val):
    try:
        if pd.isna(val):
            return pd.NA
        return pd.to_numeric(re.sub(r"[^0-9.]", "", str(val)), errors="coerce")
    except Exception:
        return pd.NA

def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    renames = {old: new for old, new in COLUMN_MAP.items() if old in df.columns}
    return df.rename(columns=renames)

def add_size_column(df: pd.DataFrame) -> pd.DataFrame:
    size_cols = [
        "RBA",
        "Total Available Space (SF)",
        "Rentable Building Area",
        "GLA",
        "Gross Leasable Area",
        "Building Size (SF)"
    ]
    for col in size_cols:
        if col in df.columns:
            df["size_sf"] = df[col].apply(_clean_numeric)
            break
    if "size_sf" not in df.columns:
        df["size_sf"] = pd.NA
    return df

def filter_sc_retail(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["property_type", "state"]:
        if col not in df.columns:
            df[col] = pd.NA
    df["property_type"] = df["property_type"].astype(str)
    df = add_size_column(df)
    mask = (
        df["property_type"].str.contains("retail", case=False, na=False)
        & (df["state"].str.upper() == "SC")
        & (df["size_sf"] >= 1500)
        & (df["size_sf"] <= 30000)
    )
    return df.loc[mask]

if uploaded_files:
    st.info("Processing… please wait ⌛")
    frames = []
    for file in uploaded_files:
        try:
            if Path(file.name).suffix.lower().startswith(".csv"):
                df = pd.read_csv(file)
                frames_single = [df]
            else:
                # Read ALL sheets and concatenate
                sheets_dict = pd.read_excel(file, sheet_name=None)
                frames_single = list(sheets_dict.values())
        except Exception as e:
            st.error(f"Could not read {file.name}: {e}")
            continue

        for single_df in frames_single:
            single_df = normalise_columns(single_df)
            single_df = filter_sc_retail(single_df)
            frames.append(single_df)

    if not frames:
        st.error("No valid SC retail data found in the uploaded file(s).")
        st.stop()

    result = pd.concat(frames, ignore_index=True)
    for col in KEY_COLUMNS_OUTPUT:
        if col not in result.columns:
            result[col] = pd.NA
    result = result[KEY_COLUMNS_OUTPUT]

    st.success(f"Done! {len(result)} matching properties found.")
    st.dataframe(result, use_container_width=True)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        result.to_excel(writer, index=False, sheet_name="Filtered")
    output.seek(0)

    st.download_button(
        "📥 Download filtered Excel",
        data=output.getvalue(),
        file_name="SC_Retail_Filtered.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("👋 Upload a Crexi or CoStar export (CSV/XLSX) to get started.")
