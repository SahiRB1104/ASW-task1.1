from jinja2 import Template

EXTRACTION_TEMPLATE = """
SYSTEM: You are a claims assistant. Extract the following fields into strict JSON:
policy_number, claimant_name, date_of_loss, amount_claimed, claim_description.
If a field is not present, set it to null. Only return JSON — no extra text.

CONTEXT:
{{ context }}

DOCUMENT:
{{ document }}
"""

SUMMARY_TEMPLATE = """
SYSTEM: You are a claims assistant. Summarize the claim in 3 brief sentences,
and highlight any potential issues (e.g., missing policy number, unusual amount).

CONTEXT:
{{ context }}

DOCUMENT:
{{ document }}
"""

def render_extraction(context: str, document: str) -> str:
    t = Template(EXTRACTION_TEMPLATE)
    return t.render(context=context or "", document=document or "")

def render_summary(context: str, document: str) -> str:
    t = Template(SUMMARY_TEMPLATE)
    return t.render(context=context or "", document=document or "")
