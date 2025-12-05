import os
import uuid
from flask import Flask, request, jsonify
import boto3
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load .env if available (local dev only)
load_dotenv()

# Config
BUCKET = os.environ.get("CLAIM_BUCKET", "aws-task1-1-sahil")
REGION = os.environ.get("AWS_REGION", "ap-south-1")

s3 = boto3.client("s3", region_name=REGION)

app = Flask(__name__)

@app.route("/ping")
def ping():
    return jsonify({"ok": True})

@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "no file provided"}), 400
    f = request.files["file"]
    filename = secure_filename(f.filename)
    key = f"raw/{uuid.uuid4()}_{filename}"
    s3.upload_fileobj(f, BUCKET, key)
    return jsonify({"s3_key": key}), 201

if __name__ == "__main__":
    # For development only
    app.run(debug=True, port=8080)
