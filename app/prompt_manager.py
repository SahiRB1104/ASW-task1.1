# app/prompt_manager.py
"""
PromptTemplateManager - small wrapper around Jinja2 templates for extraction & summary prompts.
If Jinja2 is not installed, falls back to Python .format string rendering.
"""

from typing import Optional
try:
    from jinja2 import Template
    _HAS_JINJA = True
except Exception:
    _HAS_JINJA = False

EXTRACTION_TEMPLATE = """{{ instruction }}

DOCUMENT:
{{ document }}
"""

SUMMARY_TEMPLATE = """{{ instruction }}

DOCUMENT:
{{ document }}
"""

EXTRACTION_TEMPLATE_JSON = """{{ instruction }}

# Return only a single JSON object (no additional text). Schema:
# {
#   "policy_number": <string or null>,
#   "claimant_name": <string or null>,
#   "date_of_loss": <YYYY-MM-DD or null>,
#   "amount_claimed": <string numeric or null>,
#   "claim_description": <string or null>
# }

DOCUMENT:
{{ document }}
"""

class PromptTemplateManager:
    def __init__(self, use_json_extraction: bool = True):
        # choose the extraction template (JSON schema) for more reliable parseable output
        self.use_json_extraction = use_json_extraction
        if _HAS_JINJA:
            self.templates = {
                "extraction": Template(EXTRACTION_TEMPLATE_JSON if use_json_extraction else EXTRACTION_TEMPLATE),
                "summary": Template(SUMMARY_TEMPLATE)
            }
        else:
            # fallback: simple format strings
            self.templates = {
                "extraction": EXTRACTION_TEMPLATE_JSON if use_json_extraction else EXTRACTION_TEMPLATE,
                "summary": SUMMARY_TEMPLATE
            }

    def render(self, kind: str, instruction: str, context: Optional[str], document: str) -> str:
        """
        Render a template.
        - kind: "extraction" or "summary"
        - instruction: the instruction text to include
        - context: optional extra context (unused by default templates)
        - document: the document text to send to the model
        """
        if kind not in self.templates:
            raise ValueError(f"unknown template kind: {kind}")

        tpl = self.templates[kind]
        if _HAS_JINJA:
            return tpl.render(instruction=instruction, context=context or "", document=document or "")
        else:
            # fallback formatting
            return tpl.replace("{{ instruction }}", instruction).replace("{{ context }}", context or "").replace("{{ document }}", document or "")
