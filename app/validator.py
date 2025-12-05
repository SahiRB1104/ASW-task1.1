import re
from dateutil.parser import parse

POLICY_RE = re.compile(r"^[A-Z0-9\-]{5,}$")

def validate_extraction(d: dict) -> dict:
    issues = []
    score = 1.0

    if not d.get("policy_number") or not POLICY_RE.match(str(d.get("policy_number"))):
        issues.append("policy_number_missing_or_invalid")
        score -= 0.4

    try:
        if d.get("date_of_loss"):
            parse(d.get("date_of_loss"))
        else:
            issues.append("date_of_loss_missing")
            score -= 0.3
    except Exception:
        issues.append("date_of_loss_unparseable")
        score -= 0.3

    try:
        amt = d.get("amount_claimed")
        if amt is None:
            issues.append("amount_missing")
            score -= 0.3
        else:
            if float(str(amt).replace(",", "").replace("₹", "").replace("$", "").strip()) <= 0:
                issues.append("amount_non_positive")
                score -= 0.3
    except Exception:
        issues.append("amount_unparseable")
        score -= 0.3

    valid = score >= 0.7
    return {"valid": valid, "score": max(0.0, score), "issues": issues}
