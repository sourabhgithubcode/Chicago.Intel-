"""Supabase admin client — uses service_role key, full DB access."""
import os


def get_admin_client():
    # Lazy import — lets --dry-run work without the supabase lib installed.
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)
