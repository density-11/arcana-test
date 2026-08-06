import os


SUPPORTED_API_ROUTES = ("default", "uni")


def normalize_api_route(api_route):
    route = str(api_route or "default").strip().lower()
    if route not in SUPPORTED_API_ROUTES:
        supported = ", ".join(SUPPORTED_API_ROUTES)
        raise ValueError(f"Unsupported API route '{api_route}'. Choose one of: {supported}.")
    return route


def resolve_openai_client_kwargs(
        api_route,
        *,
        default_base_url_env=None,
        default_api_key_env=None,
        environ=None,
        ):
    route = normalize_api_route(api_route)
    env = os.environ if environ is None else environ

    if route == "uni":
        base_url_env = "UNI_BASE_URL"
        api_key_env = "UNI_API_KEY"
    elif default_base_url_env and default_api_key_env:
        base_url_env = default_base_url_env
        api_key_env = default_api_key_env
    else:
        return {}

    base_url = env.get(base_url_env)
    api_key = env.get(api_key_env)
    missing = [
            env_name
            for env_name, value in ((base_url_env, base_url), (api_key_env, api_key))
            if not value
            ]
    if missing:
        missing_names = ", ".join(missing)
        raise EnvironmentError(
                f"API route '{route}' requires exported environment variable(s): {missing_names}."
                )

    return {
            "base_url": base_url,
            "api_key": api_key,
            }
