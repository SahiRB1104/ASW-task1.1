# app/main.py
import os
import uuid
import boto3
import subprocess
import json
import re
from flask import Flask, request, jsonify, render_template_string

# Should exist in your repo
from app import bedrock_client
from app.prompt_manager import PromptTemplateManager
from app.model_invoker import ModelInvoker

# ENV
CLAIM_BUCKET = os.environ.get("CLAIM_BUCKET", "claim-documents-poc-S")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")

s3 = boto3.client("s3", region_name=AWS_REGION)

app = Flask(__name__, static_folder=None)
ptm = PromptTemplateManager()
invoker = ModelInvoker()

# Simple UI HTML (keeps same look as your screenshot)
INDEX_HTML = """
<!doctype html>
<title>Claim Processing PoC</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css" rel="stylesheet">
<div class="container" style="max-width:840px;margin-top:36px;">
  <div class="card p-4 shadow-sm">
    <h3>Claim Processing PoC</h3>
    <form id="uploadForm" method="post" enctype="multipart/form-data" action="/upload">
      <div class="mb-2">
        <input type="file" name="file" />
        <button class="btn btn-primary btn-sm" type="submit">Upload</button>
      </div>
    </form>
    <div id="uploadResult"></div>
    <hr/>
    <form id="processForm" method="post" action="/process">
      <div class="mb-2">
        <label>S3 key (from upload):</label>
        <input class="form-control" type="text" id="s3_key" name="s3_key" />
      </div>
      <button class="btn btn-primary btn-sm" type="submit">Run Textract & Extract</button>
    </form>
    <hr/>
    <div id="output">
      <h4>Summary</h4>
      <pre id="summary_box" style="background:#f7f7f7;padding:12px;border-radius:6px;max-height:320px;overflow:auto;"></pre>
      <h4>Extraction</h4>
      <pre id="extraction_box" style="background:#f7f7f7;padding:12px;border-radius:6px;max-height:200px;overflow:auto;"></pre>
    </div>
  </div>
</div>

<script>
document.getElementById('uploadForm').onsubmit = async function(e) {
  e.preventDefault();
  const form = e.target;
  const fd = new FormData(form);
  const res = await fetch('/upload', {method:'POST', body: fd});
  const j = await res.json();
  document.getElementById('uploadResult').innerText = 'Uploaded: ' + j.s3_key;
  document.getElementById('s3_key').value = j.s3_key;
}

document.getElementById('processForm').onsubmit = async function(e) {
  e.preventDefault();
  const s3key = document.getElementById('s3_key').value;
  document.getElementById('summary_box').innerText = 'Processing...';
  document.getElementById('extraction_box').innerText = '';
  const res = await fetch('/process', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({s3_key: s3key})});
  const j = await res.json();
  // populate UI with both local and llm results
  const localSummary = j.local && j.local.summary ? j.local.summary : '';
  const localExtract = j.local && j.local.extraction ? JSON.stringify(j.local.extraction, null, 2) : '';
  const llmSummary = j.llm && j.llm.summary ? j.llm.summary : '';
  const llmExtract = j.llm && j.llm.extraction ? JSON.stringify(j.llm.extraction, null, 2) : '';
  let summaryText = "=== LOCAL SUMMARY ===\\n" + localSummary + "\\n\\n=== LLM SUMMARY ===\\n" + llmSummary;
  let extractText = "=== LOCAL EXTRACTION ===\\n" + localExtract + "\\n\\n=== LLM EXTRACTION ===\\n" + llmExtract;
  document.getElementById('summary_box').innerText = summaryText;
  document.getElementById('extraction_box').innerText = extractText;
}
</script>
"""

@app.route("/", methods=["GET"])
def index():
    return render_template_string(INDEX_HTML)

@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f:
        return jsonify({"error":"no file provided"}), 400
    fname = f.filename or "upload.pdf"
    uid = str(uuid.uuid4())
    s3_key = f"raw/{uid}_{fname}"
    # upload to S3
    s3.upload_fileobj(f, CLAIM_BUCKET, s3_key)
    return jsonify({"s3_key": s3_key})

def run_textract_worker(s3_key: str):
    env = os.environ.copy()
    env["SAMPLE_S3_KEY"] = s3_key
    # Use same Python interpreter as the running Flask process:
    import sys
    cmd = [sys.executable, "-m", "app.textract_worker"]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=900)
    if proc.returncode != 0:
        # include stderr in the exception so /process can return a helpful message
        raise RuntimeError(f"textract worker failed: {proc.stderr}")
    return proc.stdout


