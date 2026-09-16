import hashlib

import pytest


class FakeEmbedder:
    model_name = "fake-embedder"

    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        return [[b / 255 for b in hashlib.sha256(t.encode()).digest()[:8]] for t in texts]


@pytest.fixture
def fake_embedder():
    return FakeEmbedder()
