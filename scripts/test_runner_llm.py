# scripts/test_runner_llm.py
import os, csv, json, requests, time

FLASK_URL = os.environ.get("FLASK_PROCESS_URL", "http://127.0.0.1:8080/process")
SAMPLE_KEYS = [
    "raw/sample-claim-1.pdf",
    "raw/sample-claim-2.pdf",
    "raw/sample-claim-3.pdf"
]
OUT_CSV = os.environ.get("OUT_CSV", "llm_compare_results.csv")

def call_process(s3_key):
    resp = requests.post(FLASK_URL, json={"s3_key": s3_key}, timeout=900)
    resp.raise_for_status()
    return resp.json()

def main():
    rows = []
    for k in SAMPLE_KEYS:
        print("Processing", k)
        start = time.time()
        try:
            res = call_process(k)
        except Exception as e:
            print("Error calling process:", e)
            rows.append({"s3_key": k, "error": str(e)})
            continue
        latency = time.time() - start
        local_ex = res.get("local", {}).get("extraction")
        local_sum = res.get("local", {}).get("summary")
        llm_ex = res.get("llm", {}).get("extraction")
        llm_sum = res.get("llm", {}).get("summary")
        rows.append({
            "s3_key": k,
            "latency_s": round(latency,2),
            "local_extraction": json.dumps(local_ex, ensure_ascii=False),
            "local_summary": local_sum,
            "llm_extraction": json.dumps(llm_ex, ensure_ascii=False),
            "llm_summary": llm_sum
        })
    # write CSV
    with open(OUT_CSV, "w", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["s3_key"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print("Wrote", OUT_CSV)

if __name__ == "__main__":
    main()
