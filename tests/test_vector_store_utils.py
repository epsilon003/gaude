"""
Tests for rag_core/vector_store.py's repo_url_to_collection_name -- the
golden dataset (eval/golden_dataset.json) hardcodes the slug this function
produces for the gaude repo itself, so a change here would silently break
the eval harness even though nothing would raise an exception.
"""
from rag_core.vector_store import repo_url_to_collection_name


def test_known_repo_url_matches_the_slug_hardcoded_in_the_eval_dataset():
    # eval/golden_dataset.json assumes this exact slug for self-referential
    # evaluation against the gaude repo -- if this test breaks, update the
    # dataset's collection_name values to match.
    slug = repo_url_to_collection_name("https://github.com/epsilon003/gaude")
    assert slug == "https-github-com-epsilon003-gaude"


def test_strips_trailing_slash():
    a = repo_url_to_collection_name("https://github.com/owner/repo")
    b = repo_url_to_collection_name("https://github.com/owner/repo/")
    assert a == b


def test_lowercases_output():
    slug = repo_url_to_collection_name("https://github.com/OwnerCase/RepoCase")
    assert slug == slug.lower()


def test_non_alphanumeric_becomes_single_hyphen():
    slug = repo_url_to_collection_name("https://github.com/a/b")
    assert "--" not in slug
    assert not slug.startswith("-")
    assert not slug.endswith("-")


def test_truncates_to_chroma_max_collection_name_length():
    long_url = "https://github.com/" + ("x" * 200) + "/repo"
    slug = repo_url_to_collection_name(long_url)
    assert len(slug) <= 63


def test_empty_input_falls_back_to_default(): 
    assert repo_url_to_collection_name("") == "default-collection"


class TestGetOrCreateCollectionMetadata:
    """Regression test for a real bug found running the eval harness against
    a collection that hadn't been ingested yet: get_or_create_collection's
    default call (no source_url/commit_sha, as retrieve_and_rerank always
    makes it) used to pass {"source_url": None, "commit_sha": None} straight
    to chromadb, which rejects None as a metadata value with a TypeError
    instead of cleanly creating an empty collection."""

    def test_creating_a_new_collection_with_no_source_info_does_not_raise(self, tmp_path):
        from rag_core.vector_store import VectorStore

        store = VectorStore(persist_dir=str(tmp_path))
        collection = store.get_or_create_collection("brand-new-collection")
        assert collection.name == "brand-new-collection"

    def test_creating_a_new_collection_with_source_info_still_stores_it(self, tmp_path):
        from rag_core.vector_store import VectorStore

        store = VectorStore(persist_dir=str(tmp_path))
        collection = store.get_or_create_collection(
            "another-collection",
            source_url="https://github.com/epsilon003/gaude",
            commit_sha="abc123",
        )
        assert collection.metadata == {
            "source_url": "https://github.com/epsilon003/gaude",
            "commit_sha": "abc123",
        }

    def test_fetching_an_existing_collection_is_unaffected(self, tmp_path):
        from rag_core.vector_store import VectorStore

        store = VectorStore(persist_dir=str(tmp_path))
        first = store.get_or_create_collection("repeat-collection")
        second = store.get_or_create_collection("repeat-collection")
        assert first.id == second.id