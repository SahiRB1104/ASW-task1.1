# Claim Processing PoC

A hands-on Proof-of-Concept for automated insurance claim processing. This lightweight Flask app demonstrates an end-to-end flow:

- Upload claim documents (PDF) to S3
- Run a Textract worker to extract and process text
- Local extraction and summarization
- Optional LLM (Bedrock) based extraction and summary

## Highlights

- Minimal UI for uploading and processing files
- Uses `scripts/` utilities for local extraction and summarization
- `app/textract_worker.py` produces `processed/<file>.txt` which the app downloads and analyzes

## Image

Include an illustrative image in your project and reference it here. Place your image at:

`static/images/claim_flow.png`

Then GitHub will render it in the README like this (if the file exists):

![Flowchart illustrating the automated insurance claim processing steps, including document upload to S3, text extraction using Textract, local summarization, and optional LLM-based analysis. The flowchart is set against a clean, professional background, conveying a sense of efficiency and clarity.](app\static\images\image.png)

## Quick start

1. Create and activate the virtualenv (if not already):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

3. Run the app (defaults to port `5000`):

```powershell
.\.venv\Scripts\python.exe -m app.main
```

4. Open your browser at `http://localhost:5000`

## Environment

Set these environment variables as needed:

- `CLAIM_BUCKET` — S3 bucket used for uploads (default: `claim-documents-poc-S`)
- `AWS_REGION` — AWS region for S3 and textract (default: `ap-south-1`)
- `PORT` — override the listening port (default: `5000`)

## Notes

- The app runs `scripts/local_extract.py` and `scripts/local_summary.py` either via import (preferred) or as subprocess fallbacks.
- To enable LLM-based extraction, configure `app/bedrock_client.py` with credentials and set the appropriate flags.

---

If you want, I can add a sample `static/images/claim_flow.png` placeholder image file and commit it for you.

