from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware  
import pandas as pd
import numpy as np
from io import StringIO
from io import BytesIO
from typing import Dict, Any

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://paraphrase-tool.netlify.app",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

NUMERIC_COLUMN_HINTS = (
    "age", "year", "years", "count", "qty", "quantity", "price", "amount",
    "score", "rate", "id", "number", "num", "salary", "cost", "total"
)


def detect_missing(df: pd.DataFrame) -> Dict[str, int]:
    return df.isnull().sum().to_dict()


def detect_duplicates(df: pd.DataFrame) -> int:
    return int(df.duplicated().sum())


def detect_inconsistent_labels(df: pd.DataFrame) -> Dict[str, Any]:
    issues: Dict[str, Any] = {}
    for col in df.select_dtypes(include=["object"]).columns:
        values = df[col].dropna().astype(str).str.strip()
        values = values[values != ""]
        unique_values = values.unique().tolist()

        normalized_groups: Dict[str, list] = {}
        for v in unique_values:
            key = " ".join(v.lower().split())
            normalized_groups.setdefault(key, []).append(v)

        inconsistent = {k: vs for k, vs in normalized_groups.items() if len(vs) > 1}
        if inconsistent:
            issues[col] = inconsistent
    return issues


def detect_noise(df: pd.DataFrame) -> Dict[str, int]:
    noise_report: Dict[str, int] = {}
    for col in df.columns:
        numeric = pd.to_numeric(df[col], errors="coerce")
        valid = numeric.dropna()
        if valid.empty:
            continue

        std = valid.std()
        if std is None or np.isclose(std, 0):
            noise_report[col] = 0
            continue

        z_scores = (valid - valid.mean()) / std
        noise_report[col] = int((np.abs(z_scores) > 3).sum())
    return noise_report


def normalize_text_value(value: Any) -> Any:
    if pd.isna(value):
        return np.nan
    text = str(value).strip()
    if text == "":
        return np.nan
    return " ".join(text.lower().split())


def is_numeric_expected_column(df: pd.DataFrame, col: str) -> bool:
    col_name = col.lower()
    if any(hint in col_name for hint in NUMERIC_COLUMN_HINTS):
        return True

    raw = df[col]
    non_empty = raw.dropna().astype(str).str.strip()
    non_empty = non_empty[non_empty != ""]
    if len(non_empty) < 3:
        return False

    numeric_ratio = pd.to_numeric(non_empty, errors="coerce").notna().mean()
    return numeric_ratio >= 0.8


