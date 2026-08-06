"""UNI-specific generation controls."""

import os


UNI_MAX_LENGTH_ENV = {
        "baseline": "ARCANA_UNI_BASELINE_MAX_LENGTH",
        "pipeline": "ARCANA_UNI_PIPELINE_MAX_LENGTH",
        }
UNI_THINKING_DEFAULTS = {
        "qwen3.5": True,
        "qwen3.6-27b": True,
        }


def resolve_uni_generation_settings(workload, model_id=None, environ=None):
    if workload not in UNI_MAX_LENGTH_ENV:
        choices = ", ".join(sorted(UNI_MAX_LENGTH_ENV))
        raise ValueError(f"Unsupported UNI workload '{workload}'. Choose one of: {choices}.")

    env = os.environ if environ is None else environ
    max_length_env = UNI_MAX_LENGTH_ENV[workload]
    raw_max_length = env.get(max_length_env)
    if raw_max_length is None or str(raw_max_length).strip() == "":
        max_length = None
    else:
        try:
            max_length = int(raw_max_length)
        except (TypeError, ValueError):
            raise ValueError(f"{max_length_env} must be a positive integer when set.")
        if max_length <= 0:
            raise ValueError(f"{max_length_env} must be a positive integer when set.")

    thinking_env = "ARCANA_UNI_ENABLE_THINKING"
    normalized_model_id = str(model_id or "").strip().lower()
    thinking_supported = model_id is None or normalized_model_id in UNI_THINKING_DEFAULTS
    if not thinking_supported:
        enable_thinking = None
    else:
        default_thinking = UNI_THINKING_DEFAULTS.get(normalized_model_id, False)
        default_thinking_value = "true" if default_thinking else "false"
        thinking_value = str(
                env.get(thinking_env, default_thinking_value)
                ).strip().lower()
        if thinking_value in {"1", "true", "t", "yes", "y", "on"}:
            enable_thinking = True
        elif thinking_value in {"0", "false", "f", "no", "n", "off"}:
            enable_thinking = False
        else:
            raise ValueError(
                    f"{thinking_env} must be one of: true, false, t, f, 1, 0, yes, no."
                    )

    return {
            "max_length": max_length,
            "enable_thinking": enable_thinking,
            "max_length_env": max_length_env,
            "thinking_env": thinking_env,
            }


def apply_uni_generation_settings(request_kwargs, settings):
    request_kwargs = dict(request_kwargs)
    request_kwargs["stream"] = True
    request_kwargs.pop("stream_options", None)

    extra_body = dict(request_kwargs.get("extra_body") or {})
    if settings["enable_thinking"] is not None:
        chat_template_kwargs = dict(extra_body.get("chat_template_kwargs") or {})
        chat_template_kwargs["enable_thinking"] = settings["enable_thinking"]
        extra_body["chat_template_kwargs"] = chat_template_kwargs
    if settings["max_length"] is None:
        extra_body.pop("max_length", None)
    else:
        extra_body["max_length"] = settings["max_length"]
    if extra_body:
        request_kwargs["extra_body"] = extra_body
    else:
        request_kwargs.pop("extra_body", None)
    return request_kwargs
