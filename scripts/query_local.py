import os
from app.local_retriever import LocalRetriever

# Ensure you have downloaded processed text to this file (from S3)
LOCAL_TXT = "local_copy.txt"

def chunk_text(text, chunk_size=1000):
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

if __name__ == "__main__":
    if not os.path.exists(LOCAL_TXT):
        print(f"{LOCAL_TXT} not found. Please download processed text from S3 first.")
        exit(1)
    with open(LOCAL_TXT, "r", encoding="utf-8") as f:
        text = f.read()
    chunks = chunk_text(text)
    retriever = LocalRetriever(chunks)
    query = "Extract claimant name, policy number, date of loss and amount claimed"
    top = retriever.retrieve(query, top_k=4)
    for i, item in enumerate(top, 1):
        print(f"=== Chunk {i} (score {item['score']:.3f}) ===")
        print(item["chunk"][:800])
        print()
