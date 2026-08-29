"""Document search index."""

from elasticsearch import Elasticsearch

from config import ELASTICSEARCH_URL

INDEX = "doc_search"
es = Elasticsearch(ELASTICSEARCH_URL)


def index_document(user, document):
    es.index(
        index=INDEX,
        document={
            "owner_email": user.email,
            "title": document.title,
        },
    )
