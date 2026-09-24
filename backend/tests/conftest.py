import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api():
    return APIClient()


class FakeES:
    """Stands in for the Elasticsearch client in API tests: records the query, returns a canned response."""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


@pytest.fixture
def fake_es(monkeypatch):
    """Usage: es = fake_es(response={...}) or fake_es(error=SomeError()). Patches the client the views use."""
    def install(response=None, error=None):
        es = FakeES(response, error)
        monkeypatch.setattr("search.views.get_client", lambda: es)
        return es
    return install


# ---------- Real Elasticsearch (integration tests, marked @pytest.mark.es) ----------

@pytest.fixture(scope="session")
def es_client():
    from search.es import get_client
    client = get_client()
    try:
        reachable = client.ping()
    except Exception:  # any failure means "no ES here"
        reachable = False
    if not reachable:
        pytest.skip("Elasticsearch is not reachable")
    return client


@pytest.fixture
def es_test_alias(es_client, settings):
    """Point the app at a throwaway alias ("test_books") and delete its indices afterwards.

    The real "books" alias and its data are never touched.
    """
    alias = "test_books"
    settings.ES_BOOKS_ALIAS = alias

    def cleanup():
        # ES 8 refuses wildcard deletes (action.destructive_requires_name=true, a guard against
        # `DELETE *` accidents), so look up the concrete index names first, then delete those.
        names = list(es_client.indices.get(index=f"{alias}_*", allow_no_indices=True).keys())
        if names:
            es_client.indices.delete(index=",".join(names))

    cleanup()  # before, too: a crashed earlier run may have left indices behind
    yield alias
    cleanup()
