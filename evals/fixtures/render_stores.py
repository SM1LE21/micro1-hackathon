"""Non-relational store modules (fixture-generator.md section 3.1, section 5).

Every module takes its identifier from the store's `name`, so the manifest name and the
rendered literal cannot drift (section 7 rule 1), and records the line that names each
declared field as it writes it (section 6.1).
"""

from __future__ import annotations

import re

from emit import Doc, SpecError
from render_common import Rendered, placeholders, value_expr, value_models
from spec_model import var_of

# The client address and the request path are named locals so the log store's fields are
# tokens the code writes (fixture-generator.md section 9, S07).
LOG_SOURCES = {"ip_address": "request.client.host", "path": "request.url.path"}

_KEY_ATTR = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


def writer_params(spec: dict, store: dict) -> list[str]:
    client = store["client"]
    if client == "boto3":
        meta = [f["name"] for f in store["fields"][1:]]
        return placeholders(store["key_template"]) + ["data"] + meta
    if client == "redis":
        return ["user", "token"]
    if client in {"stripe", "mixpanel", "sendgrid"}:
        return ["user"]
    if client in {"elasticsearch", "pika"}:
        return [var_of(m) for m in value_models(spec, [f["name"] for f in store["fields"]])]
    if client == "logging":
        return ["request"]
    raise SpecError(f"store {store['name']}: no writer template for client {store['client']}")


def _header(doc: Doc, title: str, imports: list[str], config: list[str]) -> None:
    doc.add(f'"""{title}"""')
    doc.blank()
    doc.add(*imports)
    doc.blank()
    if config:
        doc.add(*config)
        doc.blank()


def _storage(spec: dict, store: dict, r: Rendered) -> None:
    doc = Doc()
    _header(doc, f"Object storage for {spec['package']}.", ["import boto3"], ["from config import AWS_REGION"])
    identity = doc.add(f'BUCKET = "{store["name"]}"')
    doc.add('s3 = boto3.client("s3", region_name=AWS_REGION)')
    doc.blank(2)
    keys = placeholders(store["key_template"])
    key_field = store["fields"][0]["name"]
    key_line = doc.add(f"def {key_field}({', '.join(keys)}):")
    doc.add(f'    return f"{store["key_template"]}"')
    doc.blank(2)
    params = writer_params(spec, store)
    doc.add(f"def {store['writes_from']}({', '.join(params)}):")
    doc.add(f"    key = {key_field}({', '.join(keys)})")
    doc.add("    s3.put_object(")
    doc.add("        Bucket=BUCKET,", "        Key=key,", "        Body=data,")
    doc.add('        ServerSideEncryption="AES256",')
    meta = [f["name"] for f in store["fields"][1:]]
    if meta:
        # One dict, one line per entry: a repeated `Metadata=` keyword is a SyntaxError.
        doc.add("        Metadata={")
        for name in meta:
            line = doc.add(f'            "{name}": {name},')
            r.cite_field(store["name"], name, store["module"], line)
        doc.add("        },")
    doc.add("    )", "    return key")
    if store["delete_call"]:
        doc.blank(2)
        doc.add(f"def {store['delete_call']}({', '.join(keys)}):")
        doc.add(f"    s3.delete_object(Bucket=BUCKET, Key={key_field}({', '.join(keys)}))")
    r.identity[store["name"]] = (store["module"], identity)
    r.cite_field(store["name"], key_field, store["module"], key_line)
    r.subject_link[store["name"]] = (store["module"], key_line)
    r.put(store["module"], doc)


def _cache(spec: dict, store: dict, r: Rendered) -> None:
    doc = Doc()
    _header(doc, "Session cache.", ["import redis"], ["from config import REDIS_URL"])
    doc.add(f"SESSION_TTL_SECONDS = {store['ttl_seconds']}")
    doc.add("cache = redis.Redis.from_url(REDIS_URL)")
    doc.blank(2)
    doc.add(f"def {store['writes_from']}({', '.join(writer_params(spec, store))}):")
    key = _KEY_ATTR.sub(lambda m: "{user." + m.group(1) + "}", store["key_template"])
    write = doc.add(f'    cache.setex(f"{key}", SESSION_TTL_SECONDS, token)')
    if store["delete_call"]:
        doc.blank(2)
        doc.add(f"def {store['delete_call']}(user):")
        doc.add(f'    cache.delete(f"{key}")')
    r.identity[store["name"]] = (store["module"], write)
    r.subject_link[store["name"]] = (store["module"], write)
    for field in store["fields"]:
        r.cite_field(store["name"], field["name"], store["module"], write)
    r.put(store["module"], doc)


def _billing(spec: dict, store: dict, r: Rendered) -> None:
    doc = Doc()
    _header(doc, "Payment integration.", ["import stripe"], ["from config import STRIPE_API_KEY"])
    identity = doc.add("stripe.api_key = STRIPE_API_KEY")
    doc.blank(2)
    doc.add(f"def {store['writes_from']}(user):")
    call = doc.add("    return stripe.Customer.create(")
    for field in store["fields"]:
        line = doc.add(f"        {field['name']}={value_expr(spec, field['name'])},")
        r.cite_field(store["name"], field["name"], store["module"], line)
    doc.add("    )")
    r.identity[store["name"]] = (store["module"], identity)
    r.subject_link[store["name"]] = (store["module"], call)
    r.put(store["module"], doc)


