import os
import time
import json
import boto3
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
