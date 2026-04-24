"""Supabase admin client — uses service_role key, full DB access."""
import os
from supabase import create_client, Client


def get_admin_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)
