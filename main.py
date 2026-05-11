from fastapi import FastAPI, UploadFile, File, Form
import pandas as pd
import numpy as np
from io import StringIO

app = FastAPI()

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
            df = pd.read_excel(content)

    elif text:
        df = pd.read_csv(StringIO(text))

    else:
        return {"error": "No input provided"}

    result = {
        "missing_values": detect_missing(df),
        "duplicate_rows": detect_duplicates(df),
        "inconsistent_labels": detect_inconsistent_labels(df),
        "noise_detection": detect_noise(df),
        "cleaned_preview": df.drop_duplicates().fillna("NULL").head(10).to_dict()
    }

    return result

@app.get("/")
def home():
    return {"message": "Backend is working "}