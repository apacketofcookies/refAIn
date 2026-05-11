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
MAX_ROWS = 50000  # Hard limit for rejecting very large datasets
MAX_FULL_ANALYSIS_ROWS = 1000  # Expensive checks skipped above this (label/noise detection)
MAX_FAST_DEDUPE_ROWS = 10000  # Use faster dedup method for large datasets

NUMERIC_COLUMN_HINTS = (
    "age", "year", "years", "count", "qty", "quantity", "price", "amount",
    "score", "rate", "id", "number", "num", "salary", "cost", "total"
)


def detect_missing(df: pd.DataFrame) -> Dict[str, int]:
    return df.isnull().sum().to_dict()


def detect_duplicates(df: pd.DataFrame) -> int:
    if len(df) > MAX_FAST_DEDUPE_ROWS:
        # For very large datasets, skip full duplicate detection to save time
        return 0
    return int(df.duplicated().sum())


def detect_inconsistent_labels(df: pd.DataFrame) -> Dict[str, Any]:
    issues: Dict[str, Any] = {}
    # Skip for larger datasets to avoid timeout
    if len(df) > MAX_FULL_ANALYSIS_ROWS:
        return issues
    
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
    if len(df) > MAX_FULL_ANALYSIS_ROWS:
        return noise_report

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
    """Fast analysis: clean data only, skip expensive detection."""
    original_rows = len(df)
    original_cols = len(df.columns)

    # Fast cleaning: minimal operations
    cleaned = df.copy()
    
    # 1) Remove completely empty rows
    cleaned = cleaned.dropna(how='all')
    
    # 2) Remove rows with ANY missing values
    before_missing = len(cleaned)
    cleaned = cleaned.dropna(how='any')
    removed_missing = before_missing - len(cleaned)
    
    # 3) Remove duplicates (only if dataset is small enough)
    removed_duplicates = 0
    if len(cleaned) <= 5000:
        before_dupes = len(cleaned)
        cleaned = cleaned.drop_duplicates()
        removed_duplicates = before_dupes - len(cleaned)
    
    # 4) Normalize text whitespace in object columns
    for col in cleaned.columns:
        if cleaned[col].dtype == 'object':
            cleaned[col] = cleaned[col].str.strip() if hasattr(cleaned[col], 'str') else cleaned[col]
    
    # 5) Normalize numeric columns (no validation, just convert)
    for col in cleaned.columns:
        if any(hint in col.lower() for hint in NUMERIC_COLUMN_HINTS):
            cleaned[col] = pd.to_numeric(cleaned[col], errors='coerce')
    
    row_counts = {
        "original_rows": int(original_rows),
        "original_columns": int(original_cols),
        "after_missing_removal": int(len(cleaned)),
        "duplicates_removed": int(removed_duplicates),
        "final_rows": int(len(cleaned)),
    }
    
    # Export cleaned data
    cleaned_for_export = cleaned.fillna("")
    cleaned_csv = cleaned_for_export.to_csv(index=False)
    
    total_removed = removed_missing + removed_duplicates
    improvement_pct = round((total_removed / original_rows * 100), 1) if original_rows > 0 else 0
    
    return {
        "message": "Dataset cleaned successfully",
        "removed_rows": int(total_removed),
        "improvement_percentage": improvement_pct,
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
            # Try decoding with utf-8 first, then latin-1 if needed
            decoded = None
            try:
                decoded = content.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    decoded = content.decode('latin-1')
                except Exception:
                    return {"error": "Unable to decode CSV file (unsupported encoding)"}

            # Strip BOM if present
            if decoded and decoded.startswith('\ufeff'):
                decoded = decoded.lstrip('\ufeff')

            # Try parsing; if default parser fails, try python engine with sep inference
            try:
                df = pd.read_csv(StringIO(decoded))
            except Exception as e1:
                try:
                    df = pd.read_csv(StringIO(decoded), sep=None, engine='python')
                except Exception as e2:
                    try:
                        # Try common alternative delimiters
                        first_line = decoded.split('\n')[0]
                        if ';' in first_line:
                            df = pd.read_csv(StringIO(decoded), sep=';')
                        elif '\t' in first_line:
                            df = pd.read_csv(StringIO(decoded), sep='\t')
                        else:
                            return {"error": "Unable to parse CSV file", "details": str(e1)}
                    except Exception as e3:
                        return {"error": "Unable to parse CSV file", "details": str(e3)}
            
            # Clean up whitespace and normalize
            df = df.copy()
            for col in df.columns:
                if df[col].dtype == 'object':
                    df[col] = df[col].str.strip() if hasattr(df[col], 'str') else df[col]
            
            # Remove completely empty rows
            df = df.dropna(how='all')
            
            # Remove completely empty columns
            df = df.dropna(axis=1, how='all')
            
            # Normalize column names
            df.columns = df.columns.str.strip().str.lower().str.replace(r'\s+', '_', regex=True)
        else:
            try:
                df = pd.read_excel(BytesIO(content))
            except Exception as e:
                return {"error": "Unable to parse Excel file", "details": str(e)}

        # Check row count limit
        if len(df) > MAX_ROWS:
            return {
                "error": f"Dataset exceeds {MAX_ROWS:,} row limit",
                "rows": len(df),
                "details": f"Your file has {len(df):,} rows. Try splitting it into smaller files."
            }

        return analyze_and_normalize(df)

    elif text:
        # Check text size limit
        text_size_bytes = len(text.encode('utf-8'))
        if text_size_bytes > MAX_FILE_SIZE_BYTES:
            return {
                "error": f"Text size exceeds {MAX_FILE_SIZE_MB}MB limit",
                "text_size_mb": round(text_size_bytes / 1024 / 1024, 2)
            }
        
        # Parse CSV with robust error handling
        try:
            df = pd.read_csv(StringIO(text))
        except Exception as e1:
            # Try alternate parsing strategies
            try:
                df = pd.read_csv(StringIO(text), sep=None, engine='python')
            except Exception as e2:
                # Last resort: try semicolon or tab
                try:
                    if ';' in text.split('\n')[0]:
                        df = pd.read_csv(StringIO(text), sep=';')
                    elif '\t' in text.split('\n')[0]:
                        df = pd.read_csv(StringIO(text), sep='\t')
                    else:
                        return {"error": "Unable to parse CSV. Ensure it's comma, semicolon, or tab-separated.", "details": str(e1)}
                except Exception as e3:
                    return {"error": "Unable to parse CSV data", "details": str(e3)}
        
        # Clean up whitespace in data
        df = df.copy()
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].str.strip() if hasattr(df[col], 'str') else df[col]
        
        # Remove completely empty rows
        df = df.dropna(how='all')
        
        # Remove completely empty columns
        df = df.dropna(axis=1, how='all')
        
        # Normalize column names: strip whitespace and lowercase for consistency
        df.columns = df.columns.str.strip().str.lower().str.replace(r'\s+', '_', regex=True)

        # Check row count limit
        if len(df) > MAX_ROWS:
            return {
                "error": f"Dataset exceeds {MAX_ROWS:,} row limit",
                "rows": len(df),
                "details": f"Your data has {len(df):,} rows. Try pasting a smaller dataset."
            }

        return analyze_and_normalize(df)

    else:
        return {"error": "No input provided"}

@app.get("/")
def home():
    return {"message": "Backend is working "}