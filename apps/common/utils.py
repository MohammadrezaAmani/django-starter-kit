import hashlib
import ipaddress
import logging
import secrets
import string
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from rest_framework.request import Request

from .models import Tag

logger = logging.getLogger(__name__)


def assign_tags_to_object(obj, tag_names, user):
    """Assign tags to an object, creating them if they don't exist."""
    tags = Tag.bulk_create_from_names(tag_names, created_by=user)
    obj.tags.set(tags)
    return tags


def get_client_ip(request: Request) -> str:
    """
    Extract client IP address from request, handling proxies and load balancers
    """
    # Check for forwarded IP addresses first
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        # X-Forwarded-For can contain multiple IPs, take the first one
        ip = x_forwarded_for.split(",")[0].strip()
        if is_valid_ip(ip):
            return ip

    # Check for real IP (commonly used by Cloudflare)
    x_real_ip = request.META.get("HTTP_X_REAL_IP")
    if x_real_ip and is_valid_ip(x_real_ip):
        return x_real_ip

    # Check for Cloudflare connecting IP
    cf_connecting_ip = request.META.get("HTTP_CF_CONNECTING_IP")
    if cf_connecting_ip and is_valid_ip(cf_connecting_ip):
        return cf_connecting_ip

    # Fall back to REMOTE_ADDR
    remote_addr = request.META.get("REMOTE_ADDR", "unknown")
    return remote_addr if is_valid_ip(remote_addr) else "unknown"


def get_user_agent(request: Request) -> str:
    """
    Extract user agent string from request
    """
    return request.META.get("HTTP_USER_AGENT", "unknown")


def is_valid_ip(ip: str) -> bool:
    """
    Validate if string is a valid IP address (IPv4 or IPv6)
    """
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def is_private_ip(ip: str) -> bool:
    """
    Check if IP address is private/internal
    """
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj.is_private
    except ValueError:
        return False


def get_geolocation_data(ip: str) -> Dict[str, Any]:
    """
    Get geolocation data for IP address (placeholder for integration with GeoIP service)
    """
    # This would integrate with a service like MaxMind GeoIP2, ip-api, etc.
    return {
        "country": "Unknown",
        "country_code": "XX",
        "region": "Unknown",
        "city": "Unknown",
        "timezone": "UTC",
        "latitude": None,
        "longitude": None,
        "isp": "Unknown",
    }


def generate_secure_token(length: int = 32) -> str:
    """
    Generate a cryptographically secure random token
    """
    return secrets.token_urlsafe(length)


def generate_numeric_code(length: int = 6) -> str:
    """
    Generate a random numeric code
    """
    return "".join(secrets.choice(string.digits) for _ in range(length))


