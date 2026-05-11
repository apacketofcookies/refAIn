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

        result = {
            "missing_values": detect_missing(df),
            "duplicate_rows": detect_duplicates(df),
            "inconsistent_labels": detect_inconsistent_labels(df),
            "noise_detection": detect_noise(df),
            "cleaned_preview": df.drop_duplicates().fillna("NULL").head(10).to_dict()
        }

        return result

    elif text:
        # When users paste text (CSV content) we return the fixed/cleaned text
        try:
            df = pd.read_csv(StringIO(text))
        except Exception:
            return {"error": "Unable to parse text as CSV"}

        cleaned = df.drop_duplicates().fillna("")
        # Return cleaned CSV as text so frontend can replace the input
        fixed_text = cleaned.to_csv(index=False)
        return {"fixed_text": fixed_text}

    else:
        return {"error": "No input provided"}

@app.get("/")
def home():
    return {"message": "Backend is working "}