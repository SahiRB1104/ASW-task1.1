import re
from heapq import nlargest

LOCAL_TXT = "local_copy.txt"

def build_summary(text, top_n=3):
    words = re.findall(r"\w+", text.lower())
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    sentences = re.split(r'(?<=[.!?]) +', text)
    scored = []
    for s in sentences:
        score = sum(freq.get(w.lower(), 0) for w in re.findall(r'\w+', s))
        scored.append((score, s.strip()))
    top_sentences = [s for _, s in nlargest(top_n, scored)]
    return " ".join(top_sentences)

if __name__ == "__main__":
    try:
        with open(LOCAL_TXT, "r", encoding="utf-8") as f:
            txt = f.read()
    except FileNotFoundError:
        print(f"{LOCAL_TXT} not found. Please download processed text from S3 first.")
        exit(1)
    summary = build_summary(txt, top_n=3)
    print("=== SUMMARY ===")
    print(summary)
