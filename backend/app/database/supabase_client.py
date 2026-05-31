import threading

from supabase import Client, create_client

from app.config import get_settings

_thread_local = threading.local()


def get_supabase_client() -> Client:
    existing_client = getattr(_thread_local, "client", None)
    if existing_client:
        return existing_client

    settings = get_settings()
    supabase_url = settings.resolved_supabase_url
    service_role_key = settings.supabase_service_role_key

    if not supabase_url or not service_role_key:
        raise RuntimeError("Backend Supabase URL and service-role key are required.")

    client = create_client(supabase_url, service_role_key)
    _thread_local.client = client
    return client