def analyze_and_normalize(df: pd.DataFrame) -> Dict[str, Any]:
    original_df = df.copy()

    # Ensure empty/whitespace object cells are treated as missing values.
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].replace(r"^\s*$", np.nan, regex=True)

    missing_values = detect_missing(df)
    duplicate_rows = detect_duplicates(df)
    inconsistent_labels = detect_inconsistent_labels(df)
    noise_detection = detect_noise(df) if len(df) < 10000 else {}

    cleaned = df.copy()
    row_counts = {
        "original_rows": int(len(cleaned)),
        "after_deduplication": 0,
        "after_drop_missing": 0,
        "after_drop_invalid_numeric": 0,
        "after_drop_noise": 0,
        "final_rows": 0,
    }

    # 1) Remove duplicate rows.
    before = len(cleaned)
    cleaned = cleaned.drop_duplicates()
    removed_duplicates = before - len(cleaned)
    row_counts["after_deduplication"] = int(len(cleaned))

    # 2) Remove rows with missing values in any column.
    before = len(cleaned)
    cleaned = cleaned.dropna(how="any")
    removed_missing_rows = before - len(cleaned)
    row_counts["after_drop_missing"] = int(len(cleaned))

    # 3) Normalize labels and detect invalid numeric rows.
    normalized_mappings: Dict[str, Dict[str, Any]] = {}
    invalid_numeric_mask = pd.Series(False, index=cleaned.index)
    numeric_expected_columns = []

    for col in cleaned.columns:
        if cleaned[col].dtype == object or cleaned[col].dtype == "O":
            uniques = cleaned[col].dropna().unique().tolist()
            mapping: Dict[str, Any] = {}
            for val in uniques:
                mapping[str(val)] = normalize_text_value(val)

            cleaned[col] = cleaned[col].map(lambda v: normalize_text_value(v))
            changed = {k: v for k, v in mapping.items() if str(k) != str(v)}
            if changed:
                normalized_mappings[col] = changed

        if is_numeric_expected_column(original_df, col):
            numeric_expected_columns.append(col)
            raw_col = cleaned[col].astype(str).str.strip()
            coerced = pd.to_numeric(raw_col, errors="coerce")
            invalid_here = raw_col.ne("") & coerced.isna()
            invalid_numeric_mask = invalid_numeric_mask | invalid_here
            cleaned[col] = coerced

    # 4) Drop rows with invalid numeric values in numeric-expected columns.
    removed_invalid_numeric_rows = int(invalid_numeric_mask.sum())
    cleaned = cleaned[~invalid_numeric_mask].copy()
    row_counts["after_drop_invalid_numeric"] = int(len(cleaned))

    # 5) Drop outlier rows (noise) based on z-score > 3 for numeric columns.
    # Skip for large datasets to avoid timeout
    removed_noise_rows = 0
    if len(cleaned) < 10000:
        numeric_cols = [c for c in cleaned.columns if pd.api.types.is_numeric_dtype(cleaned[c])]
        noise_row_mask = pd.Series(False, index=cleaned.index)
        for col in numeric_cols:
            valid = cleaned[col].dropna()
            if valid.empty:
                continue
            std = valid.std()
            if std is None or np.isclose(std, 0):
                continue
            z = (cleaned[col] - valid.mean()) / std
            noise_row_mask = noise_row_mask | (z.abs() > 3)
        removed_noise_rows = int(noise_row_mask.sum())
        cleaned = cleaned[~noise_row_mask].copy()
    row_counts["after_drop_noise"] = int(len(cleaned))

    row_counts["final_rows"] = int(len(cleaned))

    cleaned_for_export = cleaned.fillna("")
    cleaned_csv = cleaned_for_export.to_csv(index=False)

    return {
        "missing_values": missing_values,
        "duplicate_rows": duplicate_rows,
        "inconsistent_labels": inconsistent_labels,
        "noise_detection": noise_detection,
        "normalized_mappings": normalized_mappings,
        "numeric_expected_columns": numeric_expected_columns,
        "removed_rows": {
            "duplicates": int(removed_duplicates),
            "missing_required_values": int(removed_missing_rows),
            "invalid_numeric_values": int(removed_invalid_numeric_rows),
            "noise_outliers": int(removed_noise_rows),
        },
        "row_counts": row_counts,
        "cleaned_preview": cleaned_for_export.head(10).to_dict(orient="records"),
        "cleaned_csv": cleaned_csv,
        "fixed_text": cleaned_csv,
    }

# ---------------------------
# MAIN ENDPOINT
# ---------------------------

@app.post("/analyze/")
async def analyze_file(file: UploadFile = File(None), text: str = Form(None)):
    if file:
        content = await file.read()

        # Check file size
        if len(content) > MAX_FILE_SIZE_BYTES:
            return {
                "error": f"File size exceeds {MAX_FILE_SIZE_MB}MB limit",
                "file_size_mb": round(len(content) / 1024 / 1024, 2)
            }

        if file.filename.endswith(".csv"):
            df = pd.read_csv(StringIO(content.decode("utf-8")))
        else:
            df = pd.read_excel(BytesIO(content))

        return analyze_and_normalize(df)

    elif text:
        # Check text size limit
        text_size_bytes = len(text.encode('utf-8'))
        if text_size_bytes > MAX_FILE_SIZE_BYTES:
            return {
                "error": f"Text size exceeds {MAX_FILE_SIZE_MB}MB limit",
                "text_size_mb": round(text_size_bytes / 1024 / 1024, 2)
            }
        
        # When users paste text (CSV content) we return the fixed/cleaned text
        try:
            df = pd.read_csv(StringIO(text))
        except Exception:
            return {"error": "Unable to parse text as CSV"}

        return analyze_and_normalize(df)

    else:
        return {"error": "No input provided"}

@app.get("/")
def home():
    return {"message": "Backend is working "}