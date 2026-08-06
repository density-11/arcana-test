"""Parsing and normalization helpers for analogy-target responses."""

import ast
import json
import re


def _extract_json_like_object(text):
    if not isinstance(text, str) or not text.strip():
        return None
    text = text.strip()
    fenced_blocks = re.findall(r"```json\s*([\s\S]*?)```", text)
    candidates = [block.strip() for block in fenced_blocks]
    candidates.append(text)
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            pass
        try:
            return ast.literal_eval(candidate)
        except Exception:
            pass
    return None


def _first_non_empty(mapping, keys):
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def normalize_objects(value, max_objects=5, max_words=3):
    if value is None:
        candidates = []
    elif isinstance(value, str):
        candidates = []
        for line in value.replace(";", ",").splitlines():
            candidates.extend(part.strip() for part in line.split(","))
    elif isinstance(value, (list, tuple)):
        candidates = value
    else:
        candidates = [value]

    objects = []
    seen = set()
    for candidate in candidates:
        if isinstance(candidate, dict):
            candidate = candidate.get("name") or candidate.get("object") or candidate.get("Object")
        if not isinstance(candidate, str):
            candidate = str(candidate)
        candidate = candidate.strip().strip("-*0123456789.、:：")
        if not candidate:
            continue
        words = candidate.split()
        if len(words) > max_words:
            candidate = " ".join(words[:max_words])
        dedupe_key = candidate.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        objects.append(candidate)
        if len(objects) >= max_objects:
            break
    return objects


def normalize_text_items(value, max_items=6):
    if value is None:
        candidates = []
    elif isinstance(value, str):
        candidates = []
        for line in value.replace(";", "\n").splitlines():
            stripped = line.strip()
            if stripped:
                candidates.append(stripped)
    elif isinstance(value, (list, tuple)):
        candidates = value
    else:
        candidates = [value]

    items = []
    seen = set()
    for candidate in candidates:
        if isinstance(candidate, dict):
            candidate = json.dumps(candidate, ensure_ascii=False)
        elif not isinstance(candidate, str):
            candidate = str(candidate)
        candidate = candidate.strip().strip("-*0123456789.、:：")
        if not candidate:
            continue
        dedupe_key = candidate.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(candidate)
        if len(items) >= max_items:
            break
    return items


def _first_existing_value(mapping, keys):
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def normalize_analogy_target(target):
    if not isinstance(target, dict):
        return None

    analogy = _first_non_empty(target, ["Analogy", "analogy", "target", "Target"])
    if not analogy:
        return None

    reason = _first_non_empty(target, ["Reason", "reason"])
    rule = _first_non_empty(target, [
        "Rule",
        "rule",
        "Transformation_rule",
        "transformation_rule",
        "Transformation Rule",
        "transformation rule",
    ])
    if not reason:
        reason = rule or "No explicit reason was provided."

    objects_value = None
    for key in [
        "Objects",
        "objects",
        "Parsing_objects",
        "parsing_objects",
        "Parsing Objects",
        "parsing objects",
    ]:
        if key in target:
            objects_value = target[key]
            break

    used_expansion_concepts = normalize_text_items(_first_existing_value(target, [
        "Used_expansion_concepts",
        "used_expansion_concepts",
        "Used expansion concepts",
        "used expansion concepts",
        "Expansion_concepts",
        "expansion_concepts",
    ]), max_items=6)
    used_quantitative_mechanisms = normalize_text_items(_first_existing_value(target, [
        "Used_quantitative_mechanisms",
        "used_quantitative_mechanisms",
        "Used quantitative mechanisms",
        "used quantitative mechanisms",
        "Quantitative_mechanisms",
        "quantitative_mechanisms",
    ]), max_items=6)
    implementation_notes = normalize_text_items(_first_existing_value(target, [
        "Implementation_notes",
        "implementation_notes",
        "Implementation notes",
        "implementation notes",
    ]), max_items=6)
    speculative_warnings = normalize_text_items(_first_existing_value(target, [
        "Speculative_warnings",
        "speculative_warnings",
        "Speculative warnings",
        "speculative warnings",
        "Warnings",
        "warnings",
    ]), max_items=6)

    return {
        "Analogy": analogy,
        "Reason": reason,
        "Rule": rule,
        "Objects": normalize_objects(objects_value),
        "Used_expansion_concepts": used_expansion_concepts,
        "Used_quantitative_mechanisms": used_quantitative_mechanisms,
        "Implementation_notes": implementation_notes,
        "Speculative_warnings": speculative_warnings,
    }


def normalize_analogy_targets(parsed, required_count=3):
    if isinstance(parsed, dict):
        targets = parsed.get("Analogy_list")
    else:
        targets = parsed
    if not isinstance(targets, list):
        return None

    normalized_targets = []
    for target in targets:
        normalized = normalize_analogy_target(target)
        if normalized is None:
            continue
        normalized_targets.append(normalized)
        if len(normalized_targets) >= required_count:
            break
    if len(normalized_targets) < required_count:
        return None
    return {"Analogy_list": normalized_targets}


def parse_single_analogy_target_response(response):
    obj = _extract_json_like_object(response)
    if isinstance(obj, dict) and "Analogy_list" in obj:
        targets = normalize_analogy_targets(obj, required_count=1)
        if targets is None:
            return None
        return targets["Analogy_list"][0]
    return normalize_analogy_target(obj)