def hash_string(value: str, salt: str = None) -> str:
    """
    Hash a string using SHA-256
    """
    if salt is None:
        salt = getattr(settings, "SECRET_KEY", "default_salt")

    combined = f"{value}{salt}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def validate_email_address(email: str) -> bool:
    """
    Validate email address format
    """
    try:
        validate_email(email)
        return True
    except ValidationError:
        return False


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent directory traversal and other security issues
    """
    # Remove path separators and other potentially dangerous characters
    dangerous_chars = ["/", "\\", "..", "<", ">", ":", '"', "|", "?", "*"]
    sanitized = filename

    for char in dangerous_chars:
        sanitized = sanitized.replace(char, "_")

    # Limit length
    if len(sanitized) > 255:
        name, ext = sanitized.rsplit(".", 1) if "." in sanitized else (sanitized, "")
        sanitized = f"{name[:240]}.{ext}" if ext else sanitized[:255]

    return sanitized or "unnamed_file"


def extract_domain_from_url(url: str) -> Optional[str]:
    """
    Extract domain from URL
    """
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return None


def is_safe_url(url: str, allowed_hosts: List[str] = None) -> bool:
    """
    Check if URL is safe (prevents open redirect attacks)
    """
    if not url:
        return False

    try:
        parsed = urlparse(url)

        # If no scheme, treat as relative URL (safe)
        if not parsed.scheme:
            return True

        # Only allow http/https
        if parsed.scheme not in ["http", "https"]:
            return False

        # Check against allowed hosts
        if allowed_hosts:
            return parsed.netloc.lower() in [host.lower() for host in allowed_hosts]

        # If no allowed hosts specified, check against Django's ALLOWED_HOSTS
        django_allowed_hosts = getattr(settings, "ALLOWED_HOSTS", [])
        if django_allowed_hosts and "*" not in django_allowed_hosts:
            return parsed.netloc.lower() in [
                host.lower() for host in django_allowed_hosts
            ]

        return True

    except Exception:
        return False


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to specified length with suffix
    """
    if not text or len(text) <= max_length:
        return text

    return text[: max_length - len(suffix)] + suffix


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human readable format
    """
    if size_bytes == 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB", "TB"]
    size_index = 0
    size = float(size_bytes)

    while size >= 1024.0 and size_index < len(size_names) - 1:
        size /= 1024.0
        size_index += 1

    return f"{size:.1f} {size_names[size_index]}"


def get_file_extension(filename: str) -> str:
    """
    Get file extension from filename
    """
    if "." in filename:
        return filename.rsplit(".", 1)[1].lower()
    return ""


def is_image_file(filename: str) -> bool:
    """
    Check if file is an image based on extension
    """
    image_extensions = {"jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "ico"}
    return get_file_extension(filename) in image_extensions


def is_document_file(filename: str) -> bool:
    """
    Check if file is a document based on extension
    """
    document_extensions = {
        "pdf",
        "doc",
        "docx",
        "txt",
        "rtf",
        "odt",
        "xls",
        "xlsx",
        "ppt",
        "pptx",
    }
    return get_file_extension(filename) in document_extensions


def generate_unique_filename(original_filename: str, prefix: str = None) -> str:
    """
    Generate unique filename with timestamp and random component
    """
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    random_part = generate_secure_token(8)

    name, ext = (
        original_filename.rsplit(".", 1)
        if "." in original_filename
        else (original_filename, "")
    )
    sanitized_name = sanitize_filename(name)

    parts = [timestamp, random_part, sanitized_name]
    if prefix:
        parts.insert(0, prefix)

    filename = "_".join(parts)
    return f"{filename}.{ext}" if ext else filename


def parse_search_query(query: str) -> Dict[str, Any]:
    """
    Parse search query string into structured data
    """
    if not query:
        return {"terms": [], "filters": {}}

    terms = []
    filters = {}

    # Split by spaces but respect quotes
    parts = []
    current_part = ""
    in_quotes = False

    for char in query:
        if char == '"':
            in_quotes = not in_quotes
        elif char == " " and not in_quotes:
            if current_part:
                parts.append(current_part)
                current_part = ""
        else:
            current_part += char

    if current_part:
        parts.append(current_part)

    # Process parts to extract filters and terms
    for part in parts:
        if ":" in part and not part.startswith('"'):
            # This looks like a filter (e.g., "type:document")
            key, value = part.split(":", 1)
            filters[key.lower()] = value.strip('"')
        else:
            # Regular search term
            terms.append(part.strip('"'))

    return {"terms": terms, "filters": filters}


def calculate_similarity_score(text1: str, text2: str) -> float:
    """
    Calculate similarity score between two texts (simple implementation)
    """
    if not text1 or not text2:
        return 0.0

    # Convert to lowercase and split into words
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())

    if not words1 or not words2:
        return 0.0

    # Calculate Jaccard similarity
    intersection = len(words1.intersection(words2))
    union = len(words1.union(words2))

    return intersection / union if union > 0 else 0.0


def mask_sensitive_data(data: str, mask_char: str = "*", visible_chars: int = 4) -> str:
    """
    Mask sensitive data (like email, phone) for logging/display
    """
    if not data or len(data) <= visible_chars * 2:
        return mask_char * len(data) if data else ""

    start_chars = data[:visible_chars]
    end_chars = data[-visible_chars:]
    masked_middle = mask_char * (len(data) - visible_chars * 2)

    return f"{start_chars}{masked_middle}{end_chars}"


def get_request_fingerprint(request: Request) -> str:
    """
    Generate a fingerprint for the request (for rate limiting, etc.)
    """
    components = [
        get_client_ip(request),
        get_user_agent(request),
        str(request.user.id) if request.user.is_authenticated else "anonymous",
    ]

    fingerprint_string = "|".join(components)
    return hash_string(fingerprint_string)


def validate_password_strength(password: str) -> Dict[str, Any]:
    """
    Validate password strength and return detailed feedback
    """
    score = 0
    feedback = []

    # Length check
    if len(password) >= 8:
        score += 1
    else:
        feedback.append("Password should be at least 8 characters long")

    if len(password) >= 12:
        score += 1

    # Character variety checks
    if any(c.islower() for c in password):
        score += 1
    else:
        feedback.append("Password should contain lowercase letters")

    if any(c.isupper() for c in password):
        score += 1
    else:
        feedback.append("Password should contain uppercase letters")

    if any(c.isdigit() for c in password):
        score += 1
    else:
        feedback.append("Password should contain numbers")

    if any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        score += 1
    else:
        feedback.append("Password should contain special characters")

    # Common password check (simplified)
    common_passwords = ["password", "123456", "qwerty", "abc123", "password123"]
    if password.lower() in common_passwords:
        score = 0
        feedback.append("Password is too common")

    strength_levels = ["Very Weak", "Weak", "Fair", "Good", "Strong", "Very Strong"]
    strength = strength_levels[min(score, len(strength_levels) - 1)]

    return {
        "score": score,
        "strength": strength,
        "is_strong": score >= 4,
        "feedback": feedback,
    }


def rate_limit_key(request: Request, scope: str) -> str:
    """
    Generate rate limit key for request
    """
    if request.user.is_authenticated:
        identifier = f"user_{request.user.id}"
    else:
        identifier = f"ip_{get_client_ip(request)}"

    return f"rate_limit:{scope}:{identifier}"
