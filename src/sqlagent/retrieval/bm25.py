import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

K1 = 1.5
B = 0.75
_TOKEN = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    tokens = []
    for word in _TOKEN.findall(text.lower()):
        tokens.append(word)
        tokens.extend(part for part in word.split("_") if part != word)
    return tokens


@dataclass(frozen=True)
class Scored:
    id: str
    score: float


class BM25:
    def __init__(self, documents: dict[str, str]):
        self.documents = documents
        self._lengths = {}
        self._postings: dict[str, dict[str, int]] = defaultdict(dict)
        for doc_id, text in documents.items():
            counts = Counter(tokenize(text))
            self._lengths[doc_id] = sum(counts.values())
            for token, count in counts.items():
                self._postings[token][doc_id] = count
        self._average_length = (sum(self._lengths.values()) / len(self._lengths)) if self._lengths else 0.0
        total = len(documents)
        self._idf = {
            token: math.log(1 + (total - len(docs) + 0.5) / (len(docs) + 0.5))
            for token, docs in self._postings.items()
        }

    def search(self, query: str, limit: int = 50) -> list[Scored]:
        scores: dict[str, float] = defaultdict(float)
        for token in tokenize(query):
            idf = self._idf.get(token)
            if idf is None:
                continue
            for doc_id, count in self._postings[token].items():
                length = self._lengths[doc_id] / self._average_length if self._average_length else 1.0
                scores[doc_id] += idf * count * (K1 + 1) / (count + K1 * (1 - B + B * length))
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        return [Scored(doc_id, round(score, 4)) for doc_id, score in ranked[:limit]]
