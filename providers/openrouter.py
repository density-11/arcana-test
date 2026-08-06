"""OpenRouter-specific request settings."""


OPENROUTER_BASELINE_REASONING_EFFORT = "high"
SUPPORTED_OPENROUTER_REASONING_EFFORTS = {
        "none", "minimal", "low", "medium", "high", "xhigh", "max",
        }


def apply_openrouter_reasoning_effort(request_kwargs, effort):
    normalized_effort = str(effort or "").strip().lower()
    if normalized_effort not in SUPPORTED_OPENROUTER_REASONING_EFFORTS:
        choices = ", ".join(sorted(SUPPORTED_OPENROUTER_REASONING_EFFORTS))
        raise ValueError(
                f"Unsupported OpenRouter reasoning effort '{effort}'. Choose one of: {choices}."
                )

    request_kwargs = dict(request_kwargs)
    extra_body = dict(request_kwargs.get("extra_body") or {})
    reasoning = dict(extra_body.get("reasoning") or {})
    reasoning["effort"] = normalized_effort
    extra_body["reasoning"] = reasoning
    request_kwargs["extra_body"] = extra_body
    return request_kwargs
