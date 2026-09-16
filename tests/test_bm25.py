from sqlagent.retrieval.bm25 import BM25, tokenize

DOCS = {
    "column:account.frequency": "column account.frequency (text): how often statements are issued",
    "column:loan.amount": "column loan.amount (bigint): amount of the loan",
    "table:loan": "table loan: loans granted to accounts",
    "column:trans.k_symbol": "column trans.k_symbol (text): transaction characterisation",
}
INDEX = BM25(DOCS)


def test_tokenize_splits_words_and_underscores():
    assert tokenize("k_symbol Amount-2") == ["k_symbol", "k", "symbol", "amount", "2"]


def test_search_ranks_the_matching_document_first():
    assert INDEX.search("loan amount")[0].id == "column:loan.amount"
    assert INDEX.search("how often statements are issued")[0].id == "column:account.frequency"


def test_search_matches_underscore_parts():
    assert INDEX.search("symbol")[0].id == "column:trans.k_symbol"


def test_unknown_words_and_limit():
    assert INDEX.search("kubernetes") == []
    assert len(INDEX.search("loan account amount", limit=2)) == 2


def test_rare_words_outrank_common_ones():
    hits = {h.id: h.score for h in INDEX.search("loan characterisation")}
    assert hits["column:trans.k_symbol"] > hits["table:loan"]


def test_empty_index_is_safe():
    assert BM25({}).search("anything") == []
