# scripts/local_extract.py
import re
from dateutil.parser import parse
from app.local_retriever import LocalRetriever
import os
import json

LOCAL_TXT = "local_copy.txt"
TOP_K = 6                 # search top 6 chunks first
CHUNK_SIZE = 1000         # must match chunking in query_local.py

def load_text():
    with open(LOCAL_TXT, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def chunk_text(text, chunk_size=CHUNK_SIZE):
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

def safe_parse_date(s):
    try:
        return str(parse(s, dayfirst=False, fuzzy=True).date())
    except Exception:
        return None

def normalize_amount(s):
    if not s:
        return None
    s = s.replace(",", "").strip()
    # remove words
    s = re.sub(r"(inr|rs\.|rupees|rs|amount|claim|claimed)[:\s]*", "", s, flags=re.I)
    m = re.search(r"([₹$]\s?\d+(\.\d+)?|\d+(\.\d+)?\s?(?:INR|Rs\.?|rupees)?)", s, re.I)
    if m:
        return m.group(0).strip()
    # fallback: digits
    m2 = re.search(r"\d{3,}(?:\.\d{1,2})?", s)
    return m2.group(0) if m2 else None

# Multiple candidate patterns per field
POLICY_PATTERNS = [
    r"Policy\s*(?:No|Number|#)?[:\s-]*([A-Z0-9\-\/]{4,})",
    r"Policy\s*[:\s-]*([A-Z0-9\-\/]{4,})",
    r"Policy\s*ID[:\s-]*([A-Z0-9\-\/]{4,})",
    r"Policy\s*#[:\s-]*([A-Z0-9\-\/]{4,})",
    r"\b([A-Z]{2,4}\d{2,8})\b"  # fallback: alphanum like AB12345
]

CLAIMANT_PATTERNS = [
    r"Claimant[:\s-]*([A-Z][A-Za-z ,.'-]{2,80})",
    r"Name of claimant[:\s-]*([A-Z][A-Za-z ,.'-]{2,80})",
    r"Insured[:\s-]*([A-Z][A-Za-z ,.'-]{2,80})",
    r"Insured Name[:\s-]*([A-Z][A-Za-z ,.'-]{2,80})",
    r"Complainant[:\s-]*([A-Z][A-Za-z ,.'-]{2,80})",
]

DATE_PATTERNS = [
    r"(?:Date of Loss|Loss Date|Date of Accident|Date)[:\s-]*([0-3]?\d[-/ .][A-Za-z0-9]{1,11}[-/ .]\d{2,4})",
    r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
    r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
]

AMOUNT_PATTERNS = [
    r"([₹\$\£]\s?[0-9,]+(?:\.\d{1,2})?)",
    r"([0-9,]+(?:\.\d{1,2})?\s?(?:INR|Rs\.|rupees))",
    r"Amount\s*(?:Claimed)?[:\s-]*([₹\$\d,\.]+)",
    r"Claim\s*Amount[:\s-]*([₹\$\d,\.]+)"
]

def search_patterns(text, patterns):
    for p in patterns:
        m = re.search(p, text, flags=re.I)
        if m:
            # choose first non-empty group
            for g in m.groups():
                if g:
                    return g.strip()
            return m.group(0).strip()
    return None

def search_in_chunks(text, query, top_k=TOP_K):
    chunks = chunk_text(text)
    retriever = LocalRetriever(chunks)
    hits = retriever.retrieve(query, top_k=top_k)
    return [h["chunk"] for h in hits if h["chunk"].strip()]

def extract_from_text(text):
    # First search focused chunks for each field
    results = {"policy_number": None, "claimant_name": None, "date_of_loss": None, "amount_claimed": None, "claim_description": None}

    # Candidate pool: top chunks for a general information query
    pool = search_in_chunks(text, "policy number claimant name date of loss amount claimed", top_k=TOP_K)
    pool_text = "\n\n".join(pool)

    # 1) Policy
    p = search_patterns(pool_text, POLICY_PATTERNS)
    if not p:
        p = search_patterns(text, POLICY_PATTERNS)
    results["policy_number"] = p

    # 2) Claimant name
    c = search_patterns(pool_text, CLAIMANT_PATTERNS)
    if not c:
        # fallback: try lines that start with 'Name' or capitalized lines near words 'claim' or 'insured'
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        for i, ln in enumerate(lines):
            if re.search(r"\b(Name|Claimant|Insured|Complainant)\b", ln, flags=re.I):
                # pick next non-empty token sequence
                rest = ln.split(":",1)[-1].strip()
                if rest:
                    c = rest
                    break
                # try next line
                if i+1 < len(lines):
                    nxt = lines[i+1].strip()
                    if len(nxt.split()) <= 6 and any(ch.isalpha() for ch in nxt):
                        c = nxt
                        break
    results["claimant_name"] = c

    # 3) Date
    d = search_patterns(pool_text, DATE_PATTERNS)
    if not d:
        d = search_patterns(text, DATE_PATTERNS)
    d_norm = safe_parse_date(d) if d else None
    results["date_of_loss"] = d_norm

    # 4) Amount
    a = search_patterns(pool_text, AMOUNT_PATTERNS)
    if not a:
        a = search_patterns(text, AMOUNT_PATTERNS)
    a_norm = normalize_amount(a)
    results["amount_claimed"] = a_norm

    # 5) Claim description: take the chunk with highest similarity that contains 'damage' or 'loss' or 'cause'
    desc = None
    for ch in pool:
        if re.search(r"\b(damage|loss|cause|accident|reason|description)\b", ch, flags=re.I):
            desc = ch.strip()[:1000]
            break
    results["claim_description"] = desc

    return results

if __name__ == "__main__":
    if not os.path.exists(LOCAL_TXT):
        print(f"{LOCAL_TXT} not found. Please download processed text from S3 first.")
        exit(1)
    text = load_text()
    extracted = extract_from_text(text)
    print("=== EXTRACTED ===")
    print(json.dumps(extracted, indent=2, ensure_ascii=False))