def _analytics(spec: dict, store: dict, r: Rendered) -> None:
    doc = Doc()
    _header(
        doc,
        "Product analytics.",
        ["from mixpanel import Mixpanel"],
        ["from config import MIXPANEL_TOKEN"],
    )
    identity = doc.add("mp = Mixpanel(MIXPANEL_TOKEN)")
    doc.blank(2)
    doc.add(f"def {store['writes_from']}(user):")
    track = doc.add('    mp.track(user.email, "account_created")')
    r.identity[store["name"]] = (store["module"], identity)
    r.subject_link[store["name"]] = (store["module"], track)
    for field in store["fields"]:
        r.cite_field(store["name"], field["name"], store["module"], track)
    r.put(store["module"], doc)


def _mail(spec: dict, store: dict, r: Rendered) -> None:
    doc = Doc()
    _header(
        doc,
        "Transactional mail.",
        ["import sendgrid"],
        ["from config import SENDGRID_API_KEY"],
    )
    identity = doc.add("sg = sendgrid.SendGridAPIClient(SENDGRID_API_KEY)")
    doc.blank(2)
    doc.add(f"def {store['writes_from']}(user):")
    body = doc.add('    body = f"Welcome, {user.full_name}."')
    send = doc.add('    sg.send(to=user.email, subject="Welcome", body=body)')
    r.identity[store["name"]] = (store["module"], identity)
    r.subject_link[store["name"]] = (store["module"], send)
    for field in store["fields"]:
        r.cite_field(store["name"], field["name"], store["module"], body if field["name"] != "email" else send)
    r.put(store["module"], doc)


def _search(spec: dict, store: dict, r: Rendered) -> None:
    doc = Doc()
    _header(
        doc,
        "Document search index.",
        ["from elasticsearch import Elasticsearch"],
        ["from config import ELASTICSEARCH_URL"],
    )
    identity = doc.add(f'INDEX = "{store["name"]}"')
    doc.add("es = Elasticsearch(ELASTICSEARCH_URL)")
    doc.blank(2)
    doc.add(f"def {store['writes_from']}({', '.join(writer_params(spec, store))}):")
    call = doc.add("    es.index(")
    doc.add("        index=INDEX,", "        document={")
    for field in store["fields"]:
        line = doc.add(f'            "{field["name"]}": {value_expr(spec, field["name"])},')
        r.cite_field(store["name"], field["name"], store["module"], line)
    doc.add("        },", "    )")
    r.identity[store["name"]] = (store["module"], identity)
    r.subject_link[store["name"]] = (store["module"], call)
    r.put(store["module"], doc)


def _queue(spec: dict, store: dict, r: Rendered) -> None:
    doc = Doc()
    _header(doc, "Event publishing.", ["import json", "", "import pika"], ["from config import RABBITMQ_URL"])
    identity = doc.add(f'QUEUE = "{store["name"]}"')
    doc.add("channel = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL)).channel()")
    doc.blank(2)
    doc.add(f"def {store['writes_from']}({', '.join(writer_params(spec, store))}):")
    call = doc.add("    channel.basic_publish(")
    doc.add('        exchange="",', "        routing_key=QUEUE,", "        body=json.dumps(")
    doc.add("            {")
    for field in store["fields"]:
        line = doc.add(f'                "{field["name"]}": {value_expr(spec, field["name"])},')
        r.cite_field(store["name"], field["name"], store["module"], line)
    doc.add("            }", "        ),", "    )")
    r.identity[store["name"]] = (store["module"], identity)
    r.subject_link[store["name"]] = (store["module"], call)
    r.put(store["module"], doc)


def _log(spec: dict, store: dict, r: Rendered) -> None:
    doc = Doc()
    doc.add('"""Request logging middleware."""')
    doc.blank()
    doc.add("import logging")
    doc.blank()
    identity = doc.add(f'logger = logging.getLogger("{store["name"]}")')
    doc.blank(2)
    doc.add(f"def {store['writes_from']}(request):")
    for field in store["fields"]:
        source = LOG_SOURCES.get(field["name"], f'request.headers.get("{field["name"]}")')
        line = doc.add(f"    {field['name']} = {source}")
        r.cite_field(store["name"], field["name"], store["module"], line)
    names = ", ".join(f["name"] for f in store["fields"])
    fmt = " ".join(["%s"] * len(store["fields"]))
    write = doc.add(f'    logger.info("{fmt}", {names})')
    r.identity[store["name"]] = (store["module"], identity)
    r.subject_link[store["name"]] = (store["module"], write)
    r.put(store["module"], doc)


_RENDERERS = {
    "boto3": _storage,
    "redis": _cache,
    "stripe": _billing,
    "mixpanel": _analytics,
    "sendgrid": _mail,
    "elasticsearch": _search,
    "pika": _queue,
    "logging": _log,
}


def render_store(spec: dict, store: dict, r: Rendered) -> None:
    renderer = _RENDERERS.get(store["client"])
    if renderer is None:
        raise SpecError(f"store {store['name']}: no module template for client {store['client']}")
    renderer(spec, store, r)


def has_module(store: dict) -> bool:
    """Stores whose module this file renders; the rest live in app.py, models.py or a job."""
    return store["client"] in _RENDERERS
