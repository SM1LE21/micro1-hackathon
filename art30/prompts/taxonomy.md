# Personal-data taxonomy

Six category names. Every field you record carries exactly one of them.

## identifier

Names the person or points at them alone.

- `full_name`, `first_name`, `last_name`
- `username`, `display_name`, `handle`
- `national_id`, `passport_no`, `vat_number` on a person
- `stripe_customer_id`, `auth0_sub` and other external ids for the same person
- `avatar_key`, `export_path` and other object-storage keys built from a user id or username
- `slug` on a profile, where it is derived from a name

## contact

Reaches the person.

- `email`, `secondary_email`, `billing_email`
- `phone`, `mobile`, `fax`
- `address_line1`, `city`, `postcode` and the rest of a postal address
- push and messaging addresses: `device_token`, `telegram_chat_id`, `slack_user_id`
- `unsubscribe_email`, `notification_email`

## financial

Money that belongs to, or is paid by, the person.

- `iban`, `bic`, `account_holder`
- `card_last4`, `card_brand`, `payment_method_id`
- `invoice_total`, `amount_due`, `currency` on a row linked to the person
- `billing_address` (also contact-shaped; record it as financial when it sits on an invoice or a payment method)
- `tax_id`, `vat_number` on an invoice
- `payout_account`, `balance`

## behavioural

What the person did, chose or was measured doing.

- `last_login_at`, `created_at`, `updated_at` on a row linked to the person
- `login_count`, `failed_attempts`, `streak_days`
- `preferences`, `settings`, `locale`, `timezone`
- `is_active`, `is_staff`, `plan_tier` and other account-state columns on the subject class
- search terms, viewed items, cart contents, `event_name` and `properties` in an analytics payload
- `opened_at`, `clicked_at` on a mail event

## free_text_may_contain

A field a person types into, or a blob whose contents the schema does not constrain. It is classified by what it can hold, not by what a sample holds.

- `notes`, `bio`, `about`, `description` on a subject-linked model
- support-ticket `body`, `subject`, `resolution`
- `comment`, `message`, `review_text`
- `metadata`, `extra`, `payload`, `data` JSON columns on a subject-linked row
- exception messages, stack-frame locals and request bodies sent to an error tracker
- an imported CSV or attachment column stored as text

## technical

Produced by the person's device or session rather than by the person.

- `ip_address`, `x_forwarded_for`, `remote_addr` — including in a log line
- `user_agent`, `browser`, `os_version`
- `session_id`, `csrf_token`, `refresh_token`, cookie identifiers
- `device_id`, `fingerprint`
- `api_key`, `password_hash` and other credentials belonging to the person
- coarse location derived from an IP

# Edge cases

| Case | Category | Why |
|---|---|---|
| `created_at` / `last_seen_at` on a user-linked row | `behavioural` | The timestamp says what the person did and when. On a row with no link to a person it is not personal data at all. |
| `ip_address` in a middleware log line | `technical`, and the log sink is a store | An IP is data relating to an identifiable person. The log file is where it lives, so the log file is a store with that field. |
| `notes` with a comment saying it may contain phone numbers | `free_text_may_contain` | The comment is evidence about what the column holds. Cite the column's definition line; name the comment in the note. |
| A foreign key to the subject (`user_id`, `owner_id`) | Usually not a field of its own. It is the reason the store is in the record, recorded as the store's subject link with its `file:line`. Where it is the **only** personal data in that store, list it as a field with category `identifier`. | The link makes the row's other columns personal data; listing it twice inflates the field list without telling the reader anything new. Where nothing else is there, the fact that this person has a row in this store is itself information about them. |
| A hashed or tokenised value (`email_hash`, `pseudonym`) | The category the underlying value has (`email_hash` is `contact`) | The hash still points at the person. The hashing matters for the erasure verdict, not for the category. |
| `password_hash` | `technical` | A credential belonging to the person. The hasher is also worth recording as a technical security measure. |
| A soft-delete marker (`deleted_at`, `is_deleted`, `archived_at`) on a subject-linked row | `technical` | The column is the application's own state for the row, not something the person did. It is the line the erasure verdict turns on, so cite it there as well. |
| A foreign key to a lookup table (`plan_id` → `Plan`) | Not personal data; the lookup table stays out | The plan is a product, not a person. Which plan this person is on is `behavioural`, and it is already recorded as the column on the subject row. |
| An email in a queue payload or an analytics call | `contact`, in that store | The store is the queue or the third-party service, not the table the value came from. |

# Not personal data

Predicting these costs precision and nothing else.

- Product, plan, price and catalogue tables
- Currency, country, language and other lookup tables
- Configuration, settings modules, environment names, feature flags
- Migrations, schema metadata, admin registrations
- Static content, templates, translation strings
- Counters and aggregates with no link to a person (`total_orders_today`)
- Log lines that carry no user-linked value
