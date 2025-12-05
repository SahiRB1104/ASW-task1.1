# Updated textract_worker.py
# Replaces / extends the original file uploaded by the user.
import os
import time
import json
import re
import boto3
from datetime import datetime
from dotenv import load_dotenv
from app.bedrock_client import create_embedding

load_dotenv()

REGION = os.environ.get("AWS_REGION", "ap-south-1")
BUCKET = os.environ.get("CLAIM_BUCKET", "aws-task1-1-sahil")

textract = boto3.client("textract", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)


def start_text_detection(s3_bucket, s3_key):
    resp = textract.start_document_text_detection(
        DocumentLocation={"S3Object": {"Bucket": s3_bucket, "Name": s3_key}}
    )
    return resp["JobId"]


def poll_job(job_id, poll_interval=5):
    while True:
        res = textract.get_document_text_detection(JobId=job_id)
        status = res.get("JobStatus")
        print("Textract job status:", status)
        if status in ("SUCCEEDED", "FAILED"):
            return res
        time.sleep(poll_interval)


def extract_text_from_blocks(res):
    lines = []
    for b in res.get("Blocks", []) or []:
        if b.get("BlockType") == "LINE" and "Text" in b:
            lines.append(b["Text"])
    return "\n".join(lines)


def chunk_text(text, chunk_size=1000):
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]


# --- NEW: field extraction utilities ---

def _clean_number_string(s: str) -> str:
    """Remove commas and stray characters from a numeric string."""
    return re.sub(r"[^\d\.]", "", s)


def _try_parse_date(date_str: str):
    """Try multiple common date formats; return 'YYYY-MM-DD' or None."""
    date_str = date_str.strip()
    # Common formats to try (expand if needed)
    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d %B %Y",    # 28 November 2025
        "%d %b %Y",    # 28 Nov 2025
        "%B %d %Y",    # November 28 2025
        "%b %d %Y",
        "%d %b, %Y",
        "%d %B, %Y",
        "%d.%m.%Y",
    ]
    # remove ordinal suffixes (1st, 2nd, 3rd, 4th)
    date_str = re.sub(r'(\d)(st|nd|rd|th)', r'\1', date_str, flags=re.IGNORECASE)
    for fmt in formats:
        try:
            d = datetime.strptime(date_str, fmt)
            return d.strftime("%Y-%m-%d")
        except Exception:
            continue
    # fallback: try to extract yyyy and assume if present
    m = re.search(r"(20\d{2})", date_str)
    if m:
        return m.group(1)
    return None


