# scripts/local_extract.py
#

import re
from dateutil.parser import parse
import os
import json

LOCAL_TXT = "local_copy.txt"
TOP_K = 6                 # search top 6 chunks first
CHUNK_SIZE = 1000         # must match chunking in query_local.py

# ---------- Utilities ----------
def load_text():
    with open(LOCAL_TXT, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def chunk_text(text, chunk_size=CHUNK_SIZE):
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

# ---------- Date helpers (context-aware) ----------
def parse_date_str(s):
    """
    Try strict formats first, then validated fuzzy parse.
    Returns 'YYYY-MM-DD' or None.
    """
    if not s:
        return None
    s_try = s.strip()
    s_try = re.sub(r'(\d)(st|nd|rd|th)', r'\1', s_try, flags=re.IGNORECASE)

    # direct ISO-like
    m_iso = re.search(r"\b(20\d{2})[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])\b", s_try)
    if m_iso:
        return f"{m_iso.group(1)}-{m_iso.group(2)}-{m_iso.group(3)}"

    from datetime import datetime
    fmts = [
        "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %B %Y",
        "%d %b %Y", "%B %d %Y", "%b %d %Y", "%d.%m.%Y",
        "%d %B, %Y", "%d %b, %Y"
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(s_try, fmt).date()
            return dt.isoformat()
        except Exception:
            pass

    # fallback: fuzzy but validate year
    try:
        dt = parse(s_try, dayfirst=False, fuzzy=True).date()
        if 1900 <= dt.year <= 2100:
            return dt.isoformat()
    except Exception:
        pass
    return None


def find_candidate_dates(text):
    """
    Return list of (match_text, start_index, end_index) for date-like tokens found in text.
    """
    patterns = [
        r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2})\b",                              # 2025-11-28
        r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b",                              # 28/11/2025 or 28-11-25
        r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4})\b",  # 28 November 2025
        r"\b([0-3]?\d(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b",
        r"\b(\d{4})\b"  # last-resort capture year alone
    ]
    matches = []
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.I):
            matches.append((m.group(1), m.start(1), m.end(1)))
    return matches

# ---------- Amount helpers ----------
def normalize_amount(s):
    """
    Normalize amounts to 'INR <number>.2f' where possible.
    Accepts strings like 'INR 45,000', 'Amount Claimed: INR\n45,000', '45000 INR', '₹45,000'
    Returns None if no numeric amount found.
    """
    if not s:
        return None
    # unify whitespace
    s = re.sub(r"\r\n?", "\n", s)
    s = re.sub(r"\n+", " ", s).strip()

    # 1) explicit "Amount Claimed" label with optional currency
    m_label = re.search(r"Amount\s*(?:Claimed)?[:\s-]*(?:INR|Rs\.?|₹)?\s*([0-9,]+(?:\.\d{1,2})?)", s, flags=re.I)
    if m_label:
        num = m_label.group(1).replace(",", "")
        try:
            val = float(num)
            return f"INR {val:.2f}"
        except Exception:
            return num

    # 2) currency + number e.g. "INR 45,000" or "₹45,000"
    m_cur = re.search(r"(?:INR|Rs\.?|₹)\s*([0-9,]+(?:\.\d{1,2})?)", s, flags=re.I)
    if m_cur:
        num = m_cur.group(1).replace(",", "")
        try:
            val = float(num)
            return f"INR {val:.2f}"
        except:
            return num

    # 3) fallback: any number present
    s_clean = s.replace(",", "")
    m_any = re.search(r"([0-9]+(?:\.\d{1,2})?)", s_clean)
    if m_any:
        try:
            val = float(m_any.group(1))
            # If currency mentioned anywhere, return with INR
            if re.search(r"\b(INR|Rs\.?|₹|rupees)\b", s, flags=re.I):
                return f"INR {val:.2f}"
            return f"{val:.2f}"
        except:
            return m_any.group(1)
    return None

# ---------- Pattern lists ----------
POLICY_PATTERNS = [
    r"Policy\s*(?:No|Number|#)?[:\s-]*([A-Z0-9\-\/]{4,})",
    r"Policy\s*[:\s-]*([A-Z0-9\-\/]{4,})",
    r"\b([A-Z]{2,4}\d{2,8})\b"
]

CLAIMANT_PATTERNS = [
    r"Claimant Name[:\s-]*([A-Z][A-Za-z ,.'-]{2,80})",
    r"Claimant[:\s-]*([A-Z][A-Za-z ,.'-]{2,80})",
    r"Insured Name[:\s-]*([A-Z][A-Za-z ,.'-]{2,80})",
    r"Insured[:\s-]*([A-Z][A-Za-z ,.'-]{2,80})",
    r"Complainant[:\s-]*([A-Z][A-Za-z ,.'-]{2,80})"
]

DATE_PATTERNS = [
    r"(?:Date of Loss|Loss Date|Date of Accident|Date)[:\s-]*([0-3]?\d[-/ .][A-Za-z0-9]{1,11}[-/ .]\d{2,4})",
    r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
    r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})"
]

AMOUNT_PATTERNS = [
    r"(?:Amount\s*(?:Claimed)?|Claim\s*Amount)[:\s-]*([₹\$\£]?\s?[0-9,]+(?:\.\d{1,2})?)",
    r"(INR|Rs\.?|₹)\s*([0-9,]+(?:\.\d{1,2})?)",
    r"([0-9,]+(?:\.\d{1,2})?\s?(?:INR|Rs\.|rupees))",
    r"([₹\$\£]\s?[0-9,]+(?:\.\d{1,2})?)"
]

