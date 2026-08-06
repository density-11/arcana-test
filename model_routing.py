from api_routing import normalize_api_route


DEFAULT_CHAT_MODELS = {
        "Qwen": "qwen/qwen3.7-max",
        "Claude": "anthropic/claude-fable-5",
        "Opus4p5": "anthropic/claude-opus-4.5",
        "deepseek": "deepseek-r1-250528",
        "GPT5p2": "openai/gpt-5.2",
        "GPT5": "openai/gpt-5.5",
        "GPT4.1": "gpt-4.1-2025-04-14",
        "GPT4o": "gpt-4o-2024-11-20",
        "doubao": "doubao-seed-1-6-vision-250815",
        "gemini": "google/gemini-3.5-flash",
        "Gemini3p1Pro": "google/gemini-3.1-pro-preview",
        }


DEFAULT_MODEL_ALIASES = {
        "opus": "Opus4p5",
        "opus4.5": "Opus4p5",
        }


def get_chat_model_hub(api_route):
    route = normalize_api_route(api_route)
    if route == "uni":
        from providers.uni.models import CHAT_MODELS
        source = CHAT_MODELS
    else:
        source = DEFAULT_CHAT_MODELS
    return dict(source)


def _get_model_aliases(route):
    if route == "uni":
        from providers.uni.models import MODEL_ALIASES
        return MODEL_ALIASES
    return DEFAULT_MODEL_ALIASES


def resolve_chat_model(model_chosen, api_route="default"):
    route = normalize_api_route(api_route)
    model_hub = get_chat_model_hub(route)
    requested = str(model_chosen or "").strip()
    requested_lower = requested.lower()

    canonical_lookup = {name.lower(): name for name in model_hub}
    model_id_lookup = {model_id.lower(): name for name, model_id in model_hub.items()}
    alias_lookup = {
            alias.lower(): canonical
            for alias, canonical in _get_model_aliases(route).items()
            }

    canonical_name = canonical_lookup.get(requested_lower)
    if canonical_name is None:
        canonical_name = model_id_lookup.get(requested_lower)
    if canonical_name is None:
        canonical_name = alias_lookup.get(requested_lower)
    if canonical_name is None:
        choices = ", ".join(model_hub)
        raise ValueError(
                f"Model '{model_chosen}' is not available for API route '{route}'. "
                f"Choose an alias or model ID from: {choices}."
                )

    return canonical_name, model_hub[canonical_name], model_hub


def arc_model_supports_images(model_id, api_route="default"):
    route = normalize_api_route(api_route)
    if route != "uni":
        return True
    from providers.uni.models import ARC_VISION_MODEL_IDS
    return model_id in ARC_VISION_MODEL_IDS


def resolve_arc_model(model_chosen, api_route="default", require_vision=True):
    canonical_name, model_id, model_hub = resolve_chat_model(model_chosen, api_route)
    route = normalize_api_route(api_route)
    if require_vision and not arc_model_supports_images(model_id, route):
        raise ValueError(
                "UNI ARC requests include image inputs, but the documented UNI vision "
                "model is qwen3.5. Use '--api uni --mc Qwen' or '--mc qwen3.5'."
                )
    return canonical_name, model_id, model_hub
