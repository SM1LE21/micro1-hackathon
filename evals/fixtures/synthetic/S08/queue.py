"""Event publishing."""

import json

import pika

from config import RABBITMQ_URL

QUEUE = "events"
channel = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL)).channel()


def publish_document_created(user):
    channel.basic_publish(
        exchange="",
        routing_key=QUEUE,
        body=json.dumps(
            {
                "email": user.email,
            }
        ),
    )