def download_processed_text(s3_key: str) -> str:
    """
    Transforms raw/<name>.pdf -> processed/<name>.txt and downloads the text file to /tmp and returns local path.
    """
    basename = s3_key.rsplit("/",1)[-1].rsplit(".",1)[0]
    processed_key = f"processed/{basename}.txt"
    local_path = f"/tmp/{basename}.txt"
    s3.download_file(CLAIM_BUCKET, processed_key, local_path)
    return local_path, processed_key

def run_local_extraction(local_txt_path: str):
    """
    Runs scripts/local_extract.py as module if available, captures stdout JSON or fallback to return text.
    """
    try:
        # Try to import function if scripts exposes it
        import importlib
        mod = importlib.import_module("scripts.local_extract")
        if hasattr(mod, "extract_from_text"):
            with open(local_txt_path, "r", encoding="utf-8") as f:
                txt = f.read()
            return mod.extract_from_text(txt)
    except Exception:
        pass

    # Fallback: call as subprocess (prints JSON)
    cmd = ["python", "-m", "scripts.local_extract", local_txt_path]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    out = proc.stdout.strip()
    try:
        return json.loads(out)
    except Exception:
        return {"raw": out}

def run_local_summary(local_txt_path: str):
    """
    Runs scripts/local_summary.py as module if available and returns text summary.
    """
    try:
        import importlib
        mod = importlib.import_module("scripts.local_summary")
        if hasattr(mod, "summarize_text"):
            with open(local_txt_path, "r", encoding="utf-8") as f:
                txt = f.read()
            return mod.summarize_text(txt)
    except Exception:
        pass

    # Fallback subprocess
    cmd = ["python", "-m", "scripts.local_summary", local_txt_path]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return proc.stdout.strip()

def try_parse_json_from_text(text: str):
    """
    Attempt to extract a JSON object from text (first {...} block)
    """
    m = re.search(r"(\{[\s\S]*\})", text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None

@app.route("/process", methods=["POST"])
def process():
    body = request.get_json() or {}
    s3_key = body.get("s3_key")
    if not s3_key:
        return jsonify({"error":"s3_key required"}), 400

    # 1) run textract worker (writes processed/<name>.txt and processed/<name>.extraction.json etc.)
    try:
        run_textract_worker(s3_key)
    except Exception as e:
        return jsonify({"error": f"textract worker failed: {str(e)}"}), 500

    # 2) download processed text
    try:
        local_txt_path, processed_s3_key = download_processed_text(s3_key)
    except Exception as e:
        return jsonify({"error": f"failed to download processed text: {str(e)}"}), 500

    # 3) local extraction & summary
    local_extraction = run_local_extraction(local_txt_path)
    local_summary = run_local_summary(local_txt_path)

    # 4) LLM extraction & summary (if enabled)
    llm_extraction = None
    llm_summary = None
    if getattr(bedrock_client, "ENABLE_BEDROCK", False):
        try:
            # Build extraction prompt - ask for JSON strictly
            extraction_prompt = ptm.render(
                "extraction",
                instruction=(
                    "Respond with a single JSON object (no surrounding text). "
                    "Extract fields: policy_number (string), claimant_name (string), "
                    "date_of_loss (YYYY-MM-DD or null), amount_claimed (numeric string or null), "
                    "claim_description (string or null). If missing set value null."
                ),
                context="",
                document=open(local_txt_path, "r", encoding="utf-8").read()
            )
            gen_res = invoker.generate(extraction_prompt)
            if gen_res.get("success"):
                raw = gen_res.get("text","")
                parsed = try_parse_json_from_text(raw)
                llm_extraction = parsed if parsed is not None else {"raw": raw}
            else:
                llm_extraction = {"error": "bedrock disabled or failed", "note": gen_res.get("note")}
        except Exception as e:
            llm_extraction = {"error": str(e)}

        try:
            summary_prompt = ptm.render(
                "summary",
                instruction=(
                    "Write a concise 3-sentence claim summary that includes policy number, claimant name, "
                    "date_of_loss and amount claimed if present. Then on a new line produce one-line 'Action items:' listing docs required."
                ),
                context="",
                document=open(local_txt_path, "r", encoding="utf-8").read()
            )
            sum_res = invoker.generate(summary_prompt)
            if sum_res.get("success"):
                llm_summary = sum_res.get("text")
            else:
                llm_summary = "bedrock disabled or failed"
        except Exception as e:
            llm_summary = f"llm summary error: {str(e)}"
    else:
        llm_extraction = {"note": "bedrock disabled"}
        llm_summary = "bedrock disabled"

    resp = {
        "s3_processed_key": processed_s3_key,
        "local": {"extraction": local_extraction, "summary": local_summary},
        "llm": {"extraction": llm_extraction, "summary": llm_summary}
    }
    return jsonify(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
