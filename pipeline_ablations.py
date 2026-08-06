import copy
import json
import re

from ablation_prompts import direct_analogy_targets_prompt, task_name_hint_prompt
from utils.analogy_target_utils import normalize_analogy_targets


SUPPORTED_ABLATIONS = {"none", "direct_targets", "task_name"}
TASK_NAME_HINT_MARKER = "[ARCANA_TASK_NAME_HINT]"


def normalize_ablation_name(ablation):
    if ablation in [None, "", "None"]:
        return "none"
    return str(ablation).strip()


def validate_ablation_name(ablation):
    ablation_name = normalize_ablation_name(ablation)
    if ablation_name not in SUPPORTED_ABLATIONS:
        supported = ", ".join(sorted(SUPPORTED_ABLATIONS))
        raise ValueError(f"Unsupported ablation '{ablation_name}'. Supported ablations: {supported}")
    return ablation_name


def build_task_name_hint(task_name):
    raw_task_name = str(task_name or "").strip()
    if not raw_task_name:
        raise ValueError("Task-name ablation requires a non-empty task name.")
    normalized_task_name = re.sub(r"[_-]+", " ", raw_task_name)
    normalized_task_name = re.sub(r"(?<=\D)(?=\d)|(?<=\d)(?=\D)", " ", normalized_task_name)
    normalized_task_name = " ".join(normalized_task_name.split())
    return task_name_hint_prompt.format(
            raw_task_name=json.dumps(raw_task_name, ensure_ascii=True),
            normalized_task_name=json.dumps(normalized_task_name, ensure_ascii=True),
            ).strip()


def inject_task_name_hint(messages, task_name_hint):
    if not task_name_hint:
        return messages
    if not isinstance(messages, (list, tuple)):
        raise TypeError("Messages must be a list or tuple for task-name hint injection.")

    injected_messages = copy.deepcopy(list(messages))
    for message in injected_messages:
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str) and TASK_NAME_HINT_MARKER in content:
            return injected_messages
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and TASK_NAME_HINT_MARKER in str(item.get("text", "")):
                    return injected_messages

    hint_item = {"type": "text", "text": task_name_hint}
    for message in injected_messages:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, list):
            message["content"] = [hint_item] + content
        elif isinstance(content, str):
            message["content"] = task_name_hint + "\n\n" + content
        else:
            message["content"] = [hint_item]
        return injected_messages

    injected_messages.append({"role": "user", "content": [hint_item]})
    return injected_messages


def generate_direct_analogy_targets(exs_url, exs, auxiliary_mc, recog_fn, parse_answer_fn):
    response = recog_fn(direct_analogy_targets_prompt, exs_url, auxiliary_mc, exs)
    if response is None:
        return None, response
    parsed = parse_answer_fn(response, is_format="recog")
    if not isinstance(parsed, dict):
        return None, response
    normalized = normalize_analogy_targets(parsed, required_count=3)
    if normalized is None:
        return None, response
    return normalized, response
