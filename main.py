from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware  
import pandas as pd
import numpy as np
from io import StringIO
from io import BytesIO

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

# ---------------------------
# CLEANING FUNCTIONS
# ---------------------------

def detect_missing(df):
    return df.isnull().sum().to_dict()

def detect_duplicates(df):
    return int(df.duplicated().sum())

def detect_inconsistent_labels(df):
    issues = {}
    for col in df.select_dtypes(include=['object']).columns:
        issues[col] = df[col].dropna().unique().tolist()
    return issues

def detect_noise(df):
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    noise_report = {}

    for col in numeric_cols:
        z_scores = (df[col] - df[col].mean()) / (df[col].std() + 1e-9)
        noise_report[col] = int((np.abs(z_scores) > 3).sum())

    return noise_report

# ---------------------------
# MAIN ENDPOINT
# ---------------------------

@app.post("/analyze/")
async def analyze_file(file: UploadFile = File(None), text: str = Form(None)):
    if file:
        content = await file.read()

        if file.filename.endswith(".csv"):
            df = pd.read_csv(StringIO(content.decode("utf-8")))
        else:
            df = pd.read_excel(BytesIO(content))

        # Prepare normalized mappings and cleaned data
        original_values = {}
        normalized_mappings = {}

        cleaned = df.drop_duplicates().copy()

        for col in cleaned.columns:
            if cleaned[col].dtype == object or cleaned[col].dtype == 'O':
                # capture original unique values
                uniques = cleaned[col].dropna().unique().tolist()
                original_values[col] = uniques

                # simple normalization: strip and lower-case
                mapping = {}
                for val in uniques:
                    try:
                        norm = str(val).strip().lower()
                    except Exception:
                        norm = val
                    mapping[val] = norm

                # apply mapping
                cleaned[col] = cleaned[col].astype(str).map(lambda v: mapping.get(v, v)).replace('nan', '')
                normalized_mappings[col] = mapping

        # Fill numeric NaNs with empty string for portability when returning CSV
        cleaned = cleaned.fillna("")

        result = {
            "missing_values": detect_missing(df),
            "duplicate_rows": detect_duplicates(df),
            "inconsistent_labels": detect_inconsistent_labels(df),
            "noise_detection": detect_noise(df),
            "normalized_mappings": normalized_mappings,
            "cleaned_preview": cleaned.head(10).to_dict(),
            "cleaned_csv": cleaned.to_csv(index=False)
        }

        return result

    elif text:
        # When users paste text (CSV content) we return the fixed/cleaned text
        try:
            df = pd.read_csv(StringIO(text))
        except Exception:
            return {"error": "Unable to parse text as CSV"}

        # Compute detections
        missing = detect_missing(df)
        duplicates = detect_duplicates(df)
        inconsistent = detect_inconsistent_labels(df)
        noise = detect_noise(df)

        # Clean and normalize similar to file path
        cleaned = df.drop_duplicates().copy()
        normalized_mappings = {}

        for col in cleaned.columns:
            if cleaned[col].dtype == object or cleaned[col].dtype == 'O':
                uniques = cleaned[col].dropna().unique().tolist()
                mapping = {val: str(val).strip().lower() for val in uniques}
                cleaned[col] = cleaned[col].astype(str).map(lambda v: mapping.get(v, v)).replace('nan', '')
                normalized_mappings[col] = mapping

        cleaned = cleaned.fillna("")
        fixed_text = cleaned.to_csv(index=False)

        return {
            "missing_values": missing,
            "duplicate_rows": duplicates,
            "inconsistent_labels": inconsistent,
            "noise_detection": noise,
            "normalized_mappings": normalized_mappings,
            "fixed_text": fixed_text
        }

    else:
        return {"error": "No input provided"}

@app.get("/")
def home():
    return {"message": "Backend is working "}