def extract_fields(text: str) -> dict:
    """
    Extract common claim fields from OCR text.
    Returns dict with keys:
    - policy_number
    - claimant_name
    - insured_name
    - contact
    - date_of_loss (YYYY-MM-DD or None)
    - location_of_loss
    - cause_of_loss
    - items_damaged
    - amount_claimed (normalized like 'INR 45000.00' or None)
    - claim_reference
    - raw_claim_description (a useful chunk or the whole text)
    """
    # Normalized lowercase for searching keywords, but keep original for captures
    text_lower = text.lower()

    def single_line_search(label_patterns):
        """Return line text matching any of the label patterns (case-insensitive)."""
        for line in text.splitlines():
            for pat in label_patterns:
                if re.search(pat, line, flags=re.IGNORECASE):
                    return line.strip()
        return None

    def search_after_label(label_regex):
        """Search 'Label: value' on the same line or next line(s)."""
        # First try same-line capture
        m = re.search(rf"{label_regex}\s*[:\-]\s*(.+)", text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # If pattern not on same line, check lines
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if re.search(label_regex, line, flags=re.IGNORECASE):
                # try next non-empty line
                for j in range(i, min(i+3, len(lines))):
                    candidate = re.sub(rf".*{label_regex}.*[:\-]?\s*", "", lines[j], flags=re.IGNORECASE).strip()
                    if candidate:
                        return candidate
                if i+1 < len(lines):
                    nxt = lines[i+1].strip()
                    if nxt:
                        return nxt
        return None

    # Policy number
    policy = search_after_label(r"(policy\s*number|policy\s*no\.?|policy\s*#)")
    if not policy:
        # try a short uppercase token pattern
        m = re.search(r"\b(P[Ll][- ]?\d{3,})\b", text)
        policy = m.group(1) if m else None

    # Claimant / Insured
    claimant = search_after_label(r"(claimant\s*name|claimant)")
    insured = search_after_label(r"(insured\s*name|insured)")

    # Contact
    contact = search_after_label(r"(contact|phone|mobile)")
    if contact:
        # extract phone like tokens
        m = re.search(r"(\+?\d[\d\-\s]{7,}\d)", contact)
        if m:
            contact = m.group(1).strip()

    # Date of Loss
    date_val = search_after_label(r"(date\s*of\s*loss|date\s*of\s*damage|date\s*of\s*incident|date)")
    if date_val:
        parsed_date = _try_parse_date(date_val)
    else:
        # try to find any date-like token near words 'loss' or 'damage'
        m = re.search(r"(?:loss|damage|incident)[^\n]{0,40}(\d{1,2}(?:[\/\-\.\s]\w+){1,2}\d{2,4}|20\d{2})", text, flags=re.IGNORECASE)
        parsed_date = _try_parse_date(m.group(1)) if m else None

    # Location
    location = search_after_label(r"(location\s*of\s*loss|location|place)")

    # Cause
    cause = search_after_label(r"(cause\s*of\s*loss|cause|reason)")

    # Items damaged
    items = search_after_label(r"(items\s*damaged|items\s*loss|items|damaged)")

    # Claim reference
    claim_ref = search_after_label(r"(claim\s*reference|reference|claim\s*ref|reference\s*no\.?)")
    if not claim_ref:
        m = re.search(r"\bCLM[-\s]?\d{3,}\b", text, flags=re.IGNORECASE)
        claim_ref = m.group(0) if m else None

    # Amount claimed - robust patterns
    amount = None
    # Primary pattern: "Amount Claimed: INR 45,000"
    m = re.search(r"(?i)(?:amount\s*claimed|amount)\s*[:\-]?\s*(INR|Rs\.?|₹)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)", text)
    if m:
        curr = m.group(1) or "INR"
        num = _clean_number_string(m.group(2))
        try:
            amt_val = float(num) if "." in num else float(int(float(num)))
            amount = f"INR {amt_val:,.2f}".replace(",", "")  # we'll store normalized without formatting commas
            # store without commas: INR 45000.00
            amount = f"INR {amt_val:.2f}"
        except Exception:
            amount = f"INR {num}"
    else:
        # fallback: any INR/Rs/₹ followed by number
        m2 = re.search(r"(INR|Rs\.?|₹)\s*([0-9][0-9,]*(?:\.\d{1,2})?)", text, flags=re.IGNORECASE)
        if m2:
            num = _clean_number_string(m2.group(2))
            try:
                amt_val = float(num)
                amount = f"INR {amt_val:.2f}"
            except Exception:
                amount = f"INR {num}"

    # Description - take the full text or a trimmed relevant chunk
    raw_desc = text.strip()

    return {
        "policy_number": policy,
        "claimant_name": claimant,
        "insured_name": insured,
        "contact": contact,
        "date_of_loss": parsed_date,
        "location_of_loss": location,
        "cause_of_loss": cause,
        "items_damaged": items,
        "amount_claimed": amount,
        "claim_reference": claim_ref,
        "raw_claim_description": raw_desc,
    }


# --- End extraction utilities ---


if __name__ == "__main__":
    # Replace sample_key with an actual S3 key you got from upload
    sample_key = os.environ.get("SAMPLE_S3_KEY", "raw/sample-claim.pdf")
    print("Processing", sample_key)
    job = start_text_detection(BUCKET, sample_key)
    res = poll_job(job)
    if res.get("JobStatus") == "SUCCEEDED":
        text = extract_text_from_blocks(res)
        processed_key = sample_key.replace("raw/", "processed/").rsplit(".", 1)[0] + ".txt"
        s3.put_object(Bucket=BUCKET, Key=processed_key, Body=text.encode("utf-8"))
        print("Wrote processed text to", processed_key)

        # --- NEW: write extracted fields JSON to S3 ---
        extracted = extract_fields(text)
        json_key = processed_key.replace(".txt", ".extraction.json")
        s3.put_object(Bucket=BUCKET, Key=json_key, Body=json.dumps(extracted, indent=2).encode("utf-8"))
        print("Wrote extraction JSON to", json_key)
        # --- end new ---

        # chunk + create embeddings (embedding may be None if Bedrock disabled)
        chunks = chunk_text(text)
        embeddings = []
        for c in chunks:
            vec = create_embedding(c)
            embeddings.append({"chunk": c, "vector": vec})
        emb_key = processed_key.replace(".txt", ".emb.json")
        s3.put_object(Bucket=BUCKET, Key=emb_key, Body=json.dumps(embeddings).encode("utf-8"))
        print("Wrote embeddings to", emb_key)
    else:
        print("Textract failed or did not finish.")
