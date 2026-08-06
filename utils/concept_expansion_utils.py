"""Parsing helpers for concept-expansion responses."""

import ast
import json
import re

from .analogy_target_utils import normalize_objects


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


def _first_value(mapping, keys):
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _clean_text(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return value.strip()


def _normalize_text_list(value, max_items=8):
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

    output = []
    seen = set()
    for candidate in candidates:
        candidate = _clean_text(candidate).strip("-*0123456789.、:：")
        if not candidate:
            continue
        dedupe_key = candidate.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        output.append(candidate)
        if len(output) >= max_items:
            break
    return output


def normalize_concept_expansion(parsed):
    if not isinstance(parsed, dict):
        return None

    higher_raw = _first_value(parsed, [
        "Higher_level_concepts",
        "higher_level_concepts",
        "Higher-level concepts",
        "higher-level concepts",
    ]) or []
    relationships_raw = _first_value(parsed, [
        "Object_relationships",
        "object_relationships",
        "Object relationships",
        "object relationships",
    ]) or []
    subconcepts_raw = _first_value(parsed, [
        "Attached_subconcepts",
        "attached_subconcepts",
        "Attached subconcepts",
        "attached subconcepts",
    ]) or []
    mutations_raw = _first_value(parsed, [
        "Concept_mutations",
        "concept_mutations",
        "Concept mutations",
        "concept mutations",
    ]) or []
    quantitative_raw = _first_value(parsed, [
        "Quantitative_mechanisms",
        "quantitative_mechanisms",
        "Quantitative mechanisms",
        "quantitative mechanisms",
        "Quantitative_parameters",
        "quantitative_parameters",
        "Quantitative parameters",
        "quantitative parameters",
    ]) or []

    higher_level_concepts = []
    if not isinstance(higher_raw, list):
        higher_raw = [higher_raw]
    for item in higher_raw:
        if isinstance(item, dict):
            concept = _clean_text(_first_value(item, ["Concept", "concept", "Name", "name"]))
            source = _normalize_text_list(_first_value(item, ["Source", "source", "Sources", "sources"]), max_items=5)
            reason = _clean_text(_first_value(item, ["Reason", "reason"]))
        else:
            concept = _clean_text(item)
            source = []
            reason = ""
        if concept:
            higher_level_concepts.append({
                "Concept": concept,
                "Source": source,
                "Reason": reason,
            })

    object_relationships = []
    if not isinstance(relationships_raw, list):
        relationships_raw = [relationships_raw]
    for item in relationships_raw:
        if not isinstance(item, dict):
            continue
        objects = normalize_objects(
            _first_value(item, ["Objects", "objects", "Object_pair", "object_pair"]),
            max_objects=5,
            max_words=3,
        )
        relation = _clean_text(_first_value(item, ["Relation", "relation"]))
        reason = _clean_text(_first_value(item, ["Reason", "reason"]))
        if objects and relation:
            object_relationships.append({
                "Objects": objects,
                "Relation": relation,
                "Reason": reason,
            })

    attached_subconcepts = []
    if not isinstance(subconcepts_raw, list):
        subconcepts_raw = [subconcepts_raw]
    for item in subconcepts_raw:
        if not isinstance(item, dict):
            continue
        object_name = normalize_objects(
            _first_value(item, ["Object", "object", "Name", "name"]),
            max_objects=1,
            max_words=3,
        )
        subconcepts = normalize_objects(
            _first_value(item, ["Subconcepts", "subconcepts", "Concepts", "concepts"]),
            max_objects=8,
            max_words=3,
        )
        reason = _clean_text(_first_value(item, ["Reason", "reason"]))
        if object_name and subconcepts:
            attached_subconcepts.append({
                "Object": object_name[0],
                "Subconcepts": subconcepts,
                "Reason": reason,
            })

    quantitative_mechanisms = []
    if not isinstance(quantitative_raw, list):
        quantitative_raw = [quantitative_raw]
    for item in quantitative_raw:
        if isinstance(item, dict):
            concept = _clean_text(_first_value(item, [
                "Concept",
                "concept",
                "Name",
                "name",
            ]))
            related_objects = normalize_objects(
                _first_value(item, [
                    "Related_objects",
                    "related_objects",
                    "Related objects",
                    "related objects",
                    "Objects",
                    "objects",
                ]),
                max_objects=5,
                max_words=3,
            )
            candidate_parameter = _clean_text(_first_value(item, [
                "Candidate_parameter",
                "candidate_parameter",
                "Candidate parameter",
                "candidate parameter",
                "Parameter",
                "parameter",
            ]))
            mechanism = _clean_text(_first_value(item, [
                "Mechanism",
                "mechanism",
                "Rule",
                "rule",
            ]))
            evidence_to_check = _normalize_text_list(_first_value(item, [
                "Evidence_to_check",
                "evidence_to_check",
                "Evidence to check",
                "evidence to check",
            ]), max_items=8)
        else:
            concept = _clean_text(item)
            related_objects = []
            candidate_parameter = ""
            mechanism = ""
            evidence_to_check = []
        if concept or candidate_parameter or mechanism:
            quantitative_mechanisms.append({
                "Concept": concept,
                "Related_objects": related_objects,
                "Candidate_parameter": candidate_parameter,
                "Mechanism": mechanism,
                "Evidence_to_check": evidence_to_check,
            })

    concept_mutations = []
    if not isinstance(mutations_raw, list):
        mutations_raw = [mutations_raw]
    for item in mutations_raw:
        if not isinstance(item, dict):
            continue
        base_hypothesis = _clean_text(_first_value(item, [
            "Base_hypothesis",
            "base_hypothesis",
            "Base hypothesis",
            "base hypothesis",
        ]))
        preserved_assumptions = _normalize_text_list(_first_value(item, [
            "Preserved_assumptions",
            "preserved_assumptions",
            "Preserved assumptions",
            "preserved assumptions",
        ]), max_items=8)
        mutated_dimension = _clean_text(_first_value(item, [
            "Mutated_dimension",
            "mutated_dimension",
            "Mutated dimension",
            "mutated dimension",
        ]))
        mutated_assumption = _clean_text(_first_value(item, [
            "Mutated_assumption",
            "mutated_assumption",
            "Mutated assumption",
            "mutated assumption",
        ]))
        candidate_concept = _clean_text(_first_value(item, [
            "Candidate_concept",
            "candidate_concept",
            "Candidate concept",
            "candidate concept",
            "Concept",
            "concept",
        ]))
        why_it_might_help = _clean_text(_first_value(item, [
            "Why_it_might_help",
            "why_it_might_help",
            "Why it might help",
            "why it might help",
            "Reason",
            "reason",
        ]))
        evidence_to_check = _normalize_text_list(_first_value(item, [
            "Evidence_to_check",
            "evidence_to_check",
            "Evidence to check",
            "evidence to check",
        ]), max_items=8)
        if candidate_concept:
            concept_mutations.append({
                "Base_hypothesis": base_hypothesis,
                "Preserved_assumptions": preserved_assumptions,
                "Mutated_dimension": mutated_dimension,
                "Mutated_assumption": mutated_assumption,
                "Candidate_concept": candidate_concept,
                "Why_it_might_help": why_it_might_help,
                "Evidence_to_check": evidence_to_check,
            })

    normalized = {
        "Higher_level_concepts": higher_level_concepts,
        "Object_relationships": object_relationships,
        "Attached_subconcepts": attached_subconcepts,
        "Quantitative_mechanisms": quantitative_mechanisms,
        "Concept_mutations": concept_mutations,
    }
    if not any(normalized.values()):
        return None
    return normalized


def parse_concept_expansion_response(response):
    return normalize_concept_expansion(_extract_json_like_object(response))
