import re
import unicodedata


def sanitize_slug(slug: str | None) -> str | None:
    """Sanitize a string to be used as a URL slug.

    - Converts to lowercase
    - Replaces spaces and underscores with hyphens
    - Removes characters that are not alphanumeric or hyphens
    - Removes leading/trailing hyphens
    """
    if not slug:
        return None
    slug = slug.lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = slug.strip("-")
    return slug or None


def slugify_name(name: str) -> str | None:
    """Create a readable, URL-safe slug from a newsletter name."""
    normalized_name = unicodedata.normalize("NFKD", name.casefold())
    normalized_name = "".join(
        character
        for character in normalized_name
        if not unicodedata.combining(character)
    )
    normalized_name = normalized_name.replace("'", "").replace("’", "")
    normalized_name = re.sub(r"[\W_]+", "-", normalized_name)
    normalized_name = normalized_name.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized_name).strip("-")
    return slug or None
