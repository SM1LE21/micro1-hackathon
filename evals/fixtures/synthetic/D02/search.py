"""Document search index."""

from elasticsearch import Elasticsearch

from config import ELASTICSEARCH_URL

INDEX = "user_search"
es = Elasticsearch(ELASTICSEARCH_URL)


def index_user(user):
    es.index(
        index=INDEX,
        document={
            "email": user.email,
            "full_name": user.full_name,
        },
    )
