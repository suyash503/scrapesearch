"""The single Elasticsearch client for the app."""
from functools import lru_cache

from django.conf import settings
from elasticsearch import Elasticsearch


@lru_cache(maxsize=1)
def get_client():
    """One shared client per process. It holds a connection pool, so don't create one per request."""
    options = {"request_timeout": 10, "retry_on_timeout": True, "max_retries": 2}
    # Production ES 8 has security on: log in with a password and verify its self-signed CA certificate.
    if settings.ES_PASSWORD:
        options["basic_auth"] = (settings.ES_USERNAME, settings.ES_PASSWORD)
    if settings.ES_CA_CERTS:
        options["ca_certs"] = settings.ES_CA_CERTS
    return Elasticsearch(settings.ES_URL, **options)
