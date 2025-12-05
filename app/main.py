# app/main.py
import os
import sys
import uuid
import json
import subprocess
from flask import Flask, request, jsonify, render_template
import boto3
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

BUCKET = os.environ.get("CLAIM_BUCKET", "aws-task1-1-sahil")
REGION = os.environ.get("AWS_REGION", "ap-south-1")

s3 = boto3.client("s3", region_name=REGION)

app = Flask(__name__, static_folder="static", template_folder="templates")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "no file provided"}), 400
    f = request.files["file"]
    filename = secure_filename(f.filename)
    key = f"raw/{uuid.uuid4()}_{filename}"
    try:
        s3.upload_fileobj(f, BUCKET, key)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"s3_key": key}), 201


@app.route("/process", methods=["POST"])
def process_file():
    """
    POST JSON: { "s3_key": "raw/....pdf" }
    This will:
      - set SAMPLE_S3_KEY env and call textract worker (blocking)
      - after worker finishes, fetch processed txt from S3 and run local extractor + summarizer
      - return JSON with summary & extraction
    """
    data = request.get_json(force=True)
    s3_key = data.get("s3_key")
    if not s3_key:
        return jsonify({"error": "s3_key required"}), 400

    # Build env for subprocess — copy current env and ensure same python interpreter
    env = os.environ.copy()
    # Force subprocess to use the same Python interpreter that's running Flask (this ensures venv packages are available)
    env_python = sys.executable
    env["PYTHON"] = env_python
    env["SAMPLE_S3_KEY"] = s3_key
    env["AWS_REGION"] = os.environ.get("AWS_REGION", REGION)

    # 1) Run textract worker as subprocess (module form so imports resolve)
    cmd = [env_python, "-m", "app.textract_worker"]
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            return jsonify({
                "error": "textract failed",
                "stdout": proc.stdout,
                "stderr": proc.stderr
            }), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "textract timed out"}), 500

    # 2) Determine processed key name (textract_worker writes processed/<name>.txt)
    processed_key = s3_key.replace("raw/", "processed/").rsplit(".", 1)[0] + ".txt"

    # 3) Download processed text locally
    local_txt = "local_copy.txt"
    try:
        s3.download_file(BUCKET, processed_key, local_txt)
    except Exception as e:
        return jsonify({"error": f"failed to download processed text: {e}"}), 500

    # 4) Run local_summary and local_extract modules using same interpreter
    try:
        sum_proc = subprocess.run([env_python, "-m", "scripts.local_summary"],
                                   capture_output=True, text=True, env=env, timeout=60)
        summary = sum_proc.stdout.strip()

        ext_proc = subprocess.run([env_python, "-m", "scripts.local_extract"],
                                   capture_output=True, text=True, env=env, timeout=60)
        ext_out = ext_proc.stdout
        # extract JSON substring printed by the extractor
        if "{" in ext_out and "}" in ext_out:
            json_part = ext_out[ext_out.find("{"): ext_out.rfind("}")+1]
            extraction = json.loads(json_part)
        else:
            extraction = {"error": "no extraction JSON found", "raw_output": ext_out}
    except Exception as e:
        return jsonify({"error": f"local processing failed: {e}"}), 500

    return jsonify({
        "s3_processed_key": processed_key,
        "summary": summary,
        "extraction": extraction
    })


if __name__ == "__main__":
    # Use 0.0.0.0 if you want access from other machines; keep 127.0.0.1 for local-only
    app.run(debug=True, port=8080)
