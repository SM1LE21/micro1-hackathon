# Source excerpts — object storage, caches, indices and third-party services

What "we deleted it" means outside the relational database. These are the stores the hand-written record of processing forgets.

---

## 1. S3: a delete on a versioned bucket is not a delete

Context: boto3's `delete_object`, the call `django-storages` and most Python code ends up making.

> Removes an object from a bucket. The behavior depends on the bucket's versioning state:
>
> * If bucket versioning is not enabled, the operation permanently deletes the object.
> * If bucket versioning is enabled, the operation inserts a delete marker, which becomes the current version of the object. To permanently delete an object in a versioned bucket, you must include the object's `versionId` in the request.
> * If bucket versioning is suspended, the operation removes the object that has a null `versionId`, if there is one, and inserts a delete marker that becomes the current version of the object.

[S23]

Context: the S3 user guide, same fact in the service's own words. The parenthesis defines "simple DELETE".

> When versioning is enabled, a simple `DELETE` cannot permanently delete an object. (A simple `DELETE` request is a request that doesn't specify a version ID.) Instead, Amazon S3 inserts a delete marker in the bucket, and that marker becomes the current version of the object with a new ID.
>
> When you try to `GET` an object whose current version is a delete marker, Amazon S3 behaves as though the object has been deleted (even though it has not been erased) and returns a 404 error.
>
> To delete versioned objects permanently, you must use `DELETE Object versionId`.

[S22]

Context: lifecycle rules do not rescue this either — `Expiration` adds a marker, and only `NoncurrentVersionExpiration` removes bytes.

> The `Expiration` action applies to the current object version. Instead of deleting the current object version, Amazon S3 retains the current version as a noncurrent version by adding a *delete marker*, which then becomes the current version.
>
> The `NoncurrentVersionExpiration` action applies to noncurrent object versions, and Amazon S3 permanently removes these object versions. You cannot recover permanently removed objects.

[S22]

"Even though it has not been erased" is the S3 documentation's own phrase. A GET returns 404 and the bytes are still billed.

Versioning is a bucket setting rather than a line of application code, but it is declared inside the repository often enough to be worth a lookup before assuming it away: boto3 `put_bucket_versioning(..., Status="Enabled")` or `BucketVersioning(bucket).enable()` in a bootstrap script or management command, a Terraform `aws_s3_bucket_versioning` block, a CloudFormation or CDK `VersioningConfiguration`, a MinIO or localstack init step in `docker-compose`. Where one of those sits in the same tree as a delete call that passes no `versionId`, the quotes above decide the verdict and it is `not_erased`.

---

## 2. Redis: DEL removes, EXPIRE schedules

> Removes the specified keys. A key is ignored if it does not exist.

[S24]

> Set a timeout on `key`. After the timeout has expired, the key will automatically be deleted. A key with an associated timeout is often said to be *volatile* in Redis terminology.

[S25]

Context: the trap. Overwriting the key clears the timeout, so a session cache that is refreshed on every request never expires.

> The timeout will only be cleared by commands that delete or overwrite the contents of the key, including `DEL`, `SET`, `GETSET` and all the `*STORE` commands. This means that all the operations that conceptually *alter* the value stored at the key without replacing it with a new one will leave the timeout untouched.

[S25]

> It is possible to call `EXPIRE` using as argument a key that already has an existing expire set. In this case the time to live of a key is *updated* to the new value.

[S25]

A `SETEX`/`EXPIRE` TTL is a retention timer for the Art. 30 record, not an erasure path: it fires on a clock, not on account closure, and a rolling refresh moves it forward indefinitely. Two consequences for the rule set. The verdict for a TTL-only cache is `not_erased`, with the TTL rendered in the retention column — `erased_after_timer` needs a scheduled job on the path that reaches a hard delete (AMBIGUITIES row 4), and a `setex` at write time is not one. And the `delete`/`unlink` that does count has to be reached from the erasure entry point, like every other primitive; a TTL set anywhere in the repository binds to nothing, so scoring it as erasure would let a codebase with no deletion feature at all claim one.

---

## 3. Elasticsearch

> Remove a JSON document from the specified index.

[S26]

> Each document indexed is versioned. When deleting a document, the version can be specified to make sure the relevant document you are trying to delete is actually being deleted and it has not changed in the meantime.

[S26]

> Deletes documents that match the specified query.

[S27]

> Elasticsearch gets a snapshot of the data stream or index when it begins processing the request

[S27]

A search index built from user content is a separate store. Deleting the row does not touch it; only an explicit `delete` or `delete_by_query` on the index does.

---

## 4. Stripe: deleted is not gone

Context: the Delete a customer endpoint.

> Permanently deletes a customer. It cannot be undone. Also immediately cancels any active subscriptions on the customer.

[S28]

Context: the Returns section of the same endpoint. This is the sentence that matters for an erasure claim.

> Unlike other objects, deleted customers can still be retrieved through the API in order to be able to track their history. Deleting customers removes all credit card details and prevents any further operations to be performed (such as adding a new subscription).

[S28]

Context: Stripe's own guidance on handling deletion requests, which points businesses at redaction rather than deletion.

> Redaction is the ability for businesses to permanently remove personal data from view, making the redacted object's data inaccessible to you in the Dashboard and API. We recommend using redaction jobs to remove your users' data for consumer data deletion requests.

> Deletion is a capability that some Stripe features offer for object lifecycle management. […] The delete API endpoints operate on the specified object only and offer detailed controls.

> As your payments and service provider, Stripe complies with legal and operational requirements imposed by the local authorities where your business operates and might retain data as legally required, after redaction.

> Fraud - Transactions don't support deletion and can only be redacted after 90 days.

> The Redaction API doesn't support invoice redactions, because issued invoices can be subject to tax-integrity and record-retention requirements.

[S29]

So `stripe.Customer.delete(id)` in a codebase is evidence of an attempt, not of erasure: the customer object stays retrievable, transactions are untouchable for 90 days, and invoices are out of scope entirely. Under `AMBIGUITIES` row 7 this store is `external_manual`.

---

## 5. Sentry: the flag decides which fields, not whether

Context: the option, from the Python SDK documentation and the matching docstring in `sentry_sdk/consts.py`.

> If this flag is enabled, certain personally identifiable information (PII) is added by active integrations.
>
> If you enable this option, be sure to manually remove what you don't want to send using our features for managing Sensitive Data.

[S30], [S42]

Default in the current SDK (`sentry-sdk` 2.68.1, uploaded 2026-08-24), from the `init` signature:

> ```python
> send_default_pii: "Optional[bool]" = None,
> ```

[S42]

Context: what the flag unlocks. Five categories on the data-collected page are gated on it.

> HTTP headers — "set `send_default_pii=True` in the `sentry_sdk.init()` call"
>
> Cookies — "set `send_default_pii=True` in the `sentry_sdk.init()` call"
>
> Information about the logged-in user (email, ID, username) — "set `send_default_pii=True` in the `sentry_sdk.init()` call"
>
> User IP address — "set `send_default_pii=True` in the `sentry_sdk.init()` call"
>
> LLM inputs and responses — "add `send_default_pii=True` to your `sentry_sdk.init()` call"

> By default, the Sentry SDK doesn't send cookies

[S31]

Context: the categories on the same page that the flag does not gate. Re-fetched 2026-08-28; these are the sentences that decide whether Sentry belongs in the record at all.

> Request URL
>
> The full request URL of outgoing and incoming HTTP requests is always sent to Sentry. Depending on your application, this could contain PII data.

> Request Query String
>
> The full request query string of outgoing and incoming HTTP requests is always sent to Sentry. Depending on your application, this could contain PII data.

> Request Body
>
> The request body of incoming HTTP requests can be sent to Sentry. Whether it's sent or not, depends on the type and size of request body as described below: The type of the request body: JSON and form bodies are sent […] There's a "max_request_body_size" option that's set to medium by default.

> Local Variables In Stack Trace
>
> When unhandled errors and exceptions are sent to Sentry, the names and values of local variables that were set when the errors occurred are sent at the same time.

> Source Context
>
> When an unhandled exception is sent to Sentry, a snapshot of the source code surrounding the line where the error originates is sent with it.

[S31]

The two "opt out" options behind the last pair default to on. From the `init` signature in `sentry_sdk/consts.py` at `VERSION = "2.68.1"`:

> ```python
> include_local_variables: "Optional[bool]" = True,
> include_source_context: "Optional[bool]" = True,
> max_request_body_size: str = "medium",
> ```

[S42]

Context: one more way a repository becomes a full PII recipient with `send_default_pii` nowhere in the file, from the `_experiments` docstring in the same source.

> ``data_collection`` (EXPERIMENTAL): structured configuration controlling what data integrations collect automatically, superseding `send_default_pii`. Passing a dict under `_experiments={"data_collection": {...}}` opts into the feature; omitted fields use their defaults (most categories are collected, with the sensitive denylist scrubbing values). […] If `send_default_pii` is also set, `data_collection` takes precedence.

[S42]

So a repository that calls `sentry_sdk.init(dsn=...)` without the flag and never calls `set_user()` is still a recipient. A `PATCH /users/me` handler that raises sends the request URL, the JSON body holding `email`, the surrounding source and the local `user` object's fields. The flag and an explicit `set_user()` / `set_context()` add headers, cookies, logged-in identity and IP, upgrading the field categories from `free_text_may_contain` and technical to identifier and contact. Whether, not which, is settled by the `init()` call itself. Omitting Sentry from the Art. 30 record on the strength of an absent flag is the same class of harm as a false erasure verdict.

---

## 6. Do the other services have a deletion API? (one line each)

- **Mixpanel**: yes. "Creates a task that specifies a list of users in a project to delete", `POST /data-deletions/v3.0`. [S32]
- **Segment**: yes. "Regulations enable you to issue a single request to delete and suppress data about a user by `userId`." [S33] The narrative page confirms what the request does and how far it reaches: "The following Segment & Destination regulations are available: `SUPPRESS_WITH_DELETE`: Suppress new data and delete existing data. `DELETE_ONLY`: Delete existing data without suppressing any new data." and "When you create a Segment-only regulation, Segment begins to suppress new data ingestion for that user, and begins to permanently delete previously ingested data associated with this user from your workspace. This includes scanning and removing all messages related to that `userId` from all data stores that don't automatically expire data within 30 days." [S47] Worth carrying into the artifact: only the Segment & Destination regulation types forward the request downstream, so a `DELETE_INTERNAL` call clears Segment and leaves every connected destination untouched [S47].
- **SendGrid**: yes. "This endpoint can be used to delete one or more contacts. The query parameter `ids` must set to a comma-separated list of contact IDs for bulk contact deletion. The query parameter `delete_all_contacts` must be set to `"true"` to delete **all** contacts." [S34]

All three are `external_manual` unless the repository actually calls the endpoint on the erasure path.

---

## Sources

| ID | Title | URL | Accessed | Used for |
|---|---|---|---|---|
| S22 | Deleting object versions from a versioning-enabled bucket — Amazon S3 User Guide | https://docs.aws.amazon.com/AmazonS3/latest/userguide/DeletingObjectVersions.html | 2026-08-28 | Delete markers, "not been erased", lifecycle expiration behaviour |
| S23 | `S3.Client.delete_object` — boto3 documentation | https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/delete_object.html | 2026-08-28 | Versioning-dependent behaviour of the call Python code makes |
| S24 | Redis `DEL` command reference | https://redis.io/docs/latest/commands/del/ | 2026-08-28 | What DEL removes |
| S25 | Redis `EXPIRE` command reference | https://redis.io/docs/latest/commands/expire/ | 2026-08-28 | TTL semantics; timeout cleared by overwrite; TTL refresh |
| S26 | Delete a document — Elasticsearch API reference | https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete | 2026-08-28 | Document delete and versioning |
| S27 | Delete by query — Elasticsearch API reference | https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete-by-query | 2026-08-28 | Query-based delete, snapshot semantics |
| S28 | Delete a customer — Stripe API reference | https://docs.stripe.com/api/customers/delete | 2026-08-28 | What deletion does and what remains retrievable |
| S29 | Handling customer deletion requests — Stripe documentation | https://docs.stripe.com/privacy/deletion-requests | 2026-08-28 | Redaction vs deletion, legal retention, 90-day transactions, invoices |
| S30 | Configuration options — Sentry Python SDK | https://docs.sentry.io/platforms/python/configuration/options/ | 2026-08-28 | `send_default_pii` description |
| S31 | Data collected — Sentry Python SDK | https://docs.sentry.io/platforms/python/data-management/data-collected/ | 2026-08-28 | The five categories the flag unlocks; request URL and query string always sent; body, source-context and stack-local behaviour |
| S32 | Create a Deletion — Mixpanel API reference | https://docs.mixpanel.com/reference/create-deletion | 2026-08-28 | Existence of a user-deletion endpoint |
| S33 | Deletion and Suppression — Segment Public API reference | https://docs.segmentapis.com/tag/Deletion-and-Suppression | 2026-08-28 | Existence of a user-deletion endpoint |
| S34 | Delete Contacts — SendGrid API reference (Twilio) | https://www.twilio.com/docs/sendgrid/api-reference/contacts/delete-contacts | 2026-08-28 | Existence of a contact-deletion endpoint |
| S42 | `sentry_sdk/consts.py` (sentry-sdk 2.68.1) | https://github.com/getsentry/sentry-python/blob/master/sentry_sdk/consts.py · https://pypi.org/pypi/sentry-sdk/json | 2026-08-28 | Defaults of `send_default_pii`, `include_local_variables`, `include_source_context`, `max_request_body_size`; `_experiments["data_collection"]` supersession; docstrings; current version |
| S47 | User Deletion and Suppression — Segment documentation | https://segment.com/docs/privacy/user-deletion-and-suppression/ → https://www.twilio.com/docs/segment/privacy/user-deletion-and-suppression | 2026-08-28 | Regulation types; what a deletion request removes and from which stores |

Fetch note for S47: the `segment.com` URL returns HTTP 403 to the documentation fetcher, which is a bot filter and not a property of the page. `curl -sSL --compressed` with a browser user-agent follows a cross-host redirect to `www.twilio.com/docs/segment/privacy/user-deletion-and-suppression` and returns HTTP 200; the quotes in section 6 are from that response. The earlier FETCH FAILED line for this URL is withdrawn.
