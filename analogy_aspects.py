import json
import os

from prompts import (
    build_analogy_aspect_prompt,
    build_analogy_composite_prompt_text,
    build_concept_expansion_prompt_text,
)


ASPECTS_JSON_FILE = os.path.join(os.path.dirname(__file__), "analogy_aspects.json")


def _load_raw_analogy_aspects():
    with open(ASPECTS_JSON_FILE, "r", encoding="utf-8") as f:
        raw_aspects = json.load(f)
    if not isinstance(raw_aspects, dict):
        raise ValueError("analogy_aspects.json must contain a JSON object.")
    return raw_aspects


def _normalize_analogy_aspects(raw_aspects):
    normalized = {}
    for aspect_name, aspect_config in raw_aspects.items():
        if not isinstance(aspect_config, dict):
            raise ValueError(f"Analogy aspect '{aspect_name}' must be a JSON object.")
        if aspect_config.get("enabled", True) is False:
            continue
        prompt = aspect_config.get("prompt")
        prompt_tail = aspect_config.get("prompt_tail")
        if prompt is None:
            if not isinstance(prompt_tail, str) or not prompt_tail.strip():
                raise ValueError(f"Analogy aspect '{aspect_name}' must define prompt or prompt_tail.")
            prompt = build_analogy_aspect_prompt(prompt_tail)
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"Analogy aspect '{aspect_name}' prompt must be a non-empty string.")
        normalized[aspect_name] = {
            "stage": aspect_config.get("stage", f"analogy_{aspect_name}"),
            "composite_label": aspect_config.get("composite_label", aspect_name),
            "prompt": prompt,
        }
    if not normalized:
        raise ValueError("No enabled analogy aspects found in analogy_aspects.json.")
    return normalized


def load_analogy_aspects():
    return _normalize_analogy_aspects(_load_raw_analogy_aspects())


ANALOGY_ASPECTS = load_analogy_aspects()


def get_analogy_jobs():
    jobs = []
    for aspect_name, aspect_config in ANALOGY_ASPECTS.items():
        jobs.append((
            aspect_name,
            aspect_config.get("stage", f"analogy_{aspect_name}"),
            aspect_config["prompt"],
        ))
    return jobs


def is_non_empty_analogy_result(value):
    return isinstance(value, str) and bool(value.strip())


def non_empty_analogy_results(analogy_results):
    filtered_items = []
    for aspect_name, aspect_config in ANALOGY_ASPECTS.items():
        proposal = analogy_results.get(aspect_name)
        if not is_non_empty_analogy_result(proposal):
            continue
        filtered_items.append((aspect_name, aspect_config, proposal.strip()))
    return filtered_items


def count_non_empty_analogy_results(analogy_results):
    return len(non_empty_analogy_results(analogy_results))


def build_concept_expansion_prompt(analogy_structured_results):
    structured_json = json.dumps(analogy_structured_results, ensure_ascii=False, indent=2)
    return build_concept_expansion_prompt_text(structured_json)


def build_analogy_composite_prompt(analogy_results, concept_expansion=None):
    aspect_items = non_empty_analogy_results(analogy_results)
    if not aspect_items:
        return None
    concept_expansion_json = None
    if concept_expansion:
        concept_expansion_json = json.dumps(concept_expansion, ensure_ascii=False, indent=2)
    return build_analogy_composite_prompt_text(aspect_items, concept_expansion_json)
