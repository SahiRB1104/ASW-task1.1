from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class LocalRetriever:
    def __init__(self, chunks):
        self.chunks = chunks
        self.vectorizer = TfidfVectorizer().fit(chunks if chunks else [""])
        self.matrix = self.vectorizer.transform(chunks if chunks else [""])

    def retrieve(self, query, top_k=3):
        qv = self.vectorizer.transform([query])
        sims = cosine_similarity(qv, self.matrix)[0]
        idx = np.argsort(sims)[::-1][:top_k]
        return [{"chunk": self.chunks[i], "score": float(sims[i])} for i in idx]