# ---------- Search helpers ----------
def search_patterns(text, patterns):
    """
    Prefer capture groups that contain digits (for amounts) or letters (for names).
    Prevents returning 'INR' when the second group contains the numeric part.
    """
    for p in patterns:
        m = re.search(p, text, flags=re.I)
        if m:
            groups = m.groups() if m.groups() else ()
            if groups:
                # 1) prefer group with digits
                for g in groups:
                    if g and re.search(r"\d", g):
                        return g.strip()
                # 2) prefer group with letters (names/policies)
                for g in groups:
                    if g and re.search(r"[A-Za-z]", g):
                        return g.strip()
                # 3) fallback to first non-empty
                for g in groups:
                    if g:
                        return g.strip()
            return m.group(0).strip()
    return None

# Optional local retriever (safe import)
try:
    from app.local_retriever import LocalRetriever
except Exception:
    LocalRetriever = None

def search_in_chunks(text, query, top_k=TOP_K):
    chunks = chunk_text(text)
    if LocalRetriever:
        retriever = LocalRetriever(chunks)
        hits = retriever.retrieve(query, top_k=top_k)
        return [h["chunk"] for h in hits if h.get("chunk") and h["chunk"].strip()]
    else:
        return chunks[:top_k]

# ---------- Person-name heuristic ----------
def plausible_person(s):
    if not s:
        return False
    s = s.strip()
    if re.match(r"^(name|claimant|insured|compliant|complainant)$", s, flags=re.I):
        return False
    toks = s.split()
    if not (2 <= len(toks) <= 5):
        return False
    if not re.search(r"[A-Za-z]", s):
        return False
    if re.match(r"^(amount|policy|date|claim|reference)\b", s, flags=re.I):
        return False
    return True

# ---------- Main extraction ----------
def extract_from_text(text):
    results = {
        "policy_number": None,
        "claimant_name": None,
        "date_of_loss": None,
        "amount_claimed": None,
        "claim_description": None
    }

    # normalize text
    text_norm = text.replace("\r\n", "\n")
    # join lines where currency token at end/start split lines
    text_norm = re.sub(r"\n\s*(INR|Rs\.?|₹)\s*\n", r" \1 ", text_norm, flags=re.I)

    # candidate pool
    pool = search_in_chunks(text_norm, "policy number claimant name date of loss amount claimed", top_k=TOP_K)
    pool_text = "\n\n".join(pool)

    # 1) Policy
    p = search_patterns(pool_text, POLICY_PATTERNS)
    if not p:
        p = search_patterns(text_norm, POLICY_PATTERNS)
    results["policy_number"] = p

    # 2) Claimant
    c = search_patterns(pool_text, CLAIMANT_PATTERNS)
    if not c:
        c = search_patterns(text_norm, CLAIMANT_PATTERNS)
    # fallback: label-based next-line but validate plausibility
    if not c:
        lines = [ln.rstrip() for ln in text_norm.splitlines() if ln.strip()]
        for i, ln in enumerate(lines):
            if re.search(r"\b(Name|Claimant|Insured|Complainant)\b", ln, flags=re.I):
                # if colon and a value exists, take it (only if plausible)
                if ":" in ln:
                    rest = ln.split(":", 1)[1].strip()
                    if rest and plausible_person(rest):
                        c = rest
                        break
                # otherwise inspect following lines for a plausible name
                for j in range(i+1, min(i+4, len(lines))):
                    cand = lines[j].strip()
                    if plausible_person(cand):
                        c = cand
                        break
                if c:
                    break
    results["claimant_name"] = c

    # 3) Date — context-aware: prefer tokens close to "Date of Loss"
    label_idx = text_norm.lower().find("date of loss")
    pool_candidates = find_candidate_dates(pool_text) if pool_text else []
    full_candidates = find_candidate_dates(text_norm)
    candidates = pool_candidates if pool_candidates else full_candidates

    chosen_date = None
    if candidates:
        if label_idx != -1:
            # pick candidate closest to label index
            best = None
            best_dist = None
            for txt, start, end in candidates:
                dist = abs(start - label_idx)
                if best is None or dist < best_dist:
                    best = (txt, start, end)
                    best_dist = dist
            if best:
                chosen_date = parse_date_str(best[0])
        if not chosen_date:
            # fallback: try each candidate in order
            for txt, start, end in candidates:
                pd = parse_date_str(txt)
                if pd:
                    chosen_date = pd
                    break

    # ultimate fallback to previous pattern search
    if not chosen_date:
        d = search_patterns(pool_text, DATE_PATTERNS)
        if not d:
            d = search_patterns(text_norm, DATE_PATTERNS)
        chosen_date = parse_date_str(d) if d else None

    results["date_of_loss"] = chosen_date

    # 4) Amount
    a = search_patterns(pool_text, AMOUNT_PATTERNS)
    if not a:
        a = search_patterns(text_norm, AMOUNT_PATTERNS)
    if isinstance(a, tuple):
        a = " ".join([str(x) for x in a if x])
    results["amount_claimed"] = normalize_amount(a if a else text_norm)

    # 5) Claim description
    desc = None
    for ch in pool:
        if re.search(r"\b(damage|loss|cause|accident|reason|description)\b", ch, flags=re.I):
            desc = ch.strip()
            break
    if not desc:
        desc = text_norm.strip()[:1000]
    results["claim_description"] = desc

    return results

# ---------- CLI ----------
if __name__ == "__main__":
    if not os.path.exists(LOCAL_TXT):
        print(f"{LOCAL_TXT} not found. Please download processed text from S3 first.")
        exit(1)
    text = load_text()
    extracted = extract_from_text(text)
    print("=== EXTRACTED ===")
    print(json.dumps(extracted, indent=2, ensure_ascii=False))
