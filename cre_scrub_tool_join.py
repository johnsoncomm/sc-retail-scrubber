import re
from io import BytesIO
import pandas as pd
import streamlit as st

# ---------- Column mapping ----------
COLUMN_MAP = {
    "Property Name": "property_name",
    "Property Address": "address",
    "Address": "address",
    "City": "city",
    "State": "state",
    "State / Country": "state",
    "Property Type": "property_type",
    "Building Size (SF)": "size_sf",
    "RBA": "size_sf",
    "Total Available Space (SF)": "size_sf",
    "Owner Name": "owner_name",
    "Owner Phone": "owner_phone",
    "Company Name": "company_name",
    "Company Address": "company_address",
    "Company Phone": "company_phone",
    "Phone": "company_phone",
}

KEY_COLUMNS_OUTPUT = [
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


def make_join_key(addr, city):
    if pd.isna(addr) or pd.isna(city):
        return ""
    key = f"{addr} {city}".lower()
    key = re.sub(r"[^a-z0-9]", "", key)
    return key


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    # rename columns
    df = df.rename(columns={c: COLUMN_MAP.get(c, c) for c in df.columns})

    # size_sf
    if "size_sf" in df.columns:
        df["size_sf"] = df["size_sf"].apply(_clean_numeric)
    else:
        df["size_sf"] = pd.NA

    df["address"] = df.get("address", pd.NA)
    df["city"] = df.get("city", pd.NA)

    # join key
    df["join_key"] = df.apply(lambda r: make_join_key(r["address"], r["city"]), axis=1)
    return df


def load_and_normalise(file):
    xl = pd.read_excel(file, sheet_name=None)
    frames = []
    for sheet in xl.values():
        frames.append(normalise(sheet))
    return pd.concat(frames, ignore_index=True)


# ---------- Streamlit app ----------
st.set_page_config(page_title="SC CRE Property + Owner Join", layout="wide")
st.title("South Carolina CRE – Property + Owner Join Tool")

files = st.file_uploader(
    "Upload *two* CoStar exports: 1) PROPERTY and 2) OWNERSHIP",
    type=["xlsx", "xls"],
    accept_multiple_files=True,
)

if files and len(files) == 2:
    st.info("Processing… please wait ⌛")

    prop_df = load_and_normalise(files[0])
    owner_df = load_and_normalise(files[1])

    merged = prop_df.merge(
        owner_df[["join_key", "company_name", "company_address", "company_phone"]],
        on="join_key",
        how="left",
    )

    # fill blanks
    for col in ["property_type", "state", "size_sf"]:
        merged[col] = merged.get(col, pd.NA)

    if "size_sf" in merged.columns:
    merged["size_sf"] = pd.to_numeric(merged["size_sf"], errors="coerce")
else:
    merged["size_sf"] = pd.NA

    # retail-SC filter
    filtered = merged[
        merged["property_type"].str.contains("retail", case=False, na=False)
        & (merged["state"].str.upper() == "SC")
        & merged["size_sf"].between(1500, 30000, inclusive="both")
    ]

    for col in KEY_COLUMNS_OUTPUT:
        if col not in filtered.columns:
            filtered[col] = pd.NA

    filtered = filtered[KEY_COLUMNS_OUTPUT]

    st.success(f"Done! {len(filtered)} matching properties found.")
    st.dataframe(filtered, use_container_width=True)

    out = BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as w:
        filtered.to_excel(w, index=False, sheet_name="Filtered")
    out.seek(0)

    st.download_button(
        "📥 Download Excel",
        data=out.getvalue(),
        file_name="SC_CoStar_Joined.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
elif files:
    st.warning("Please upload **exactly two** Excel files.")
