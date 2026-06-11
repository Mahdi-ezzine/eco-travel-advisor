
import os

try:
    from dotenv import load_dotenv
    _here = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(_here, ".env"))
    load_dotenv()
except Exception:
    pass


def _from_colab(name):
    """Return a secret from Colab userdata, or None if not in Colab."""
    try:
        from google.colab import userdata
        try:
            return userdata.get(name)
        except Exception:
            return None
    except Exception:
        return None


def get_secret(name, *aliases, default=None):
    """
    Resolve a secret by name, trying a list of accepted alias names.

    """
    candidates = (name,) + aliases
    for candidate in candidates:
        value = _from_colab(candidate)
        if value:
            return value
        value = os.getenv(candidate)
        if value:
            return value
    return default


def get_database_url():
    """
    Build the PostgreSQL connection string for Neon.

    """
    url = get_secret(
        "DATABASE_URL",
        "POSTGRES_URL",
        "POSTGRES_CONNECTION_STRING",
        "POSTGRES_URI",
        "NEON_DATABASE_URL",
    )
    if url:
        return url

    host = get_secret("POSTGRES_HOST", "PGHOST")
    db = get_secret("POSTGRES_DB", "POSTGRES_DATABASE", "PGDATABASE", default="neondb")
    user = get_secret("POSTGRES_USER", "PGUSER")
    password = get_secret("POSTGRES_PASSWORD", "PGPASSWORD")
    port = get_secret("POSTGRES_PORT", "PGPORT", default="5432")

    if host and user and password:
        return (
            "postgresql://{user}:{password}@{host}:{port}/{db}?sslmode=require"
        ).format(user=user, password=password, host=host, port=port, db=db)

    return None


def write_env_file(path=".env"):

    values = {
        "DATABASE_URL": get_database_url(),
        "CLIMATIQ_API_KEY": get_secret("CLIMATIQ_API_KEY", "CLIMATIQ_KEY"),
        "OPENCAGE_API_KEY": get_secret("OPENCAGE_API_KEY", "OPENCAGE_KEY"),
        "ORS_API_KEY": get_secret("ORS_API_KEY", "OPENROUTESERVICE_API_KEY"),
        "NGROK_AUTH_TOKEN": get_secret("NGROK_AUTH_TOKEN", "NGROK_TOKEN"),
        "RASA_API_URL": os.getenv(
            "RASA_API_URL", "http://localhost:5005/webhooks/rest/webhook"
        ),
        "ACTION_ENDPOINT_URL": os.getenv(
            "ACTION_ENDPOINT_URL", "http://localhost:5055/webhook"
        ),
    }
    lines = []
    for key, value in values.items():
        if value:
            lines.append("{key}={value}".format(key=key, value=value))
    with open(path, "w") as handle:
        handle.write("\n".join(lines) + "\n")
    # Also export to the current process so subprocesses inherit the values.
    for key, value in values.items():
        if value:
            os.environ[key] = value
    return [key for key, value in values.items() if value]


# Endpoints (overridable through the environment for Docker networking).
RASA_API_URL = os.getenv(
    "RASA_API_URL", "http://localhost:5005/webhooks/rest/webhook"
)
ACTION_SERVER_URL = os.getenv(
    "ACTION_SERVER_URL", "http://localhost:5055/webhook"
)
