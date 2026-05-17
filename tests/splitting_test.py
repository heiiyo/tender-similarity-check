from apps import AppContext

def test_splitting_a():
    AppContext().init_context()
    embe = AppContext().embedding_vectorizer
    em_list = embe.encode("你好呀")
    assert len(em_list[0]) == embe.get_vector_dim()

