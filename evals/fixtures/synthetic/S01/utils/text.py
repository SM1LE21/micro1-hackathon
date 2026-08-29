"""Small string helpers. No personal data passes through this module."""


def slugify(value):
    return "-".join(part for part in value.lower().split() if part)


def truncate(value, limit=80):
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def humanise_bytes(count):
    for unit in ("B", "KB", "MB"):
        if count < 1024:
            return f"{count} {unit}"
        count //= 1024
    return f"{count} GB"
