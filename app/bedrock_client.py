import os
import json
import boto3

# Safe-mode: only call Bedrock if env var ENABLE_BEDROCK is set to "1"
ENABLE_BEDROCK = os.environ.get("ENABLE_BEDROCK", "0") == "1"
REGION = os.environ.get("AWS_REGION", "ap-south-1")
BEDROCK_MODEL_SUMMARY = os.environ.get("BEDROCK_MODEL_SUMMARY", "REPLACE_LATER")
BEDROCK_MODEL_EMBED = os.environ.get("BEDROCK_MODEL_EMBED", "REPLACE_LATER")

# Create bedrock client only when needed
_bedrock_client = None
def _get_bedrock_client():
    global _bedrock_client
    if _bedrock_client is None:
        try:
            _bedrock_client = boto3.client("bedrock-runtime", region_name=REGION)
        except Exception:
            _bedrock_client = boto3.client("bedrock", region_name=REGION)
    return _bedrock_client

def invoke_model(model_id: str, input_payload: dict, timeout_seconds: int = 30):
    """
    Generic Bedrock invoke wrapper. Returns parsed JSON or raw text.
    Only runs if ENABLE_BEDROCK is True. Otherwise returns None.
    """
    if not ENABLE_BEDROCK:
        print("Bedrock calls are disabled (ENABLE_BEDROCK=0). Skipping invoke_model.")
        return None

    client = _get_bedrock_client()
    body = json.dumps(input_payload)
    response = client.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=body
    )
    raw = None
    if "body" in response:
        try:
            raw_bytes = response["body"].read()
            raw = raw_bytes.decode("utf-8")
        except Exception:
            raw = None
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            return raw
    return response

def create_embedding(text: str):
    """
    Return embedding vector or None.
    Must set BEDROCK_MODEL_EMBED and ENABLE_BEDROCK=1 to actually call.
    """
    if not ENABLE_BEDROCK:
        print("Bedrock disabled; create_embedding returning None")
        return None
    payload = {"input": text}
    res = invoke_model(BEDROCK_MODEL_EMBED, payload)
    if isinstance(res, dict):
        # common shapes: {"embedding": [...] } or {"embeddings":[...]}
        if "embedding" in res:
            return res["embedding"]
        if "embeddings" in res:
            return res["embeddings"][0]
    return None
