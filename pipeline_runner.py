import json
import logging
import os
import random
import re
import subprocess
import threading
import copy
import html
from concurrent.futures import ThreadPoolExecutor, as_completed

import openai

from api_routing import (
    normalize_api_route,
    resolve_openai_client_kwargs,
)
from model_routing import resolve_arc_model, resolve_chat_model
from prompts import (
    code_prompt, rectify_code_prompt, question_code_prompt,
    modify_code_prompt, crossover_code_prompt, mutate_analogy_prompt, mutate_code_prompt,
    abnormal_code_prompt, small_mutation_code_prompt, final_rectify_code_prompt,
    breaking_code_prompt, compositional_introspection_prompt,
    direct_grid_prediction_prompt, direct_grid_arbitration_prompt,
)
from analogy_aspects import (
    ANALOGY_ASPECTS,
    build_analogy_composite_prompt,
    build_concept_expansion_prompt,
    count_non_empty_analogy_results,
    get_analogy_jobs,
)
from utils.common_utils import (
    _read_task_file, build_per_test_results, calculate_cost, parse_answer,
    get_similarity_mask_batch, metrics_code_grid, extract_section, clean_code,
    is_safe_code,
)
from utils.visualization import (
    save_vis_data_temp, vis_data_for_VLM, vis_difference_grid_for_LLM,
    vis_result_grid_for_LLM,
)
from pipeline_ablations import (
    build_task_name_hint,
    generate_direct_analogy_targets,
    inject_task_name_hint,
    validate_ablation_name,
)
from utils.analogy_target_utils import (
    normalize_analogy_target,
    normalize_analogy_targets,
    parse_single_analogy_target_response,
)
from utils.concept_expansion_utils import parse_concept_expansion_response
from utils.direct_grid_utils import (
    compare_direct_and_code_outputs,
    parse_direct_grid_arbitration_response,
    parse_direct_grid_prediction_response,
)

def normalize_pipeline_analogy_context(value):
    if not isinstance(value, dict):
        return {
                "Analogy": "",
                "Reason": "",
                "Rule": "",
                "Objects": [],
                "Used_expansion_concepts": [],
                "Used_quantitative_mechanisms": [],
                "Implementation_notes": [],
                "Speculative_warnings": [],
                }
    normalized = normalize_analogy_target(value)
    if normalized is not None:
        return normalized
    analogy = value.get("analogy") or value.get("Analogy") or value.get("target") or value.get("Target") or ""
    reason = value.get("reason") or value.get("Reason") or ""
    rule = value.get("rule") or value.get("Rule") or ""
    objects = value.get("objects") or value.get("Objects") or []
    if isinstance(objects, str):
        objects = [objects]
    if not isinstance(objects, list):
        objects = []
    used_expansion_concepts = value.get("Used_expansion_concepts") or value.get("used_expansion_concepts") or []
    used_quantitative_mechanisms = value.get("Used_quantitative_mechanisms") or value.get("used_quantitative_mechanisms") or []
    implementation_notes = value.get("Implementation_notes") or value.get("implementation_notes") or []
    speculative_warnings = value.get("Speculative_warnings") or value.get("speculative_warnings") or []
    if isinstance(used_expansion_concepts, str):
        used_expansion_concepts = [used_expansion_concepts]
    if isinstance(used_quantitative_mechanisms, str):
        used_quantitative_mechanisms = [used_quantitative_mechanisms]
    if isinstance(implementation_notes, str):
        implementation_notes = [implementation_notes]
    if isinstance(speculative_warnings, str):
        speculative_warnings = [speculative_warnings]
    return {
            "Analogy": str(analogy or "").strip(),
            "Reason": str(reason or "").strip(),
            "Rule": str(rule or "").strip(),
            "Objects": [str(obj).strip() for obj in objects if str(obj).strip()],
            "Used_expansion_concepts": [str(item).strip() for item in used_expansion_concepts if str(item).strip()] if isinstance(used_expansion_concepts, list) else [],
            "Used_quantitative_mechanisms": [str(item).strip() for item in used_quantitative_mechanisms if str(item).strip()] if isinstance(used_quantitative_mechanisms, list) else [],
            "Implementation_notes": [str(item).strip() for item in implementation_notes if str(item).strip()] if isinstance(implementation_notes, list) else [],
            "Speculative_warnings": [str(item).strip() for item in speculative_warnings if str(item).strip()] if isinstance(speculative_warnings, list) else [],
            }


def format_analogy_context(value, title="Analogy context"):
    context = normalize_pipeline_analogy_context(value)
    return (
            f"{title}:\n"
            f"Analogy: {context['Analogy']}\n"
            f"Reason: {context['Reason']}\n"
            f"Rule: {context['Rule']}\n"
            f"Objects: {json.dumps(context['Objects'], ensure_ascii=False)}\n"
            f"Selected expansion concepts: {json.dumps(context.get('Used_expansion_concepts', []), ensure_ascii=False)}\n"
            f"Selected quantitative mechanisms: {json.dumps(context.get('Used_quantitative_mechanisms', []), ensure_ascii=False)}\n"
            f"Implementation notes: {json.dumps(context.get('Implementation_notes', []), ensure_ascii=False)}\n"
            f"Speculative warnings: {json.dumps(context.get('Speculative_warnings', []), ensure_ascii=False)}"
            )


def format_other_analogy_contexts(programs_dict, current_code_file_name=None):
    lines = ["Other analogy contexts you can consider:"]
    index = 1
    for code_file_name, code_file_dict in programs_dict.items():
        if code_file_name == "circulate times" or not isinstance(code_file_dict, dict):
            continue
        if current_code_file_name is not None and code_file_name == current_code_file_name:
            continue
        lines.append(f"{index}. {format_analogy_context(code_file_dict, 'Analogy context')}")
        index += 1
    if index == 1:
        lines.append("None.")
    return "\n".join(lines)


def extract_provider_error_message(response):
    choices = getattr(response, "choices", None)
    if not choices:
        return None
    choice = choices[0]
    finish_reason = getattr(choice, "finish_reason", None)
    error = getattr(choice, "error", None)
    if finish_reason != "error" and not error:
        return None
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message")
        metadata = error.get("metadata") or {}
        error_type = metadata.get("error_type") if isinstance(metadata, dict) else None
        details = []
        if code not in [None, ""]:
            details.append(str(code))
        if error_type:
            details.append(str(error_type))
        if message:
            details.append(str(message))
        return ": ".join(details) if details else str(error)
    if error:
        return str(error)
    return f"finish_reason={finish_reason}"


def _build_pipeline_flow_html(pipeline_flow):
    task_name = html.escape(str(pipeline_flow.get("task", "")))
    task_output_name = html.escape(str(pipeline_flow.get("task_output_name", "")))
    model_name = html.escape(str(pipeline_flow.get("model", "")))
    ablation_name = html.escape(str(pipeline_flow.get("ablation", "none")))
    nodes = list(pipeline_flow.get("nodes", {}).values())
    events = list(pipeline_flow.get("events", []))
    flow_html_dir = pipeline_flow.get("flow_html_dir")
    valid_summary = pipeline_flow.get("pipeline_valid_correctness", {})
    valid_summary_text = (
        f"pipeline valid correct: {valid_summary.get('valid_correct_count', 0)}/"
        f"{valid_summary.get('valid_program_count', 0)}"
    )

    def link_href(path):
        if not path:
            return ""
        try:
            if flow_html_dir:
                path = os.path.relpath(path, start = flow_html_dir)
        except ValueError:
            pass
        return html.escape(path.replace(os.sep, "/"), quote = True)

    def visual_label(visual):
        if visual.get("temp"):
            return f"round {visual.get('round', '')}"
        if visual.get("cot"):
            return "result cot"
        return "result"

    def visual_links(visuals, round_filter = None):
        links = []
        seen_paths = set()
        for visual in sorted(visuals, key = visual_sort_key):
            if round_filter is not None and visual.get("round") not in [round_filter, str(round_filter)]:
                continue
            path = visual.get("path") or visual.get("compat_path")
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            href = link_href(path)
            if not href:
                continue
            label = html.escape(visual_label(visual))
            links.append(f'<a href="{href}" target="_blank">{label}</a>')
        return " ".join(links)

    def first_visual_href(visuals, round_filter = None):
        for visual in sorted(visuals, key = visual_sort_key):
            if round_filter is not None and visual.get("round") not in [round_filter, str(round_filter)]:
                continue
            path = visual.get("path") or visual.get("compat_path")
            href = link_href(path)
            if href:
                return href
        return ""

    def node_analogy_text(node):
        details = node.get("details", {}) or {}
        analogy = (
                details.get("analogy")
                or node.get("analogy")
                or details.get("Analogy")
                or ""
                )
        reason = (
                details.get("reason")
                or node.get("reason")
                or details.get("Reason")
                or ""
                )
        return str(analogy or ""), str(reason or "")

    def node_rule_objects_text(node):
        details = node.get("details", {}) or {}
        rule = details.get("rule") or details.get("Rule") or node.get("rule") or ""
        objects = details.get("objects") or details.get("Objects") or node.get("objects") or []
        if isinstance(objects, (list, tuple)):
            objects_text = ", ".join(str(item) for item in objects if item not in [None, ""])
        elif objects in [None, ""]:
            objects_text = ""
        else:
            objects_text = str(objects)
        return str(rule or ""), objects_text

    def short_text(value, limit = 72):
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if len(text) <= limit:
            return text
        return text[:max(0, limit - 3)].rstrip() + "..."

    def round_label(round_value):
        if round_value in [None, ""]:
            return "final"
        try:
            if int(round_value) == 0:
                return "init"
        except (TypeError, ValueError):
            pass
        return f"circ {round_value}"

    def event_label(event):
        event_type = str(event.get("type", "event")).replace("_", " ")
        round_value = event.get("round")
        if round_value in [None, ""]:
            return event_type
        return f"{round_label(round_value)}: {event_type}"

    def visual_sort_key(visual):
        if visual.get("temp"):
            try:
                return (0, int(visual.get("round", 0)))
            except (TypeError, ValueError):
                return (0, 999999)
        if visual.get("cot"):
            return (1, 0)
        return (2, 0)

    if not nodes:
        nodes = [{
            "id": "no_code",
            "label": "no_code",
            "created_by": "none",
            "created_round": 0,
            "path": "",
        }]

    def node_round(node):
        round_value = node.get("created_round")
        if round_value is None:
            return 0
        return round_value

    nodes.sort(key=lambda node: (node_round(node), node.get("label", "")))
    round_groups = {}
    for node in nodes:
        round_groups.setdefault(node_round(node), []).append(node)

    self_event_count_by_target = {}
    for event in events:
        source = event.get("source")
        target = event.get("target")
        if target and (source == target or source is None):
            self_event_count_by_target[target] = self_event_count_by_target.get(target, 0) + 1

    positions = {}
    round_values = sorted(round_groups)
    max_column_height = 0
    for round_index, round_value in enumerate(round_values):
        group = round_groups[round_value]
        x = 120 + round_index * 280
        y = 90
        for node in group:
            positions[node["id"]] = (x, y)
            self_event_count = self_event_count_by_target.get(node["id"], 0)
            node_slot_height = 165 + max(0, self_event_count) * 30
            y += node_slot_height
        max_column_height = max(max_column_height, y)

    width = max(980, 260 + len(round_values) * 280)
    height = max(520, max_column_height + 80)
    event_styles = {
        "initial_programming": ("#3f6fb5", "#dceafe"),
        "loaded_prior_code": ("#6b7280", "#f3f4f6"),
        "modify": ("#6b7280", "#f3f4f6"),
        "rectify": ("#8b5cf6", "#ede9fe"),
        "final_rectify": ("#8b5cf6", "#ede9fe"),
        "small_mutation": ("#b45309", "#fef3c7"),
        "mutation": ("#0f766e", "#ccfbf1"),
        "mutation_failed": ("#b91c1c", "#fee2e2"),
        "crossover": ("#2563eb", "#dbeafe"),
        "crossover_failed": ("#b91c1c", "#fee2e2"),
        "pipeline_validated": ("#15803d", "#dcfce7"),
        "pipeline_abnormal": ("#b91c1c", "#fee2e2"),
    }

    edge_parts = []
    self_event_counts = {}
    for event in events:
        event_type = event.get("type", "event")
        source = event.get("source")
        target = event.get("target")
        color, fill = event_styles.get(event_type, ("#475569", "#e2e8f0"))
        label = html.escape(event_label(event))
        if source in positions and target in positions and source != target:
            x1, y1 = positions[source]
            x2, y2 = positions[target]
            stroke_dash = ' stroke-dasharray="7 5"' if event.get("status") != "success" else ""
            stroke_width = "3.2" if event_type.startswith("crossover") else "2.5"
            source_label = html.escape(str(source))
            target_label = html.escape(str(target))
            if abs(x1 - x2) < 1:
                start_x = x1 + 86
                end_x = x2 + 86
                control_x = x1 + 210
                path_d = f"M {start_x} {y1} C {control_x} {y1}, {control_x} {y2}, {end_x} {y2}"
                label_x = control_x
                label_y = (y1 + y2) / 2
            else:
                source_side = 86 if x2 > x1 else -86
                target_side = -86 if x2 > x1 else 86
                start_x = x1 + source_side
                end_x = x2 + target_side
                control_dx = max(90, abs(x2 - x1) / 2)
                control1_x = start_x + (control_dx if x2 > x1 else -control_dx)
                control2_x = end_x - (control_dx if x2 > x1 else -control_dx)
                path_d = f"M {start_x} {y1} C {control1_x} {y1}, {control2_x} {y2}, {end_x} {y2}"
                label_x = (start_x + end_x) / 2
                label_y = (y1 + y2) / 2 - 12
            edge_parts.append(
                f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="{stroke_width}" '
                f'marker-end="url(#arrow)"{stroke_dash}>'
                f'<title>{source_label} -> {target_label}: {label}</title>'
                f'</path>'
            )
            edge_parts.append(
                f'<rect x="{label_x - 86}" y="{label_y - 15}" width="172" height="24" rx="6" '
                f'fill="{fill}" stroke="{color}" />'
                f'<text x="{label_x}" y="{label_y + 2}" text-anchor="middle" '
                f'class="edge-label">{label}</text>'
            )
        elif target in positions:
            x, y = positions[target]
            offset = self_event_counts.get(target, 0)
            self_event_counts[target] = offset + 1
            loop_y = y + 48 + offset * 28
            edge_parts.append(
                f'<rect x="{x - 86}" y="{loop_y}" width="172" height="22" rx="6" '
                f'fill="{fill}" stroke="{color}" />'
                f'<text x="{x}" y="{loop_y + 15}" text-anchor="middle" '
                f'class="edge-label">{label}</text>'
            )

    def node_correctness_text(node):
        correctness = node.get("correctness", {})
        correctness_status = correctness.get("status", "unknown")
        correct_num = correctness.get("correct_num")
        all_num = correctness.get("all_num")
        if correct_num is not None and all_num is not None:
            correctness_text = f"{correctness_status} ({correct_num}/{all_num})"
        else:
            correctness_text = correctness_status
        return str(correctness_status), html.escape(str(correctness_text))

    def node_validity_text(node):
        pipeline_valid = node.get("pipeline_valid")
        if pipeline_valid is True:
            return "valid", "pipeline valid"
        if pipeline_valid is False:
            return "invalid", "pipeline abnormal"
        return "unknown", "validity unknown"

    node_parts = []
    for node in nodes:
        x, y = positions[node["id"]]
        label = html.escape(str(node.get("label", node["id"])))
        created_by = html.escape(str(node.get("created_by", "")))
        created_round = html.escape(str(node.get("created_round", "")))
        path = html.escape(str(node.get("path", "")))
        correctness_status, correctness_text = node_correctness_text(node)
        validity_status, validity_text = node_validity_text(node)
        node_class = (
            "node node-correctness-" + re.sub(r"[^a-z0-9_-]+", "-", str(correctness_status).lower())
            + " node-validity-" + re.sub(r"[^a-z0-9_-]+", "-", str(validity_status).lower())
        )
        validity_text = html.escape(validity_text)
        visuals = node.get("visualizations", [])
        primary_href = ""
        if visuals:
            primary_href = link_href((visuals[-1].get("path") or visuals[-1].get("compat_path")))
        node_markup = (
            f'<g class="{node_class}">'
            f'<rect x="{x - 82}" y="{y - 50}" width="164" height="100" rx="8" />'
            f'<text x="{x}" y="{y - 23}" text-anchor="middle" class="node-title">{label}</text>'
            f'<text x="{x}" y="{y - 2}" text-anchor="middle" class="node-sub">{created_by}</text>'
            f'<text x="{x}" y="{y + 17}" text-anchor="middle" class="node-validity">{validity_text}</text>'
            f'<text x="{x}" y="{y + 34}" text-anchor="middle" class="node-correctness">{correctness_text}</text>'
            f'<text x="{x}" y="{y + 48}" text-anchor="middle" class="node-link">visuals: {len(visuals)}</text>'
            f'<title>{path}\nround: {created_round}\n{validity_text}\n{correctness_text}</title>'
            f'</g>'
        )
        if primary_href:
            node_markup = f'<a href="{primary_href}" target="_blank">{node_markup}</a>'
        node_parts.append(node_markup)

    node_visual_rows = []
    for node in nodes:
        visuals = node.get("visualizations", [])
        if not visuals:
            continue
        _, correctness_text = node_correctness_text(node)
        _, validity_text = node_validity_text(node)
        analogy_text, _ = node_analogy_text(node)
        rule_text, objects_text = node_rule_objects_text(node)
        node_visual_rows.append(
            "<tr>"
            f"<td>{html.escape(str(node.get('label', node.get('id', ''))))}</td>"
            f"<td>{html.escape(str(node.get('created_by', '')))}</td>"
            f"<td>{html.escape(validity_text)}</td>"
            f"<td>{correctness_text}</td>"
            f"<td class=\"analogy-cell\"><strong>Analogy:</strong> {html.escape(analogy_text)}<br><strong>Rule:</strong> {html.escape(rule_text)}<br><strong>Objects:</strong> {html.escape(objects_text)}</td>"
            f"<td>{visual_links(visuals)}</td>"
            "</tr>"
        )
    node_visual_table = "\n".join(node_visual_rows) or '<tr><td colspan="6">No visualization files were recorded.</td></tr>'
    nodes_by_id = {node.get("id"): node for node in nodes}

    def timeline_col_sort_key(column_value):
        if column_value == "final":
            return (1, 999999)
        try:
            return (0, int(column_value))
        except (TypeError, ValueError):
            return (0, 999999)

    def timeline_event_matches_round(event, column_value):
        event_round = event.get("round")
        if column_value == "final":
            return event_round in [None, ""]
        return event_round in [column_value, str(column_value)]

    timeline_snapshots_by_col = {}
    timeline_snapshot_by_code_col = {}
    for node in nodes:
        code_id = node.get("id")
        for visual in sorted(node.get("visualizations", []), key = visual_sort_key):
            column_value = visual.get("round") if visual.get("temp") else "final"
            path = visual.get("path") or visual.get("compat_path")
            href = link_href(path)
            if not href:
                continue
            snapshot = {
                    "code_id": code_id,
                    "node": node,
                    "visual": visual,
                    "href": href,
                    "column": column_value,
                    }
            timeline_snapshots_by_col.setdefault(column_value, []).append(snapshot)
            timeline_snapshot_by_code_col[(code_id, column_value)] = snapshot

    timeline_columns = sorted(timeline_snapshots_by_col.keys(), key = timeline_col_sort_key)
    timeline_positions = {}
    timeline_parts = []
    timeline_edge_parts = []
    timeline_preview_parts = []
    timeline_width = max(980, 260 + len(timeline_columns) * 310)
    timeline_height = 520
    for column_index, column_value in enumerate(timeline_columns):
        x = 125 + column_index * 310
        timeline_parts.append(
            f'<text x="{x}" y="32" text-anchor="middle" class="timeline-heading">{html.escape(round_label(column_value))}</text>'
        )
        column_snapshots = sorted(timeline_snapshots_by_col[column_value], key = lambda item: item["code_id"])
        y = 82
        for snapshot in column_snapshots:
            node = snapshot["node"]
            code_id = snapshot["code_id"]
            timeline_positions[(code_id, column_value)] = (x, y)
            _, correctness_text = node_correctness_text(node)
            _, validity_text = node_validity_text(node)
            analogy_text, reason_text = node_analogy_text(node)
            rule_text, objects_text = node_rule_objects_text(node)
            short_analogy = short_text(analogy_text, 30) or "no analogy recorded"
            short_objects = short_text(objects_text, 30) or "no objects recorded"
            preview_href = snapshot["href"] or first_visual_href(node.get("visualizations", []), column_value)
            preview_x = x + 104
            if preview_x + 250 > timeline_width:
                preview_x = x - 354
            preview_y = max(42, y - 54)
            event_badges = []
            for event in events:
                if event.get("target") != code_id:
                    continue
                if not timeline_event_matches_round(event, column_value):
                    continue
                badge_type = str(event.get("type", "event")).replace("_", " ")
                event_badges.append(html.escape(badge_type))
            badge_lines = []
            for badge_index, badge_text in enumerate(event_badges[:3]):
                badge_y = y + 74 + badge_index * 14
                badge_lines.append(
                    f'<text x="{x}" y="{badge_y}" text-anchor="middle" class="timeline-badge">{badge_text}</text>'
                )
            if len(event_badges) > 3:
                badge_lines.append(
                    f'<text x="{x}" y="{y + 116}" text-anchor="middle" class="timeline-badge">+{len(event_badges) - 3} events</text>'
                )
            if preview_href:
                timeline_preview_parts.append(
                    f'<a href="{snapshot["href"]}" target="_blank" class="timeline-hover-anchor">'
                    f'<rect x="{x - 92}" y="{y - 36}" width="184" height="138" fill="#ffffff" opacity="0" />'
                    f'<foreignObject x="{preview_x}" y="{preview_y}" width="250" height="310" class="timeline-preview">'
                    f'<div xmlns="http://www.w3.org/1999/xhtml" class="preview-card">'
                    f'<img src="{preview_href}" alt="{html.escape(code_id, quote=True)} visualization" />'
                    f'<div class="preview-title">{html.escape(code_id)}</div>'
                    f'<div class="preview-text"><strong>analogy:</strong> {html.escape(analogy_text or "not recorded")}</div>'
                    f'<div class="preview-text"><strong>reason:</strong> {html.escape(reason_text or "not recorded")}</div>'
                    f'<div class="preview-text"><strong>rule:</strong> {html.escape(rule_text or "not recorded")}</div>'
                    f'<div class="preview-text"><strong>objects:</strong> {html.escape(objects_text or "not recorded")}</div>'
                    f'</div>'
                    f'</foreignObject>'
                    f'</a>'
                )
            timeline_parts.append(
                f'<a href="{snapshot["href"]}" target="_blank" class="timeline-anchor">'
                f'<g class="timeline-node">'
                f'<rect x="{x - 92}" y="{y - 36}" width="184" height="138" rx="8" />'
                f'<text x="{x}" y="{y - 12}" text-anchor="middle" class="timeline-title">{html.escape(code_id)}</text>'
                f'<text x="{x}" y="{y + 7}" text-anchor="middle" class="timeline-sub">{html.escape(validity_text)} | {correctness_text}</text>'
                f'<text x="{x}" y="{y + 24}" text-anchor="middle" class="timeline-link">{html.escape(visual_label(snapshot["visual"]))}</text>'
                f'<text x="{x}" y="{y + 43}" text-anchor="middle" class="timeline-analogy">ana: {html.escape(short_analogy)}</text>'
                f'<text x="{x}" y="{y + 56}" text-anchor="middle" class="timeline-objects">obj: {html.escape(short_objects)}</text>'
                f'{"".join(badge_lines)}'
                f'</g>'
                f'</a>'
            )
            y += 185
        timeline_height = max(timeline_height, y + 60)

    def timeline_position_for(code_id, preferred_column):
        if (code_id, preferred_column) in timeline_positions:
            return preferred_column, timeline_positions[(code_id, preferred_column)]
        if preferred_column not in [None, "", "final"]:
            try:
                preferred_value = int(preferred_column)
            except (TypeError, ValueError):
                preferred_value = 0
        else:
            preferred_value = 999999
        candidates = []
        for column_value in timeline_columns:
            if (code_id, column_value) not in timeline_positions:
                continue
            sort_group, sort_value = timeline_col_sort_key(column_value)
            value = 999999 if sort_group == 1 else sort_value
            candidates.append((abs(value - preferred_value), value, column_value, timeline_positions[(code_id, column_value)]))
        if not candidates:
            return None, None
        candidates.sort(key = lambda item: (item[0], item[1]))
        return candidates[0][2], candidates[0][3]

    for node in nodes:
        code_id = node.get("id")
        code_columns = [
                column_value
                for column_value in timeline_columns
                if (code_id, column_value) in timeline_positions
                ]
        code_columns.sort(key = timeline_col_sort_key)
        for previous_column, next_column in zip(code_columns, code_columns[1:]):
            x1, y1 = timeline_positions[(code_id, previous_column)]
            x2, y2 = timeline_positions[(code_id, next_column)]
            timeline_edge_parts.append(
                f'<path d="M {x1 + 94} {y1} C {x1 + 175} {y1}, {x2 - 175} {y2}, {x2 - 94} {y2}" '
                f'fill="none" stroke="#94a3b8" stroke-width="1.8" marker-end="url(#arrow)" />'
            )

    for event in events:
        event_type = event.get("type", "event")
        source = event.get("source")
        target = event.get("target")
        if not source or not target or source == target:
            continue
        event_column = event.get("round")
        _, source_pos = timeline_position_for(source, event_column)
        _, target_pos = timeline_position_for(target, event_column)
        if source_pos is None or target_pos is None:
            continue
        x1, y1 = source_pos
        x2, y2 = target_pos
        color, fill = event_styles.get(event_type, ("#475569", "#e2e8f0"))
        stroke_dash = ' stroke-dasharray="7 5"' if event.get("status") != "success" else ""
        if abs(x1 - x2) < 1:
            control_x = x1 + 150
            path_d = f"M {x1 + 94} {y1 + 14} C {control_x} {y1 + 14}, {control_x} {y2 - 14}, {x2 + 94} {y2 - 14}"
            label_x = control_x
            label_y = (y1 + y2) / 2
        else:
            path_d = f"M {x1 + 94} {y1 + 14} C {x1 + 190} {y1 + 14}, {x2 - 190} {y2 - 14}, {x2 - 94} {y2 - 14}"
            label_x = (x1 + x2) / 2
            label_y = (y1 + y2) / 2 - 16
        label = html.escape(event_label(event))
        timeline_edge_parts.append(
            f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="3" marker-end="url(#arrow)"{stroke_dash} />'
            f'<rect x="{label_x - 86}" y="{label_y - 14}" width="172" height="22" rx="6" fill="{fill}" stroke="{color}" />'
            f'<text x="{label_x}" y="{label_y + 1}" text-anchor="middle" class="edge-label">{label}</text>'
        )
    timeline_svg = (
            f'<svg width="{timeline_width}" height="{timeline_height}" viewBox="0 0 {timeline_width} {timeline_height}" xmlns="http://www.w3.org/2000/svg">'
            '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#475569" /></marker></defs>'
            + ''.join(timeline_edge_parts)
            + ''.join(timeline_parts)
            + ''.join(timeline_preview_parts)
            + '</svg>'
            )

    code_evolution_rows = []
    for node in nodes:
        visuals = sorted(node.get("visualizations", []), key = visual_sort_key)
        if not visuals:
            continue
        route_links = []
        for visual in visuals:
            path = visual.get("path") or visual.get("compat_path")
            href = link_href(path)
            if not href:
                continue
            route_links.append(
                f'<a href="{href}" target="_blank">{html.escape(visual_label(visual))}</a>'
            )
        if not route_links:
            continue
        _, correctness_text = node_correctness_text(node)
        _, validity_text = node_validity_text(node)
        analogy_text, reason_text = node_analogy_text(node)
        rule_text, objects_text = node_rule_objects_text(node)
        route_html = ' <span class="route-arrow">-&gt;</span> '.join(route_links)
        code_evolution_rows.append(
            "<tr>"
            f"<td>{html.escape(str(node.get('label', node.get('id', ''))))}</td>"
            f"<td>{round_label(node_round(node))}</td>"
            f"<td>{html.escape(validity_text)}</td>"
            f"<td>{correctness_text}</td>"
            f"<td class=\"analogy-cell\"><strong>Analogy:</strong> {html.escape(analogy_text)}<br><strong>Reason:</strong> {html.escape(reason_text)}<br><strong>Rule:</strong> {html.escape(rule_text)}<br><strong>Objects:</strong> {html.escape(objects_text)}</td>"
            f"<td>{route_html}</td>"
            "</tr>"
        )
    code_evolution_table = "\n".join(code_evolution_rows) or '<tr><td colspan="6">No code evolution route was recorded.</td></tr>'

    circ_snapshot_rows = []
    for node in nodes:
        for visual in sorted(node.get("visualizations", []), key = visual_sort_key):
            if not visual.get("temp"):
                continue
            path = visual.get("path") or visual.get("compat_path")
            href = link_href(path)
            if not href:
                continue
            circ_snapshot_rows.append(
                "<tr>"
                f"<td>{round_label(visual.get('round'))}</td>"
                f"<td>{html.escape(str(node.get('label', node.get('id', ''))))}</td>"
                f"<td><a href=\"{href}\" target=\"_blank\">{html.escape(visual_label(visual))}</a></td>"
                "</tr>"
            )
    circ_snapshot_rows.sort()
    circ_snapshot_table = "\n".join(circ_snapshot_rows) or '<tr><td colspan="3">No circ snapshot was recorded.</td></tr>'
    nodes_by_id = {node.get("id"): node for node in nodes}
    event_rows = []
    for index, event in enumerate(events, start=1):
        details = event.get("details", {}) or {}
        compact_details = ", ".join(
            f"{key}={value}" for key, value in details.items()
            if value is not None and str(value) != ""
        )
        event_target = event.get("target")
        event_visuals = nodes_by_id.get(event_target, {}).get("visualizations", [])
        event_visual_links = visual_links(event_visuals, event.get("round"))
        event_rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{html.escape(round_label(event.get('round')))}</td>"
            f"<td>{html.escape(str(event.get('type', '')))}</td>"
            f"<td>{html.escape(str(event.get('source', '') or ''))}</td>"
            f"<td>{html.escape(str(event.get('target', '') or ''))}</td>"
            f"<td>{html.escape(str(event.get('status', '') or ''))}</td>"
            f"<td>{event_visual_links}</td>"
            f"<td>{html.escape(compact_details)}</td>"
            "</tr>"
        )
    event_table = "\n".join(event_rows) or '<tr><td colspan="8">No lineage events were recorded.</td></tr>'

    def render_object_badges(value):
        if isinstance(value, (list, tuple)):
            items = [str(item) for item in value if item not in [None, ""]]
        elif value in [None, ""]:
            items = []
        else:
            items = [str(value)]
        if not items:
            return '<span class="muted">not recorded</span>'
        return " ".join(f'<span class="tag">{html.escape(item)}</span>' for item in items)

    def target_value(target, keys):
        if not isinstance(target, dict):
            return ""
        for key in keys:
            value = target.get(key)
            if value not in [None, ""]:
                return value
        return ""

    ablation_details = pipeline_flow.get("ablation_details", {}) or {}
    target_module = str(ablation_details.get("target_module", "not recorded"))
    structured_results = ablation_details.get("analogy_structured_results") or {}
    concept_expansion = ablation_details.get("concept_expansion") or {}
    concept_expansion_status = str(ablation_details.get("concept_expansion_status", "not recorded"))
    final_targets = ablation_details.get("targets") or []
    initial_program_count = len([
        node for node in nodes
        if str(node.get("created_by", "")) == "initial_programming"
    ])

    process_stage_html = (
        '<div class="process-flow">'
        f'<div class="process-card"><div class="process-title">Aspect structured results</div><div class="process-number">{len(structured_results)}</div><div class="process-note">parsed from analogy aspect responses</div></div>'
        '<div class="process-arrow">-&gt;</div>'
        f'<div class="process-card"><div class="process-title">Concept expansion</div><div class="process-number">{html.escape(concept_expansion_status)}</div><div class="process-note">higher concepts, relationships, sub-concepts, quantitative mechanisms, mutations</div></div>'
        '<div class="process-arrow">-&gt;</div>'
        f'<div class="process-card"><div class="process-title">Slippage targets</div><div class="process-number">{len(final_targets)}</div><div class="process-note">module: {html.escape(target_module)}</div></div>'
        '<div class="process-arrow">-&gt;</div>'
        f'<div class="process-card"><div class="process-title">Initial programs</div><div class="process-number">{initial_program_count}</div><div class="process-note">code nodes generated from final targets</div></div>'
        '</div>'
    )

    structured_rows = []
    if isinstance(structured_results, dict):
        for aspect_name, target in structured_results.items():
            structured_rows.append(
                "<tr>"
                f"<td>{html.escape(str(aspect_name))}</td>"
                f"<td>{html.escape(str(target_value(target, ['Analogy', 'analogy'])))}</td>"
                f"<td>{html.escape(str(target_value(target, ['Reason', 'reason'])))}</td>"
                f"<td>{html.escape(str(target_value(target, ['Rule', 'rule'])))}</td>"
                f"<td>{render_object_badges(target_value(target, ['Objects', 'objects']))}</td>"
                "</tr>"
            )
    structured_table = "\n".join(structured_rows) or '<tr><td colspan="5">No structured analogy aspect result was recorded.</td></tr>'

    higher_rows = []
    for item in concept_expansion.get("Higher_level_concepts", []) if isinstance(concept_expansion, dict) else []:
        higher_rows.append(
            "<tr>"
            f"<td>{html.escape(str(target_value(item, ['Concept', 'concept'])))}</td>"
            f"<td>{render_object_badges(target_value(item, ['Source', 'source', 'Sources', 'sources']))}</td>"
            f"<td>{html.escape(str(target_value(item, ['Reason', 'reason'])))}</td>"
            "</tr>"
        )
    higher_table = "\n".join(higher_rows) or '<tr><td colspan="3">No higher-level concept was recorded.</td></tr>'

    relationship_rows = []
    for item in concept_expansion.get("Object_relationships", []) if isinstance(concept_expansion, dict) else []:
        relationship_rows.append(
            "<tr>"
            f"<td>{render_object_badges(target_value(item, ['Objects', 'objects']))}</td>"
            f"<td>{html.escape(str(target_value(item, ['Relation', 'relation'])))}</td>"
            f"<td>{html.escape(str(target_value(item, ['Reason', 'reason'])))}</td>"
            "</tr>"
        )
    relationship_table = "\n".join(relationship_rows) or '<tr><td colspan="3">No object relationship was recorded.</td></tr>'

    subconcept_rows = []
    for item in concept_expansion.get("Attached_subconcepts", []) if isinstance(concept_expansion, dict) else []:
        subconcept_rows.append(
            "<tr>"
            f"<td>{html.escape(str(target_value(item, ['Object', 'object'])))}</td>"
            f"<td>{render_object_badges(target_value(item, ['Subconcepts', 'subconcepts', 'Concepts', 'concepts']))}</td>"
            f"<td>{html.escape(str(target_value(item, ['Reason', 'reason'])))}</td>"
            "</tr>"
        )
    subconcept_table = "\n".join(subconcept_rows) or '<tr><td colspan="3">No attached sub-concept was recorded.</td></tr>'

    quantitative_rows = []
    for item in concept_expansion.get("Quantitative_mechanisms", []) if isinstance(concept_expansion, dict) else []:
        quantitative_rows.append(
            "<tr>"
            f"<td>{html.escape(str(target_value(item, ['Concept', 'concept', 'Name', 'name'])))}</td>"
            f"<td>{render_object_badges(target_value(item, ['Related_objects', 'related_objects', 'Related objects', 'related objects', 'Objects', 'objects']))}</td>"
            f"<td>{html.escape(str(target_value(item, ['Candidate_parameter', 'candidate_parameter', 'Candidate parameter', 'candidate parameter', 'Parameter', 'parameter'])))}</td>"
            f"<td>{html.escape(str(target_value(item, ['Mechanism', 'mechanism', 'Rule', 'rule'])))}</td>"
            f"<td>{render_object_badges(target_value(item, ['Evidence_to_check', 'evidence_to_check', 'Evidence to check', 'evidence to check']))}</td>"
            "</tr>"
        )
    quantitative_table = "\n".join(quantitative_rows) or '<tr><td colspan="5">No quantitative mechanism was recorded.</td></tr>'

    mutation_rows = []
    for item in concept_expansion.get("Concept_mutations", []) if isinstance(concept_expansion, dict) else []:
        mutation_rows.append(
            "<tr>"
            f"<td>{html.escape(str(target_value(item, ['Base_hypothesis', 'base_hypothesis', 'Base hypothesis', 'base hypothesis'])))}</td>"
            f"<td>{render_object_badges(target_value(item, ['Preserved_assumptions', 'preserved_assumptions', 'Preserved assumptions', 'preserved assumptions']))}</td>"
            f"<td>{html.escape(str(target_value(item, ['Mutated_dimension', 'mutated_dimension', 'Mutated dimension', 'mutated dimension'])))}</td>"
            f"<td>{html.escape(str(target_value(item, ['Mutated_assumption', 'mutated_assumption', 'Mutated assumption', 'mutated assumption'])))}</td>"
            f"<td>{html.escape(str(target_value(item, ['Candidate_concept', 'candidate_concept', 'Candidate concept', 'candidate concept'])))}</td>"
            f"<td>{html.escape(str(target_value(item, ['Why_it_might_help', 'why_it_might_help', 'Why it might help', 'why it might help', 'Reason', 'reason'])))}</td>"
            f"<td>{render_object_badges(target_value(item, ['Evidence_to_check', 'evidence_to_check', 'Evidence to check', 'evidence to check']))}</td>"
            "</tr>"
        )
    mutation_table = "\n".join(mutation_rows) or '<tr><td colspan="7">No concept mutation was recorded.</td></tr>'

    final_target_rows = []
    for index, target in enumerate(final_targets, start=1):
        final_target_rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{html.escape(str(target_value(target, ['Analogy', 'analogy'])))}</td>"
            f"<td>{html.escape(str(target_value(target, ['Reason', 'reason'])))}</td>"
            f"<td>{html.escape(str(target_value(target, ['Rule', 'rule'])))}</td>"
            f"<td>{render_object_badges(target_value(target, ['Objects', 'objects']))}</td>"
            f"<td>{render_object_badges(target_value(target, ['Used_expansion_concepts', 'used_expansion_concepts', 'Used expansion concepts', 'used expansion concepts']))}</td>"
            f"<td>{render_object_badges(target_value(target, ['Used_quantitative_mechanisms', 'used_quantitative_mechanisms', 'Used quantitative mechanisms', 'used quantitative mechanisms']))}</td>"
            f"<td>{render_object_badges(target_value(target, ['Implementation_notes', 'implementation_notes', 'Implementation notes', 'implementation notes']))}</td>"
            f"<td>{render_object_badges(target_value(target, ['Speculative_warnings', 'speculative_warnings', 'Speculative warnings', 'speculative warnings']))}</td>"
            "</tr>"
        )
    final_target_table = "\n".join(final_target_rows) or '<tr><td colspan="9">No final slippage target was recorded.</td></tr>'

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Pipeline Flow - {task_output_name}</title>
<style>
body {{ margin: 0; font-family: Arial, sans-serif; color: #172033; background: #f7f8fb; }}
header {{ padding: 22px 28px 10px; background: #ffffff; border-bottom: 1px solid #e5e7eb; }}
h1 {{ margin: 0 0 8px; font-size: 22px; }}
h2 {{ margin: 22px 0 8px; font-size: 16px; }}
.meta {{ color: #5b6472; font-size: 13px; }}
.wrap {{ padding: 18px 28px 32px; }}
.panel {{ background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; overflow: auto; }}
svg {{ display: block; min-width: 100%; }}
.timeline-heading {{ font-size: 14px; font-weight: 800; fill: #111827; }}
.timeline-node rect {{ fill: #ffffff; stroke: #334155; stroke-width: 1.5; }}
.timeline-title {{ font-size: 13px; font-weight: 800; fill: #111827; }}
.timeline-sub {{ font-size: 10px; fill: #374151; font-weight: 700; }}
.timeline-link {{ font-size: 10px; fill: #2563eb; font-weight: 800; }}
.timeline-analogy {{ font-size: 9px; fill: #0f172a; font-weight: 700; }}
.timeline-objects {{ font-size: 9px; fill: #334155; font-weight: 700; }}
.timeline-badge {{ font-size: 9px; fill: #475569; font-weight: 700; }}
.timeline-preview {{ display: none; pointer-events: none; }}
.timeline-hover-anchor:hover .timeline-preview {{ display: block; }}
.preview-card {{ box-sizing: border-box; width: 240px; max-height: 300px; overflow: auto; background: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 8px; box-shadow: 0 12px 28px rgba(15, 23, 42, 0.22); color: #172033; font-size: 11px; line-height: 1.35; }}
.preview-card img {{ display: block; width: 100%; max-height: 118px; object-fit: contain; background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 4px; margin-bottom: 6px; }}
.preview-title {{ font-weight: 800; margin-bottom: 4px; }}
.preview-text {{ white-space: normal; overflow-wrap: anywhere; }}
.node rect {{ fill: #ffffff; stroke: #1f2937; stroke-width: 1.4; }}
.node-correctness-correct rect {{ stroke: #15803d; stroke-width: 3; }}
.node-correctness-partial rect {{ stroke: #ca8a04; stroke-width: 3; }}
.node-correctness-wrong rect {{ stroke: #b91c1c; stroke-width: 3; }}
.node-correctness-error rect {{ stroke: #b91c1c; stroke-width: 3; stroke-dasharray: 6 4; }}
.node-validity-valid rect {{ fill: #f0fdf4; }}
.node-validity-invalid rect {{ fill: #fff1f2; }}
.node-title {{ font-size: 14px; font-weight: 700; fill: #111827; }}
.node-sub {{ font-size: 11px; fill: #6b7280; }}
.node-correctness {{ font-size: 11px; fill: #111827; font-weight: 700; }}
.node-validity {{ font-size: 11px; fill: #374151; font-weight: 700; }}
.node-link {{ font-size: 11px; fill: #2563eb; font-weight: 700; }}
.edge-label {{ font-size: 11px; fill: #111827; font-weight: 700; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 18px; background: #ffffff; }}
th, td {{ border: 1px solid #e5e7eb; padding: 7px 8px; text-align: left; vertical-align: top; }}
th {{ background: #f3f4f6; }}
a {{ color: #1d4ed8; text-decoration: none; font-weight: 700; }}
a:hover {{ text-decoration: underline; }}
td a {{ display: inline-block; margin: 0 8px 4px 0; }}
.analogy-cell {{ max-width: 560px; white-space: normal; overflow-wrap: anywhere; }}
.route-arrow {{ color: #6b7280; font-weight: 700; margin: 0 4px; }}
.process-flow {{ display: grid; grid-template-columns: minmax(160px, 1fr) 32px minmax(160px, 1fr) 32px minmax(160px, 1fr) 32px minmax(160px, 1fr); gap: 10px; align-items: stretch; margin-bottom: 16px; }}
.process-card {{ border: 1px solid #dbe1ea; background: #ffffff; border-radius: 8px; padding: 12px; min-height: 92px; }}
.process-title {{ font-size: 12px; color: #475569; font-weight: 800; text-transform: uppercase; }}
.process-number {{ margin-top: 10px; font-size: 20px; color: #0f172a; font-weight: 800; overflow-wrap: anywhere; }}
.process-note {{ margin-top: 8px; font-size: 12px; color: #64748b; line-height: 1.35; }}
.process-arrow {{ display: flex; align-items: center; justify-content: center; color: #64748b; font-weight: 900; }}
.subgrid {{ display: grid; grid-template-columns: repeat(3, minmax(220px, 1fr)); gap: 14px; margin-top: 14px; }}
.mini-panel {{ border: 1px solid #e5e7eb; border-radius: 8px; overflow: auto; background: #ffffff; }}
.wide-panel {{ grid-column: 1 / -1; }}
.mini-panel h3 {{ margin: 0; padding: 10px 12px; font-size: 13px; background: #f8fafc; border-bottom: 1px solid #e5e7eb; }}
.mini-panel table {{ margin-top: 0; }}
.tag {{ display: inline-block; border: 1px solid #cbd5e1; background: #f8fafc; border-radius: 999px; padding: 2px 7px; margin: 0 4px 4px 0; font-size: 11px; font-weight: 700; color: #334155; }}
.muted {{ color: #94a3b8; font-style: italic; }}
@media (max-width: 980px) {{
  .process-flow {{ grid-template-columns: 1fr; }}
  .process-arrow {{ min-height: 18px; }}
  .subgrid {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<header>
<h1>Pipeline Flow: {task_name}</h1>
<div class="meta">run: {task_output_name} | model: {model_name} | ablation: {ablation_name} | {html.escape(valid_summary_text)}</div>
</header>
<div class="wrap">
<h2>Analogy, Expansion, Slippage</h2>
{process_stage_html}
<table>
<thead><tr><th>aspect</th><th>analogy</th><th>reason</th><th>rule</th><th>objects</th></tr></thead>
<tbody>
{structured_table}
</tbody>
</table>
<div class="subgrid">
<div class="mini-panel">
<h3>Higher-Level Concepts</h3>
<table>
<thead><tr><th>concept</th><th>source</th><th>reason</th></tr></thead>
<tbody>{higher_table}</tbody>
</table>
</div>
<div class="mini-panel">
<h3>Object Relationships</h3>
<table>
<thead><tr><th>objects</th><th>relation</th><th>reason</th></tr></thead>
<tbody>{relationship_table}</tbody>
</table>
</div>
	<div class="mini-panel">
	<h3>Attached Sub-Concepts</h3>
	<table>
	<thead><tr><th>object</th><th>sub-concepts</th><th>reason</th></tr></thead>
	<tbody>{subconcept_table}</tbody>
	</table>
	</div>
	<div class="mini-panel wide-panel">
	<h3>Quantitative Mechanisms</h3>
	<table>
	<thead><tr><th>concept</th><th>objects</th><th>parameter</th><th>mechanism</th><th>evidence</th></tr></thead>
	<tbody>{quantitative_table}</tbody>
	</table>
	</div>
	<div class="mini-panel wide-panel">
	<h3>Concept Mutations</h3>
	<table>
<thead><tr><th>base</th><th>preserved</th><th>dimension</th><th>mutated assumption</th><th>candidate</th><th>why</th><th>evidence</th></tr></thead>
<tbody>{mutation_table}</tbody>
</table>
</div>
</div>
	<h2>Final Slippage Targets</h2>
	<table>
	<thead><tr><th>#</th><th>analogy</th><th>reason</th><th>rule</th><th>objects</th><th>selected expansion</th><th>quantitative mechanisms</th><th>implementation notes</th><th>warnings</th></tr></thead>
	<tbody>
	{final_target_table}
	</tbody>
</table>
<h2>Circ Timeline + Code Lineage</h2>
<div class="panel">
{timeline_svg}
</div>
<h2>Code Evolution Route</h2>
<table>
<thead><tr><th>code</th><th>created circ</th><th>pipeline validity</th><th>correctness</th><th>analogy / reason</th><th>route</th></tr></thead>
<tbody>
{code_evolution_table}
</tbody>
</table>
<h2>Circ Snapshots</h2>
<table>
<thead><tr><th>circ</th><th>code</th><th>visualization</th></tr></thead>
<tbody>
{circ_snapshot_table}
</tbody>
</table>
<h2>Code Visualizations</h2>
<table>
<thead><tr><th>code</th><th>created by</th><th>pipeline validity</th><th>correctness</th><th>analogy</th><th>visualizations</th></tr></thead>
<tbody>
{node_visual_table}
</tbody>
</table>
<h2>Lineage Events</h2>
<table>
<thead><tr><th>#</th><th>round</th><th>type</th><th>source</th><th>target</th><th>status</th><th>visualizations</th><th>details</th></tr></thead>
<tbody>
{event_table}
</tbody>
</table>
</div>
</body>
	</html>
	"""

def generate_pipeline_flow_html_only(
        file_name=None,
        model_chosen="GPT5",
        pipeline_dir="./pipeline",
        ablation="none",
        api_route="default",
        ):
    model_chosen, _, _ = resolve_chat_model(model_chosen, api_route)
    model_output_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", model_chosen).strip("_") or "model"
    ablation_name = validate_ablation_name(ablation)
    pipeline_path_parts = [model_output_name] if ablation_name == "none" else [model_output_name, ablation_name]
    results_model_dir = os.path.join(pipeline_dir, "results", *pipeline_path_parts)
    programs_model_dir = os.path.join(pipeline_dir, "programs", *pipeline_path_parts)
    if not os.path.isdir(results_model_dir):
        print(f"Pipeline results directory does not exist: {results_model_dir}")
        return []

    requested_task = None
    if file_name not in [None, "", "None"]:
        requested_task = os.path.basename(file_name).replace(".json", "")

    def parse_task_run_dir(task_dir_name, task_name):
        match = re.match(rf"^{re.escape(task_name)}(?:_(\d+))?$", task_dir_name)
        if not match:
            return None
        return 0 if match.group(1) is None else int(match.group(1))

    def parse_flow_file(flow_file_name, task_name):
        match = re.match(rf"^pipeline_flow_{re.escape(task_name)}(?:_(\d+))?\.json$", flow_file_name)
        if not match:
            return None
        return 0 if match.group(1) is None else int(match.group(1))

    def task_name_from_flow_file(flow_file_name):
        match = re.match(r"^pipeline_flow_(.+?)(?:_(\d+))?\.json$", flow_file_name)
        if not match:
            return None
        return match.group(1)

    def enrich_flow_with_program_metadata(pipeline_flow, task_name, task_output_name):
        programs_file = os.path.join(programs_model_dir, task_output_name, f"programs_{task_name}.json")
        if not os.path.exists(programs_file):
            return
        try:
            with open(programs_file, "r") as f:
                programs_payload = json.load(f)
        except Exception as e:
            print(f"Failed to read programs metadata from {programs_file}: {e}")
            return
        programs_dict = programs_payload.get(task_name, {}) if isinstance(programs_payload, dict) else {}
        if not isinstance(programs_dict, dict):
            return
        nodes = pipeline_flow.setdefault("nodes", {})
        for code_file_name, code_file_dict in programs_dict.items():
            if code_file_name == "circulate times" or not isinstance(code_file_dict, dict):
                continue
            code_id = os.path.basename(code_file_name).replace(".py", "")
            node = nodes.setdefault(code_id, {
                    "id": code_id,
                    "label": code_id,
                    "path": code_file_name,
                    "created_by": code_file_dict.get("created_by", "programs_metadata"),
                    "created_round": code_file_dict.get("created_round"),
                    "details": {},
                    })
            details = node.setdefault("details", {})
            for key in ["analogy", "reason", "rule", "objects", "explanation", "code reasoning"]:
                if code_file_dict.get(key) not in [None, ""]:
                    details[key] = code_file_dict.get(key)
            for source_key, target_key in [
                    ("created_by", "created_by"),
                    ("created_round", "created_round"),
                    ("pipeline_valid", "pipeline_valid"),
                    ("pipeline_valid_reason", "pipeline_valid_reason"),
                    ("pipeline_valid_round", "pipeline_valid_round"),
                    ]:
                if code_file_dict.get(source_key) not in [None, ""]:
                    node[target_key] = code_file_dict.get(source_key)

    flow_candidates = []
    for task_output_name in os.listdir(results_model_dir):
        task_results_dir = os.path.join(results_model_dir, task_output_name)
        if not os.path.isdir(task_results_dir):
            continue
        if requested_task is not None and parse_task_run_dir(task_output_name, requested_task) is None:
            continue
        for existing_file_name in os.listdir(task_results_dir):
            if not existing_file_name.startswith("pipeline_flow_") or not existing_file_name.endswith(".json"):
                continue
            task_name = requested_task or task_name_from_flow_file(existing_file_name)
            if not task_name:
                continue
            flow_index = parse_flow_file(existing_file_name, task_name)
            if flow_index is None:
                continue
            task_run_index = parse_task_run_dir(task_output_name, task_name)
            if task_run_index is None:
                task_run_index = 0
            flow_candidates.append((
                    task_name,
                    task_run_index,
                    flow_index,
                    task_output_name,
                    os.path.join(task_results_dir, existing_file_name),
                    ))

    if not flow_candidates:
        target_text = requested_task if requested_task else "all tasks"
        print(f"No pipeline flow JSON files found for {target_text} under {results_model_dir}")
        return []

    generated_html_files = []
    flow_candidates.sort(key = lambda item: (item[0], item[1], item[2], item[4]))
    for task_name, task_run_index, flow_index, task_output_name, flow_json_file in flow_candidates:
        try:
            with open(flow_json_file, "r") as f:
                pipeline_flow = json.load(f)
        except Exception as e:
            print(f"Failed to read pipeline flow JSON {flow_json_file}: {e}")
            continue
        if not isinstance(pipeline_flow, dict):
            print(f"Skipped invalid pipeline flow JSON: {flow_json_file}")
            continue
        flow_html_file = os.path.splitext(flow_json_file)[0] + ".html"
        pipeline_flow["task"] = pipeline_flow.get("task") or task_name
        pipeline_flow["task_output_name"] = pipeline_flow.get("task_output_name") or task_output_name
        pipeline_flow["task_run_index"] = pipeline_flow.get("task_run_index", task_run_index)
        pipeline_flow["model"] = pipeline_flow.get("model") or model_output_name
        pipeline_flow["ablation"] = ablation_name
        pipeline_flow["flow_html_file"] = flow_html_file
        pipeline_flow["flow_html_dir"] = os.path.dirname(flow_html_file)
        pipeline_flow.setdefault("nodes", {})
        pipeline_flow.setdefault("events", [])
        enrich_flow_with_program_metadata(pipeline_flow, task_name, task_output_name)
        with open(flow_html_file, "w", encoding = "utf-8") as f:
            f.write(_build_pipeline_flow_html(pipeline_flow))
        generated_html_files.append(flow_html_file)
        print(f"Generated pipeline flow HTML: {flow_html_file}")
    print(f"Generated {len(generated_html_files)} pipeline flow HTML file(s).")
    return generated_html_files

def test_one_file(
        data_dir,
        file_name,
        model_chosen: str,
        upc: str,
        ablation: str = "none",
        direct_grid: str = "f",
        api_route: str = "default",
        pipeline_dir: str = "./pipeline",
        ):
    if file_name == None:
        print(f"file name should not be None")
        return

    path = os.path.join(data_dir, file_name)

    if upc == 'f':
        use_prior_code = False
    elif upc == 't':
        use_prior_code = True
    else:
        print("The parameter upc should be t or f, not others, Default t is set.")
        use_prior_code = True

    api_route_name = normalize_api_route(api_route)
    uni_generation = None
    uni_streaming = None
    if api_route_name == "uni":
        from providers.uni import generation as uni_generation
        from providers.uni import streaming as uni_streaming
    requested_model_chosen = model_chosen
    model_chosen, mc, model_hub_dict = resolve_arc_model(model_chosen, api_route_name)
    auxiliary_model_key = model_chosen
    auxiliary_mc = mc
    introspection_model_key = model_chosen
    introspection_mc = mc
    api_model_to_model_key = {api_model: model_key for model_key, api_model in model_hub_dict.items()}
    model_output_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", model_chosen).strip("_") or "model"
    ablation_name = validate_ablation_name(ablation)
    api_client_kwargs = resolve_openai_client_kwargs(api_route_name)
    uni_generation_settings = (
            uni_generation.resolve_uni_generation_settings("pipeline", model_id=mc)
            if api_route_name == "uni"
            else None
            )
    ex_name = os.path.splitext(os.path.basename(file_name))[0]
    task_name_hint = build_task_name_hint(ex_name) if ablation_name == "task_name" else ""
    direct_grid_enabled = str(direct_grid).lower() == "t"
    pipeline_path_parts = [model_output_name] if ablation_name == "none" else [model_output_name, ablation_name]
    token_context = threading.local()
    token_context.stage = "init"
    token_context.round = None
    token_usage_lock = threading.Lock()
    token_usage = {
            "total": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost": 0},
            "by_stage": {},
            "by_round": {},
            "by_model": {},
            "calls": []
            }
    code_timeout_seconds = float(os.environ.get("ARCANA_CODE_TIMEOUT_SECONDS", "10"))

    def llm_worker_count(job_count, default_workers):
        if api_route_name == "uni":
            configured = os.environ.get("ARCANA_UNI_PIPELINE_LLM_WORKERS", "2")
        else:
            configured = str(default_workers)
        try:
            worker_count = int(configured)
        except ValueError:
            raise ValueError("Pipeline LLM worker count must be a positive integer.")
        return max(1, min(worker_count, job_count))

    def set_token_context(stage, round_sig = None):
        token_context.stage = stage
        token_context.round = round_sig

    def _usage_value(usage, key):
        if usage is None:
            return 0
        if isinstance(usage, dict):
            return usage.get(key, 0) or 0
        return getattr(usage, key, 0) or 0

    def record_token_usage(response, fallback_model):
        usage = getattr(response, "usage", None)
        input_tokens = _usage_value(usage, "prompt_tokens")
        output_tokens = _usage_value(usage, "completion_tokens")
        total_tokens = _usage_value(usage, "total_tokens") or input_tokens + output_tokens
        cost = calculate_cost(fallback_model, input_tokens, output_tokens)
        if cost == 0:
            try:
                cost = float(_usage_value(usage, "cost"))
            except (TypeError, ValueError):
                cost = 0
        stage = getattr(token_context, "stage", "init")
        round_sig = getattr(token_context, "round", None)
        model_key = api_model_to_model_key.get(fallback_model, fallback_model or "unknown")
        call_record = {
                "stage": stage,
                "round": round_sig,
                "model": model_key,
                "api_model": fallback_model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "cost": cost
                }
        with token_usage_lock:
            token_usage["calls"].append(call_record)
            for key, value in [("input_tokens", input_tokens), ("output_tokens", output_tokens), ("total_tokens", total_tokens), ("cost", cost)]:
                token_usage["total"][key] += value
            if model_key not in token_usage["by_model"]:
                token_usage["by_model"][model_key] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost": 0, "calls": 0}
            for key, value in [("input_tokens", input_tokens), ("output_tokens", output_tokens), ("total_tokens", total_tokens), ("cost", cost)]:
                token_usage["by_model"][model_key][key] += value
            token_usage["by_model"][model_key]["calls"] += 1
            if stage not in token_usage["by_stage"]:
                token_usage["by_stage"][stage] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost": 0, "calls": 0}
            for key, value in [("input_tokens", input_tokens), ("output_tokens", output_tokens), ("total_tokens", total_tokens), ("cost", cost)]:
                token_usage["by_stage"][stage][key] += value
            token_usage["by_stage"][stage]["calls"] += 1
            if round_sig is not None:
                round_key = str(round_sig)
                if round_key not in token_usage["by_round"]:
                    token_usage["by_round"][round_key] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost": 0, "calls": 0}
                for key, value in [("input_tokens", input_tokens), ("output_tokens", output_tokens), ("total_tokens", total_tokens), ("cost", cost)]:
                    token_usage["by_round"][round_key][key] += value
                token_usage["by_round"][round_key]["calls"] += 1

    original_openai_client = openai.OpenAI

    class _TrackedCompletions:
        def __init__(self, completions):
            self._completions = completions

        def create(self, *args, **kwargs):
            if task_name_hint and "messages" in kwargs:
                kwargs = dict(kwargs)
                kwargs["messages"] = inject_task_name_hint(kwargs["messages"], task_name_hint)
            if api_route_name == "uni":
                kwargs = uni_generation.apply_uni_generation_settings(kwargs, uni_generation_settings)
            response = self._completions.create(*args, **kwargs)
            if api_route_name == "uni":
                response = uni_streaming.collect_chat_completion_stream(response)
            record_token_usage(response, kwargs.get("model", mc))
            return response

        def __getattr__(self, name):
            return getattr(self._completions, name)

    class _TrackedChat:
        def __init__(self, chat):
            self._chat = chat
            self.completions = _TrackedCompletions(chat.completions)

        def __getattr__(self, name):
            return getattr(self._chat, name)

    class _TrackedOpenAI:
        def __init__(self, *args, **kwargs):
            client_kwargs = dict(kwargs)
            client_kwargs.update(api_client_kwargs)
            self._client = original_openai_client(*args, **client_kwargs)
            self.chat = _TrackedChat(self._client.chat)

        def __getattr__(self, name):
            return getattr(self._client, name)

    openai.OpenAI = _TrackedOpenAI
    exs, ques, ans = _read_task_file(path)

    exs_url, exs_b64 = vis_data_for_VLM(exs, in_out = True)
    ques_url, ques_b64 = vis_data_for_VLM(ques, in_out = False)

    # important parameters
    crossover_rate = 0.4
    circ_times = 0
    max_circ_times = 5
    delta_mutation_rate = 0.15
    coeff_right_delta_mutation = 0.5
    delta_small_mutation_rate = 0.15
    coeff_right_delta_small_mutation = 0.5

    # mutation probablity calculation
    mutation_rate_dict = {}
    small_mutation_rate_dict = {}
    former_correct_rate_dict = {}

    requested_use_prior_code = use_prior_code

    # directory examination
    pipeline_dir = os.path.normpath(pipeline_dir or "./pipeline")
    stats_dir = os.path.join(pipeline_dir, "results")
    visuals_dir = os.path.join(pipeline_dir, "visualizations")
    logs_root_dir = os.path.join(pipeline_dir, "logs")
    programs_root_dir = os.path.join(pipeline_dir, "programs")

    def parse_task_run_index(task_dir_name):
        match = re.match(rf"^{re.escape(ex_name)}(?:_(\d+))?$", task_dir_name)
        if not match:
            return None
        if match.group(1) is None:
            return 0
        return int(match.group(1))

    def iter_pipeline_task_run_dirs(root_dir):
        model_dir = os.path.join(root_dir, *pipeline_path_parts)
        if not os.path.isdir(model_dir):
            return []
        task_run_dirs = []
        for task_dir_name in os.listdir(model_dir):
            task_run_index = parse_task_run_index(task_dir_name)
            if task_run_index is None:
                continue
            task_run_dir = os.path.join(model_dir, task_dir_name)
            if os.path.isdir(task_run_dir):
                task_run_dirs.append((task_run_index, task_dir_name, task_run_dir))
        return task_run_dirs

    def next_fresh_task_output_name():
        existing_indices = []
        for root_dir in [stats_dir, visuals_dir, logs_root_dir, programs_root_dir]:
            existing_indices.extend(
                    task_run_index
                    for task_run_index, _, _ in iter_pipeline_task_run_dirs(root_dir)
                    )
        next_task_run_index = max(existing_indices, default = 0) + 1
        return f"{ex_name}_{next_task_run_index}", next_task_run_index

    def latest_programs_dict_candidate():
        candidates = []
        for task_run_index, task_dir_name, task_run_dir in iter_pipeline_task_run_dirs(programs_root_dir):
            candidate_file = os.path.join(task_run_dir, f"programs_{ex_name}.json")
            if os.path.exists(candidate_file):
                candidates.append((task_run_index, task_dir_name, candidate_file))
        if ablation_name == "none":
            legacy_candidates = [
                (0, ex_name, os.path.join("./programs", model_output_name, ex_name, f"programs_{ex_name}.json")),
                (0, ex_name, os.path.join("./programs", ex_name, f"programs_{ex_name}.json")),
            ]
            candidates.extend(
                    candidate
                    for candidate in legacy_candidates
                    if os.path.exists(candidate[2])
                    )
        if not candidates:
            return None
        candidates.sort(key = lambda candidate: candidate[0])
        return candidates[-1]

    programs_dict_read_file = None
    if requested_use_prior_code:
        prior_candidate = latest_programs_dict_candidate()
        if prior_candidate is None:
            use_prior_code = False
            task_output_name, task_run_index = next_fresh_task_output_name()
        else:
            use_prior_code = True
            task_run_index, task_output_name, programs_dict_read_file = prior_candidate
    else:
        task_output_name, task_run_index = next_fresh_task_output_name()

    programs_dir = os.path.join(programs_root_dir, *pipeline_path_parts, task_output_name)
    os.makedirs(programs_dir, exist_ok = True)
    results_dir = os.path.join(stats_dir, *pipeline_path_parts, task_output_name)
    legacy_results_dirs = [
        os.path.join("./results", model_output_name, ex_name),
        os.path.join("./results", ex_name),
    ]
    os.makedirs(results_dir, exist_ok = True)
    task_visuals_dir = os.path.join(visuals_dir, *pipeline_path_parts, task_output_name)
    os.makedirs(task_visuals_dir, exist_ok = True)

    def next_pipeline_result_file():
        result_name_pattern = re.compile(rf"^result_{re.escape(ex_name)}(?:_(\d+))?\.json$")
        existing_result_indices = []
        for scan_results_dir in [results_dir, *legacy_results_dirs]:
            if not os.path.exists(scan_results_dir):
                continue
            for existing_file_name in os.listdir(scan_results_dir):
                match = result_name_pattern.match(existing_file_name)
                if not match:
                    continue
                if match.group(1) is None:
                    existing_result_indices.append(0)
                else:
                    existing_result_indices.append(int(match.group(1)))
        if not existing_result_indices:
            return os.path.join(results_dir, f"result_{ex_name}.json"), 0
        next_result_index = max(existing_result_indices) + 1
        return os.path.join(results_dir, f"result_{ex_name}_{next_result_index}.json"), next_result_index

    result_file_name, result_run_index = next_pipeline_result_file()
    log_run_suffix = "" if result_run_index == 0 else f"_{result_run_index}"
    logs_dir = os.path.join(logs_root_dir, *pipeline_path_parts, task_output_name)
    os.makedirs(logs_dir, exist_ok=True)
    logging.basicConfig(
            level = logging.INFO,
            format = '%(asctime)s - %(levelname)s - %(message)s',
            filename = os.path.join(logs_dir, f'{ex_name}_test{log_run_suffix}.log'),
            filemode = 'a',
            force = True
            )
    if task_name_hint:
        print(f"Task-name hint ablation enabled: {ex_name}")
        logging.info(f"Task-name hint ablation enabled for {ex_name}; scope=all_llm_calls.")
    print(f"API route: {api_route_name}")
    logging.info(f"API route: {api_route_name}")
    print(f"Model mapping: {requested_model_chosen} -> {mc}")
    logging.info(f"Model mapping: {requested_model_chosen} -> {mc}")
    print(f"Model storage folder: {model_output_name}")
    logging.info(f"Model storage folder: {model_output_name}")
    if uni_generation_settings:
        uni_generation_message = (
                "UNI generation settings: "
                f"max_length={uni_generation_settings['max_length'] or 'provider default'}, "
                "thinking=" + (
                    "provider default"
                    if uni_generation_settings["enable_thinking"] is None
                    else "on" if uni_generation_settings["enable_thinking"] else "off"
                )
                )
        print(uni_generation_message)
        logging.info(uni_generation_message)

    def latest_pipeline_flow_file():
        flow_name_pattern = re.compile(rf"^pipeline_flow_{re.escape(ex_name)}(?:_(\d+))?\.json$")
        flow_candidates = []
        if not os.path.isdir(results_dir):
            return None
        for existing_file_name in os.listdir(results_dir):
            match = flow_name_pattern.match(existing_file_name)
            if not match:
                continue
            flow_index = 0 if match.group(1) is None else int(match.group(1))
            flow_candidates.append((flow_index, os.path.join(results_dir, existing_file_name)))
        if not flow_candidates:
            return None
        flow_candidates.sort(key = lambda candidate: candidate[0])
        return flow_candidates[-1][1]

    usage_total_keys = ("input_tokens", "output_tokens", "total_tokens", "cost")

    def empty_usage_total():
        return {key: 0 for key in usage_total_keys}

    def sanitize_usage_total(source):
        total = empty_usage_total()
        if not isinstance(source, dict):
            return total
        for key in usage_total_keys:
            total[key] = source.get(key, 0) or 0
        return total

    def add_usage_totals(*totals):
        merged = empty_usage_total()
        for total in totals:
            total = sanitize_usage_total(total)
            for key in usage_total_keys:
                merged[key] += total.get(key, 0)
        return merged

    def sanitize_usage_by_model(source):
        if not isinstance(source, dict):
            return {}
        sanitized = {}
        for model_name, model_usage in source.items():
            if not isinstance(model_usage, dict):
                continue
            sanitized[model_name] = sanitize_usage_total(model_usage)
            sanitized[model_name]["calls"] = model_usage.get("calls", 0) or 0
        return sanitized

    def add_usage_by_model(*model_usage_dicts):
        merged = {}
        for model_usage_dict in model_usage_dicts:
            for model_name, model_usage in sanitize_usage_by_model(model_usage_dict).items():
                if model_name not in merged:
                    merged[model_name] = {**empty_usage_total(), "calls": 0}
                for key in usage_total_keys:
                    merged[model_name][key] += model_usage.get(key, 0)
                merged[model_name]["calls"] += model_usage.get("calls", 0)
        return merged

    def candidate_result_files_from_flow(flow_dict, flow_file):
        candidate_files = []
        result_file = flow_dict.get("result_file") if isinstance(flow_dict, dict) else None
        if result_file:
            candidate_files.append(result_file)
            candidate_files.append(os.path.join(os.path.dirname(flow_file), os.path.basename(result_file)))
        flow_base_name = os.path.basename(flow_file)
        inferred_name = flow_base_name.replace("pipeline_flow_", "result_", 1)
        candidate_files.append(os.path.join(os.path.dirname(flow_file), inferred_name))
        seen = set()
        unique_candidates = []
        for candidate_file in candidate_files:
            normalized = os.path.normpath(candidate_file)
            if normalized in seen:
                continue
            seen.add(normalized)
            unique_candidates.append(candidate_file)
        return unique_candidates

    def load_historical_usage_from_flow(flow_dict, flow_file):
        historical_usage = {
                "api_call_count": 0,
                "total": empty_usage_total(),
                "by_model": {},
                "source_file": None
                }
        for candidate_file in candidate_result_files_from_flow(flow_dict, flow_file):
            if not os.path.exists(candidate_file):
                continue
            try:
                with open(candidate_file, "r") as f:
                    prior_result = json.load(f)
            except Exception as e:
                print(f"Failed to load historical token usage from {candidate_file}: {e}")
                logging.info(f"Failed to load historical token usage from {candidate_file}: {e}")
                continue
            if not isinstance(prior_result, dict):
                continue
            historical_usage["api_call_count"] = prior_result.get(
                    "cumulative_api_call_count",
                    prior_result.get("api_call_count", 0)
                    ) or 0
            historical_usage["total"] = {
                    "input_tokens": prior_result.get("cumulative_input_tokens", prior_result.get("input_tokens", 0)) or 0,
                    "output_tokens": prior_result.get("cumulative_output_tokens", prior_result.get("output_tokens", 0)) or 0,
                    "total_tokens": prior_result.get("cumulative_total_tokens", prior_result.get("total_tokens", 0)) or 0,
                    "cost": prior_result.get("cumulative_cost", prior_result.get("cost", 0)) or 0,
                    }
            historical_usage["by_model"] = sanitize_usage_by_model(
                    prior_result.get("cumulative_token_usage_by_model")
                    or prior_result.get("token_usage_by_model")
                    or {}
                    )
            historical_usage["source_file"] = candidate_file
            return historical_usage
        return historical_usage

    pipeline_flow = {
            "task": ex_name,
            "task_output_name": task_output_name,
            "task_run_index": task_run_index,
            "model": model_output_name,
            "requested_model": requested_model_chosen,
            "api_model": mc,
            "ablation": ablation_name,
            "api_route": api_route_name,
            "uni_generation_settings": uni_generation_settings,
            "task_name_hint": ex_name if task_name_hint else None,
            "task_name_hint_scope": "all_llm_calls" if task_name_hint else None,
            "direct_grid_enabled": direct_grid_enabled,
            "requested_use_prior_code": requested_use_prior_code,
            "effective_use_prior_code": use_prior_code,
            "nodes": {},
            "events": [],
            }
    prior_pipeline_flow_file = latest_pipeline_flow_file() if use_prior_code else None
    loaded_prior_pipeline_flow = False
    historical_usage = {
            "api_call_count": 0,
            "total": empty_usage_total(),
            "by_model": {},
            "source_file": None
            }
    if prior_pipeline_flow_file is not None:
        try:
            with open(prior_pipeline_flow_file, "r") as f:
                prior_pipeline_flow = json.load(f)
            if isinstance(prior_pipeline_flow, dict):
                historical_usage = load_historical_usage_from_flow(prior_pipeline_flow, prior_pipeline_flow_file)
                prior_pipeline_flow.setdefault("nodes", {})
                prior_pipeline_flow.setdefault("events", [])
                prior_pipeline_flow["task"] = ex_name
                prior_pipeline_flow["task_output_name"] = task_output_name
                prior_pipeline_flow["task_run_index"] = task_run_index
                prior_pipeline_flow["model"] = model_output_name
                prior_pipeline_flow["requested_model"] = requested_model_chosen
                prior_pipeline_flow["api_model"] = mc
                prior_pipeline_flow["ablation"] = ablation_name
                prior_pipeline_flow["api_route"] = api_route_name
                prior_pipeline_flow["uni_generation_settings"] = uni_generation_settings
                prior_pipeline_flow["task_name_hint"] = ex_name if task_name_hint else None
                prior_pipeline_flow["task_name_hint_scope"] = "all_llm_calls" if task_name_hint else None
                prior_pipeline_flow["requested_use_prior_code"] = requested_use_prior_code
                prior_pipeline_flow["effective_use_prior_code"] = use_prior_code
                prior_pipeline_flow.setdefault("resumed_from", []).append({
                    "flow_file": prior_pipeline_flow_file,
                    "programs_file": programs_dict_read_file,
                    "result_run_index": result_run_index,
                    })
                pipeline_flow = prior_pipeline_flow
                loaded_prior_pipeline_flow = True
                print(f"Loaded prior pipeline flow from {prior_pipeline_flow_file}")
                logging.info(f"Loaded prior pipeline flow from {prior_pipeline_flow_file}")
        except Exception as e:
            print(f"Failed to load prior pipeline flow from {prior_pipeline_flow_file}: {e}")
            logging.info(f"Failed to load prior pipeline flow from {prior_pipeline_flow_file}: {e}")

    def flow_code_id(code_file_name):
        if code_file_name is None:
            return None
        return os.path.basename(code_file_name).replace(".py", "")

    def ensure_flow_node(code_file_name, created_by = None, created_round = None, details = None):
        code_id = flow_code_id(code_file_name)
        if code_id is None:
            return None
        if code_id not in pipeline_flow["nodes"]:
            pipeline_flow["nodes"][code_id] = {
                    "id": code_id,
                    "label": code_id,
                    "path": code_file_name,
                    "created_by": created_by or "unknown",
                    "created_round": created_round,
                    "details": details or {},
                    }
        else:
            node = pipeline_flow["nodes"][code_id]
            if created_by is not None:
                node.setdefault("created_by", created_by)
            if created_round is not None and node.get("created_round") is None:
                node["created_round"] = created_round
            if details:
                node.setdefault("details", {}).update(details)
        return code_id

    def record_flow_event(event_type, source_code_file_name = None, target_code_file_name = None, round_id = None, status = "success", details = None):
        source_id = ensure_flow_node(source_code_file_name) if source_code_file_name else None
        target_id = ensure_flow_node(target_code_file_name) if target_code_file_name else None
        pipeline_flow["events"].append({
                "type": event_type,
                "round": round_id,
                "source": source_id,
                "target": target_id,
                "status": status,
                "details": details or {},
                })

    def record_flow_visualization(code_file_name, circ_sig, temp, cot, path, compat_path):
        code_id = ensure_flow_node(code_file_name)
        if code_id is None:
            return
        node = pipeline_flow["nodes"][code_id]
        node.setdefault("visualizations", [])
        round_value = circ_sig + 1 if temp else None
        visual_record = {
                "round": round_value,
                "temp": temp,
                "cot": cot,
                "path": path,
                "compat_path": compat_path,
                }
        for existing_record in node["visualizations"]:
            if (
                    existing_record.get("round") == visual_record["round"]
                    and existing_record.get("temp") == temp
                    and existing_record.get("cot") == cot
                    and existing_record.get("path") == path
                    ):
                existing_record.update(visual_record)
                break
        else:
            node["visualizations"].append(visual_record)

    def set_pipeline_validity(code_file_name, pipeline_valid, reason = None, round_id = None):
        code_id = ensure_flow_node(code_file_name)
        if code_id is None:
            return
        node = pipeline_flow["nodes"][code_id]
        node["pipeline_valid"] = pipeline_valid
        node["pipeline_valid_reason"] = reason
        node["pipeline_valid_round"] = round_id
        if code_file_name in programs_dict and isinstance(programs_dict[code_file_name], dict):
            programs_dict[code_file_name]["pipeline_valid"] = pipeline_valid
            programs_dict[code_file_name]["pipeline_valid_reason"] = reason
            programs_dict[code_file_name]["pipeline_valid_round"] = round_id

    def write_pipeline_flow_files():
        flow_suffix = "" if result_run_index == 0 else f"_{result_run_index}"
        flow_json_file = os.path.join(results_dir, f"pipeline_flow_{ex_name}{flow_suffix}.json")
        flow_html_file = os.path.join(results_dir, f"pipeline_flow_{ex_name}{flow_suffix}.html")
        pipeline_flow["result_file"] = result_file_name
        pipeline_flow["flow_html_file"] = flow_html_file
        pipeline_flow["flow_html_dir"] = os.path.dirname(flow_html_file)
        with open(flow_json_file, "w") as f:
            json.dump(pipeline_flow, f)
        with open(flow_html_file, "w", encoding = "utf-8") as f:
            f.write(_build_pipeline_flow_html(pipeline_flow))
        return flow_json_file, flow_html_file

    def pipeline_visual_path(code_file_name, circ_sig, temp = True, cot = True):
        abbre_code_file_name = os.path.basename(code_file_name).replace(".py", "")
        if temp:
            return os.path.join(task_visuals_dir, f"{abbre_code_file_name}_results_circ{circ_sig+1}.png")
        if cot:
            return os.path.join(task_visuals_dir, f"{abbre_code_file_name}_cot.png")
        return os.path.join(task_visuals_dir, f"{abbre_code_file_name}.png")

    def pipeline_compat_visual_path(code_file_name, circ_sig, temp = True, cot = True):
        abbre_code_file_name = os.path.basename(code_file_name).replace(".py", "")
        if temp:
            return os.path.join(programs_dir, f"{abbre_code_file_name}_results_circ{circ_sig+1}.png")
        if cot:
            return os.path.join(results_dir, f"{abbre_code_file_name}_cot.png")
        return os.path.join(results_dir, f"{abbre_code_file_name}.png")

    def save_pipeline_visualization(exs_data, exs_ans_data, ques_data, ans_data, circ_sig, code_file_name, temp = True, cot = True):
        primary_png_path = pipeline_visual_path(code_file_name, circ_sig, temp = temp, cot = cot)
        compat_png_path = pipeline_compat_visual_path(code_file_name, circ_sig, temp = temp, cot = cot)
        for png_path in [primary_png_path, compat_png_path]:
            os.makedirs(os.path.dirname(png_path), exist_ok = True)
            save_vis_data_temp(
                    exs_data, exs_ans_data, ques_data, ans_data,
                    circ_sig, code_file_name, temp = temp, cot = cot,
                    path = png_path
                    )
        record_flow_visualization(code_file_name, circ_sig, temp, cot, primary_png_path, compat_png_path)

    def finish_test_one_file(result_dict = None, failed_reason = None):
        if result_dict is None:
            result_dict = {}
        with token_usage_lock:
            token_total = dict(token_usage.get("total", {}))
            token_by_model = {
                model_name: dict(model_usage)
                for model_name, model_usage in token_usage.get("by_model", {}).items()
            }
            api_call_count = len(token_usage.get("calls", []))
        historical_total = sanitize_usage_total(historical_usage.get("total", {}))
        historical_by_model = sanitize_usage_by_model(historical_usage.get("by_model", {}))
        historical_api_call_count = historical_usage.get("api_call_count", 0) or 0
        cumulative_total = add_usage_totals(historical_total, token_total)
        cumulative_by_model = add_usage_by_model(historical_by_model, token_by_model)
        cumulative_api_call_count = historical_api_call_count + api_call_count
        if failed_reason is not None:
            result_dict["failed_reason"] = failed_reason
            result_dict.setdefault("task_correct", False)
            result_dict.setdefault("task_partially_correct", False)
            result_dict.setdefault("pipeline_correctness", {
                "task_correct": False,
                "task_partially_correct": False,
                "best_program": None,
                "best_correct_num": 0,
                "all_num": len(ans),
                "best_correct_rate": 0,
                "best_correct_tests": [],
                "best_per_test_results": build_per_test_results([], ans),
                "evaluated_program_count": 0,
                "evaluated_programs": [],
                "solved_programs": [],
                "partially_correct_programs": [],
            })
            result_dict.setdefault("per_test_results", build_per_test_results([], ans))
            print(f"Pipeline result for {ex_name}: failed ({failed_reason})")
        result_dict["result_run_index"] = result_run_index
        result_dict["task_output_name"] = task_output_name
        result_dict["task_run_index"] = task_run_index
        result_dict["model_chosen"] = model_chosen
        result_dict["requested_model_chosen"] = requested_model_chosen
        result_dict["ablation"] = ablation_name
        result_dict["api_route"] = api_route_name
        result_dict["uni_generation_settings"] = uni_generation_settings
        result_dict["task_name_hint"] = ex_name if task_name_hint else None
        result_dict["task_name_hint_scope"] = "all_llm_calls" if task_name_hint else None
        result_dict["api_model"] = mc
        result_dict["auxiliary_model"] = auxiliary_model_key
        result_dict["auxiliary_api_model"] = auxiliary_mc
        result_dict["introspection_model"] = introspection_model_key
        result_dict["introspection_api_model"] = introspection_mc
        result_dict["pipeline_dir"] = pipeline_dir
        result_dict["output_dirs"] = {
            "results_dir": results_dir,
            "logs_dir": logs_dir,
            "programs_dir": programs_dir,
            "visualizations_dir": task_visuals_dir,
            "round_visualizations_dir": programs_dir,
            "result_visualizations_dir": results_dir,
        }
        result_dict["api_call_count"] = api_call_count
        result_dict["input_tokens"] = token_total.get("input_tokens", 0)
        result_dict["output_tokens"] = token_total.get("output_tokens", 0)
        result_dict["total_tokens"] = token_total.get("total_tokens", 0)
        result_dict["cost"] = token_total.get("cost", 0)
        result_dict["token_usage_by_model"] = token_by_model
        result_dict["token_usage"] = token_usage
        result_dict["historical_usage_source"] = historical_usage.get("source_file")
        result_dict["historical_api_call_count"] = historical_api_call_count
        result_dict["historical_input_tokens"] = historical_total.get("input_tokens", 0)
        result_dict["historical_output_tokens"] = historical_total.get("output_tokens", 0)
        result_dict["historical_total_tokens"] = historical_total.get("total_tokens", 0)
        result_dict["historical_cost"] = historical_total.get("cost", 0)
        result_dict["historical_token_usage_by_model"] = historical_by_model
        result_dict["cumulative_api_call_count"] = cumulative_api_call_count
        result_dict["cumulative_input_tokens"] = cumulative_total.get("input_tokens", 0)
        result_dict["cumulative_output_tokens"] = cumulative_total.get("output_tokens", 0)
        result_dict["cumulative_total_tokens"] = cumulative_total.get("total_tokens", 0)
        result_dict["cumulative_cost"] = cumulative_total.get("cost", 0)
        result_dict["cumulative_token_usage_by_model"] = cumulative_by_model
        result_dict["cumulative_token_usage"] = {
                "api_call_count": cumulative_api_call_count,
                "total": cumulative_total,
                "by_model": cumulative_by_model,
                }
        pipeline_flow["api_call_count"] = api_call_count
        pipeline_flow["token_usage_total"] = token_total
        pipeline_flow["token_usage_by_model"] = token_by_model
        pipeline_flow["historical_usage_source"] = historical_usage.get("source_file")
        pipeline_flow["historical_api_call_count"] = historical_api_call_count
        pipeline_flow["historical_token_usage_total"] = historical_total
        pipeline_flow["historical_token_usage_by_model"] = historical_by_model
        pipeline_flow["cumulative_api_call_count"] = cumulative_api_call_count
        pipeline_flow["cumulative_token_usage_total"] = cumulative_total
        pipeline_flow["cumulative_token_usage_by_model"] = cumulative_by_model
        pipeline_flow["per_test_results"] = result_dict.get("per_test_results", [])
        flow_json_file, flow_html_file = write_pipeline_flow_files()
        result_dict["pipeline_flow"] = pipeline_flow
        result_dict["pipeline_flow_json_file"] = flow_json_file
        result_dict["pipeline_flow_html_file"] = flow_html_file
        with open(result_file_name, "w") as f:
            json.dump(result_dict, f)
        print(f"Results already saved to {result_file_name}!")
        print(f"Pipeline flow saved to {flow_html_file}!")
        logging.info(f"Results already saved to {result_file_name}!")
        logging.info(f"Pipeline flow saved to {flow_html_file}!")
        openai.OpenAI = original_openai_client
        return result_dict

    def communicate_code_process(process, input_json, code_file_name):
        try:
            stdout, stderr = process.communicate(input=input_json, timeout=code_timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            timeout_message = f"Code execution timed out after {code_timeout_seconds} seconds: {code_file_name}"
            if stderr:
                timeout_message = timeout_message + "\n" + stderr
            return None, timeout_message
        return stdout, stderr

    def run_code_on_grid(code_file_name, input_grid):
        input_json = json.dumps(input_grid)
        process = subprocess.Popen(
                ['python3', code_file_name],
                stdin = subprocess.PIPE,
                stdout = subprocess.PIPE,
                stderr = subprocess.PIPE,
                text = True
            )
        stdout, stderr = communicate_code_process(process, input_json, code_file_name)
        if stdout is None:
            return None, stderr
        if process.returncode != 0:
            return None, stderr
        try:
            output_json = json.loads(stdout)
            if output_json == None:
                return None, "The output grid is None, which is not valid!"
        except Exception:
            return None, "The output of the function execute() can not be parsed correctly."
        if isinstance(output_json, list) and len(output_json) == 1:
            output_json = output_json[0]
        return output_json, ""

    def run_code_on_inputs(code_file_name, input_grids, max_workers = 8):
        if len(input_grids) == 0:
            return [], False, ""
        output_grid_list = [None] * len(input_grids)
        error_signal = False
        error_message = ""
        worker_count = min(max_workers, len(input_grids))
        with ThreadPoolExecutor(max_workers = worker_count) as executor:
            future_to_idx = {
                    executor.submit(run_code_on_grid, code_file_name, input_grid): idx
                    for idx, input_grid in enumerate(input_grids)
                    }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    output_json, one_error_message = future.result()
                except Exception as e:
                    output_json = None
                    one_error_message = str(e)
                if one_error_message:
                    error_signal = True
                    if not error_message:
                        error_message = one_error_message
                output_grid_list[idx] = output_json
        if error_signal:
            output_grid_list = [grid for grid in output_grid_list if grid is not None]
        return output_grid_list, error_signal, error_message

    def outputs_complete(output_grid_list, expected_count):
        return (
                isinstance(output_grid_list, list)
                and len(output_grid_list) == expected_count
                and all(output_grid is not None for output_grid in output_grid_list)
                )

    def save_code_visualization_snapshot(code_file_name, circ_sig, phase, question_outputs = None, question_error_signal = None, question_error_message = None, update_program_error = True):
        code_result_dict = programs_dict.get(code_file_name)
        if not isinstance(code_result_dict, dict):
            return None, True, "Program metadata is not available."
        example_outputs = example_result_dict.get(code_file_name)
        if not outputs_complete(example_outputs, len(exs)):
            message = f"Skip visualization for {code_file_name} at {phase}: example outputs are incomplete."
            print(message)
            logging.info(message)
            return question_outputs, True, message
        if question_outputs is None:
            question_outputs, question_error_signal, question_error_message = run_code_on_inputs(code_file_name, ques)
        question_error_signal = bool(question_error_signal)
        question_error_message = question_error_message or ""
        if update_program_error:
            code_result_dict['error_signal'] = question_error_signal
            code_result_dict['error_message'] = question_error_message
        output_grid_temp_dict[code_file_name] = question_outputs
        if question_error_signal or not outputs_complete(question_outputs, len(ques)):
            message = question_error_message or f"Question outputs are incomplete for {code_file_name} at {phase}."
            print(f"Skip visualization for {code_file_name} at {phase}: {message}")
            logging.info(f"Skip visualization for {code_file_name} at {phase}: {message}")
            return question_outputs, True, message
        try:
            save_pipeline_visualization(
                    exs, example_outputs, ques, question_outputs,
                    circ_sig, code_file_name, temp = True
                    )
            print(f"Visualization saved for {code_file_name} at {phase}.")
            logging.info(f"Visualization saved for {code_file_name} at {phase}.")
        except Exception as e:
            message = str(e)
            print(f"Visualization for {code_file_name} failed at {phase}. Error: {message}")
            logging.info(f"Visualization for {code_file_name} failed at {phase}. Error: {message}")
            return question_outputs, True, message
        return question_outputs, False, ""

    def save_all_current_code_visualizations(circ_sig, phase, update_program_error = True):
        for code_file_name, code_result_dict in list(programs_dict.items()):
            if code_file_name == 'circulate times' or not isinstance(code_result_dict, dict):
                continue
            save_code_visualization_snapshot(code_file_name, circ_sig, phase, update_program_error = update_program_error)

    programs_dict_file = os.path.join(programs_dir, f'programs_{ex_name}.json')
    if programs_dict_read_file is None:
        programs_dict_read_file = programs_dict_file
    output_grid_temp_dict = {}

    # code wrapper for execution
    modified_code_head = """import json
import sys
import traceback as trace

"""
    modified_code_main = """
if __name__ == "__main__":
    try:
        input_data = json.load(sys.stdin)
        result = execute(input_data)
        json.dump(result, sys.stdout)
    except Exception as e:
        error_info = {
            "error": str(e),
            "traceback": trace.format_exc()
        }
        json.dump(error_info, sys.stderr)
        sys.exit(1)
"""
    # preparing code prompt
    code_prompt_dict = {}
    for sig in range(len(exs)):
        code_prompt_dict[f"example{sig}"] = {}
        code_prompt_dict[f"example{sig}"]["input"] = exs[sig][0]
        code_prompt_dict[f"example{sig}"]["output"] = exs[sig][1]

    question_prompt_dict = {}
    for sig in range(len(ques)):
        question_prompt_dict[f"question{sig}"] = ques[sig]

    def call_direct_grid_model(prompt_content, mc, system_text):
        client = openai.OpenAI()
        messages = [
                {"role": "system", "content": system_text},
                {"role": "user", "content": prompt_content},
                ]
        temp_sig = 0
        while True:
            try:
                response = client.chat.completions.create(model = mc, messages = messages)
                provider_error_message = extract_provider_error_message(response)
                if provider_error_message:
                    logging.info(f"Direct grid model provider error: {provider_error_message}. Response: {response}")
                    temp_sig += 1
                else:
                    return response.choices[0].message.content
            except Exception as e:
                print(e)
                logging.info(f"Direct grid model call failed with exception: {e}")
                temp_sig += 1
            if temp_sig > 2:
                return None

    def run_direct_grid_challenger(code_file_dict, code_question_outputs, round_id):
        details = {
                "enabled": direct_grid_enabled,
                "blocks_break": False,
                "skip_reason": "",
                }
        if not direct_grid_enabled:
            details["skip_reason"] = "disabled"
            return details
        direct_prompt_content = [
                {"type": "text", "text": direct_grid_prediction_prompt},
                {"type": "text", "text": format_analogy_context(code_file_dict, "The analogy context and selected expansion for direct grid prediction")},
                {"type": "text", "text": "The visualization of examples is shown below:"},
                {"type": "image_url", "image_url": {"url": exs_url}},
                {"type": "text", "text": "The matrix of examples is shown below:"},
                {"type": "text", "text": str(code_prompt_dict)},
                {"type": "text", "text": "The visualization of question inputs is shown below:"},
                {"type": "image_url", "image_url": {"url": ques_url}},
                {"type": "text", "text": "The matrix of question inputs is shown below:"},
                {"type": "text", "text": str(question_prompt_dict)},
                ]
        set_token_context("direct_grid_prediction", round_id)
        raw_response = call_direct_grid_model(
                direct_prompt_content,
                auxiliary_mc,
                "You are a careful ARC solver. Return only the requested JSON object.",
                )
        details["raw_response"] = raw_response
        if raw_response is None:
            details["skip_reason"] = "prediction_empty_response"
            details["parse_success"] = False
            return details
        prediction = parse_direct_grid_prediction_response(raw_response, exs, ques)
        details.update(prediction)
        comparison = compare_direct_and_code_outputs(prediction, code_question_outputs or [])
        details.update(comparison)
        if not prediction.get("parse_success"):
            details["skip_reason"] = "prediction_parse_failed"
            return details
        if not prediction.get("question_pred_all_valid"):
            details["skip_reason"] = "question_prediction_invalid"
            return details
        if comparison.get("code_question_match"):
            details["skip_reason"] = "direct_matches_code"
            return details
        if not comparison.get("comparison_available"):
            details["skip_reason"] = "comparison_unavailable"
            return details

        direct_question_outputs = [
                item.get("output") if isinstance(item, dict) else None
                for item in prediction.get("question_predictions", [])
                ]
        direct_prediction_reasoning = {
                "rule_summary": prediction.get("rule_summary", ""),
                "mechanism_spec": prediction.get("mechanism_spec", {}),
                "example_traces": prediction.get("example_traces", []),
                "rejected_shortcuts": prediction.get("rejected_shortcuts", []),
                "key_observations": prediction.get("key_observations", []),
                "invariants": prediction.get("invariants", []),
                "transformation_steps": prediction.get("transformation_steps", []),
                "test_trace": prediction.get("test_trace", {}),
                "uncertainty": prediction.get("uncertainty", ""),
                "example_reasons": [
                    {
                        "index": item.get("index"),
                        "confidence": item.get("confidence", ""),
                        "reason": item.get("reason", ""),
                        "check": item.get("check", ""),
                    }
                    for item in prediction.get("example_predictions", [])
                    if isinstance(item, dict)
                    ],
                "question_reasons": [
                    {
                        "index": item.get("index"),
                        "confidence": item.get("confidence", ""),
                        "reason": item.get("reason", ""),
                        "check": item.get("check", ""),
                    }
                    for item in prediction.get("question_predictions", [])
                    if isinstance(item, dict)
                    ],
                }
        arbitration_content = [
                {"type": "text", "text": direct_grid_arbitration_prompt},
                {"type": "text", "text": format_analogy_context(code_file_dict, "The analogy context and selected expansion")},
                {"type": "text", "text": "The visualization of examples is shown below:"},
                {"type": "image_url", "image_url": {"url": exs_url}},
                {"type": "text", "text": "The matrix of examples is shown below:"},
                {"type": "text", "text": str(code_prompt_dict)},
                {"type": "text", "text": "The matrix of question inputs is shown below:"},
                {"type": "text", "text": str(question_prompt_dict)},
                {"type": "text", "text": "Candidate A/code question outputs are shown below:"},
                {"type": "text", "text": json.dumps(code_question_outputs, ensure_ascii=False)},
                {"type": "text", "text": "Candidate B/direct question predictions are shown below:"},
                {"type": "text", "text": json.dumps(direct_question_outputs, ensure_ascii=False)},
                {"type": "text", "text": "Candidate B/direct structured reasoning is shown below:"},
                {"type": "text", "text": json.dumps(direct_prediction_reasoning, ensure_ascii=False)},
                ]
        for ques_sig_num, question_grid in enumerate(ques):
            if ques_sig_num < len(direct_question_outputs) and ques_sig_num < len(code_question_outputs):
                direct_output = direct_question_outputs[ques_sig_num]
                if direct_output is not None:
                    code_url, _ = vis_result_grid_for_LLM(question_grid, code_question_outputs[ques_sig_num])
                    direct_url, _ = vis_result_grid_for_LLM(question_grid, direct_output)
                    arbitration_content.extend([
                            {"type": "text", "text": f"Question {ques_sig_num} Candidate A/code visualization:"},
                            {"type": "image_url", "image_url": {"url": code_url}},
                            {"type": "text", "text": f"Question {ques_sig_num} Candidate B/direct visualization:"},
                            {"type": "image_url", "image_url": {"url": direct_url}},
                            ])
        set_token_context("direct_grid_arbitration", round_id)
        arbitration_raw = call_direct_grid_model(
                arbitration_content,
                auxiliary_mc,
                "You are a careful ARC verifier. Return only the requested JSON object.",
                )
        details["arbitration_raw_response"] = arbitration_raw
        arbitration = parse_direct_grid_arbitration_response(arbitration_raw)
        details["arbitration"] = arbitration
        if arbitration.get("parse_success") and arbitration.get("preferred") in ["direct", "uncertain"]:
            details["blocks_break"] = True
            details["skip_reason"] = "arbitration_blocks_break"
        elif arbitration.get("parse_success"):
            details["skip_reason"] = "arbitration_prefers_code"
        else:
            details["skip_reason"] = "arbitration_parse_failed"
        return details

    def examples_all_correct(example_outputs):
        return (
                outputs_complete(example_outputs, len(exs))
                and all(
                    example_outputs[example_index] == exs[example_index][1]
                    for example_index in range(len(exs))
                    )
                )

    def build_introspection_prompt_contents(code_file_dict, question_outputs):
        breaking_prompt_content = [
                {
                    "type": "text",
                    "text": breaking_code_prompt,
                },
                {
                    "type": "text",
                    "text": format_analogy_context(code_file_dict, "The analogy context of the question"),
                },
                {
                    "type": "text",
                    "text": "The code reasoning is shown below:" + str(code_file_dict.get('code reasoning', '')),
                },
                {
                    "type": "text",
                    "text": "The code explanation is shown below:" + str(code_file_dict.get('explanation', '')),
                },
                {
                    "type": "text",
                    "text": "The full code is shown below:" + str(code_file_dict.get('code', '')),
                },
                {
                    "type": "text",
                    "text": "The visualization of examples is shown below:",
                },
                {
                    "type": "image_url",
                    "image_url": {"url": exs_url},
                },
                {
                    "type": "text",
                    "text": "The matrix of examples is shown below:",
                },
                {
                    "type": "text",
                    "text": str(code_prompt_dict),
                },
                ]
        final_rectify_prompt_content = [
                {
                    "type": "text",
                    "text": final_rectify_code_prompt,
                },
                {
                    "type": "text",
                    "text": format_analogy_context(code_file_dict, "The analogy context of the question"),
                },
                {
                    "type": "text",
                    "text": "The visualization of examples is shown below:",
                },
                {
                    "type": "image_url",
                    "image_url": {"url": exs_url},
                },
                {
                    "type": "text",
                    "text": "The matrix of examples is shown below:",
                },
                {
                    "type": "text",
                    "text": str(code_prompt_dict),
                },
                {
                    "type": "text",
                    "text": "The code is shown below:",
                },
                {
                    "type": "text",
                    "text": str(code_file_dict.get('code', '')),
                },
                ]
        for question_index, question_grid in enumerate(ques):
            result_ques_url, _ = vis_result_grid_for_LLM(
                    question_grid,
                    question_outputs[question_index],
                    )
            question_content = [
                    {
                        "type": "text",
                        "text": (
                            f"The visualization of question {question_index + 1} input "
                            "and the corresponding output from the code is shown below:"
                            ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": result_ques_url},
                    },
                    {
                        "type": "text",
                        "text": "The matrix of the question input is: " + str(question_grid),
                    },
                    {
                        "type": "text",
                        "text": (
                            "The matrix of the code output is: "
                            + str(question_outputs[question_index])
                            ),
                    },
                    ]
            breaking_prompt_content.extend(question_content)
            final_rectify_prompt_content.extend(copy.deepcopy(question_content))
        compositional_prompt_content = copy.deepcopy(breaking_prompt_content)
        compositional_prompt_content[0]["text"] = compositional_introspection_prompt
        return (
                breaking_prompt_content,
                compositional_prompt_content,
                final_rectify_prompt_content,
                )

    def run_model_introspection(code_file_name, code_file_dict, question_outputs, round_id, phase):
        def audit_list(audit, field):
            value = audit.get(field, [])
            return value if isinstance(value, list) else []

        if not outputs_complete(question_outputs, len(ques)):
            return {
                    "is_valid": False,
                    "instruction": "Question outputs are incomplete and must be made executable before validation.",
                    "details": {
                        "phase": phase,
                        "judge_mode": "single_model_two_layer_mc",
                        "judge_model": introspection_model_key,
                        "judge_api_model": introspection_mc,
                        "judge_call_count": 0,
                        "judgement": False,
                        "error": "incomplete_question_outputs",
                        "semantic_introspection": {
                            "executed": False,
                            "skip_reason": "incomplete_question_outputs",
                            },
                        "compositional_introspection": {
                            "executed": False,
                            "skip_reason": "incomplete_question_outputs",
                            },
                    },
                    "rectify_prompt_content": None,
                    }

        (
                semantic_prompt_content,
                compositional_prompt_content,
                final_rectify_prompt_content,
                ) = build_introspection_prompt_contents(code_file_dict, question_outputs)

        print(f"Start semantic {introspection_model_key} introspection on {code_file_name} ({phase}).")
        logging.info(f"Semantic introspection judging {code_file_name} during {phase}.")
        set_token_context(f"introspection_{phase}_semantic", round_id)
        semantic_judgement, semantic_instruction, semantic_audit = get_breaking_instruction(
                semantic_prompt_content,
                introspection_mc,
                )
        semantic_judgement = bool(semantic_judgement)
        semantic_audit = semantic_audit or {}
        semantic_details = {
                "executed": True,
                "judgement": semantic_judgement,
                "instruction": semantic_instruction,
                "audit": semantic_audit,
                }

        compositional_judgement = False
        compositional_instruction = None
        compositional_audit = {}
        compositional_details = {
                "executed": False,
                "judgement": None,
                "instruction": None,
                "audit": {},
                "skip_reason": "semantic_introspection_rejected",
                }
        if semantic_judgement:
            compositional_prompt_content.append({
                    "type": "text",
                    "text": (
                        "The first-layer semantic introspection tentatively accepted the "
                        "candidate. Use its independently inferred contract as context, but "
                        "verify the actual component-level execution rather than repeating "
                        "its conclusion:\n"
                        + json.dumps({
                            "judgement": semantic_judgement,
                            "instruction": semantic_instruction,
                            "audit": semantic_audit,
                            }, ensure_ascii = False)
                        ),
                    })
            print(f"Start compositional {introspection_model_key} introspection on {code_file_name} ({phase}).")
            logging.info(f"Compositional introspection judging {code_file_name} during {phase}.")
            set_token_context(f"introspection_{phase}_compositional", round_id)
            (
                    compositional_judgement,
                    compositional_instruction,
                    compositional_audit,
                    ) = get_breaking_instruction(
                            compositional_prompt_content,
                            introspection_mc,
                            )
            compositional_judgement = bool(compositional_judgement)
            compositional_audit = compositional_audit or {}
            if compositional_judgement and (
                    not audit_list(compositional_audit, "component_traces")
                    or not audit_list(compositional_audit, "counterfactual_checks")
                    ):
                compositional_judgement = False
                compositional_instruction = (
                        "Repeat the execution-level audit with concrete component traces "
                        "and counterfactual isolation before accepting the implementation."
                        )
                compositional_audit["format_consistent"] = False
                compositional_audit["error"] = "missing_execution_evidence"
            compositional_details = {
                    "executed": True,
                    "judgement": compositional_judgement,
                    "instruction": compositional_instruction,
                    "audit": compositional_audit,
                    "skip_reason": "",
                    }

        raw_judgement = bool(semantic_judgement and compositional_judgement)
        direct_grid_details = {
                "enabled": direct_grid_enabled,
                "blocks_break": False,
                "skip_reason": (
                    "semantic_introspection_rejected"
                    if not semantic_judgement
                    else "compositional_introspection_rejected"
                    if not compositional_judgement
                    else "not_run"
                    ),
                }
        if raw_judgement:
            direct_grid_details = run_direct_grid_challenger(
                    code_file_dict,
                    question_outputs,
                    round_id,
                    )
            code_file_dict["direct_grid_prediction"] = direct_grid_details
            record_flow_event(
                    "direct_grid_prediction",
                    target_code_file_name = code_file_name,
                    round_id = round_id,
                    status = "blocked_break" if direct_grid_details.get("blocks_break") else "success",
                    details = {
                        "phase": phase,
                        **direct_grid_details,
                        },
                    )

        semantic_reasoning = semantic_audit.get("reasoning", "")
        compositional_reasoning = compositional_audit.get("reasoning", "")
        combined_reasoning_parts = []
        if semantic_reasoning:
            combined_reasoning_parts.append("SEMANTIC INTROSPECTION:\n" + semantic_reasoning)
        if compositional_reasoning:
            combined_reasoning_parts.append(
                    "COMPOSITIONAL EXECUTION INTROSPECTION:\n" + compositional_reasoning
                    )
        combined_audit = {
                "parse_success": bool(
                    semantic_audit.get("parse_success")
                    and (
                        not semantic_judgement
                        or compositional_audit.get("parse_success")
                        )
                    ),
                "reasoning": "\n\n".join(combined_reasoning_parts),
                "blocking_issues": (
                    audit_list(semantic_audit, "blocking_issues")
                    + audit_list(compositional_audit, "blocking_issues")
                    ),
                "contract_audit": audit_list(semantic_audit, "contract_audit"),
                "question_stress_test": audit_list(semantic_audit, "question_stress_test"),
                "component_traces": audit_list(compositional_audit, "component_traces"),
                "overlapping_operations": audit_list(
                    compositional_audit,
                    "overlapping_operations",
                    ),
                "counterfactual_checks": audit_list(
                    compositional_audit,
                    "counterfactual_checks",
                    ),
                "format_consistent": bool(
                    semantic_audit.get("format_consistent")
                    and (
                        not semantic_judgement
                        or compositional_audit.get("format_consistent")
                        )
                    ),
                }
        is_valid = bool(raw_judgement and not direct_grid_details.get("blocks_break"))
        if is_valid:
            break_instruction = ""
        elif direct_grid_details.get("blocks_break"):
            arbitration = direct_grid_details.get("arbitration", {}) or {}
            break_instruction = (
                    arbitration.get("instructions")
                    or "Direct grid challenger found a plausible mismatch between code output and independent grid prediction."
                    )
        elif not semantic_judgement:
            break_instruction = (
                    semantic_instruction
                    or "The semantic introspection audit rejected the implementation."
                    )
        else:
            break_instruction = (
                compositional_instruction
                    or "The compositional introspection audit rejected the implementation."
                    )

        details = {
                "phase": phase,
                "judge_mode": "single_model_two_layer_mc",
                "judge_model": introspection_model_key,
                "judge_api_model": introspection_mc,
                "judge_call_count": 2 if semantic_judgement else 1,
                "judgement": raw_judgement,
                "instruction": break_instruction,
                "audit": combined_audit,
                "semantic_introspection": semantic_details,
                "compositional_introspection": compositional_details,
                "direct_grid": direct_grid_details,
                "break_instruction": break_instruction,
                # Compatibility fields for existing result readers.
                "auxiliary_model": introspection_model_key,
                "auxiliary_api_model": introspection_mc,
                "auxiliary_judgement": raw_judgement,
                "auxiliary_instruction": break_instruction,
                }
        if not is_valid:
            final_rectify_prompt_content.append({
                    "type": "text",
                    "text": (
                        "The introspection audit rejected the current mechanism. "
                        "Repair every evidence-backed blocking issue below, while preserving "
                        "all example outputs.\n"
                        + json.dumps({
                            "semantic_introspection": semantic_details,
                            "compositional_introspection": compositional_details,
                            "combined_audit": combined_audit,
                            "instructions": break_instruction,
                            }, ensure_ascii = False)
                        ),
                    })
        return {
                "is_valid": is_valid,
                "instruction": break_instruction,
                "details": details,
                "rectify_prompt_content": final_rectify_prompt_content,
                }

    # Calculate mask and choose metric strategy
    try:
        judge_mask_exs = get_similarity_mask_batch(exs)
        judge_by_mask = True
    except Exception as e:
        judge_mask_exs = None
        judge_by_mask = False

    if use_prior_code:
        print("Start code execution!")
        logging.info("Reload programs.")

        ## directly execute the code

        # load programs file
        program_write_dict = {}
        with open(programs_dict_read_file, "r") as f:
            program_write_dict = json.load(f)
        programs_dict = program_write_dict[ex_name]
        for loaded_code_file_name, loaded_code_file_dict in programs_dict.items():
            if loaded_code_file_name == 'circulate times' or loaded_code_file_dict is None:
                continue
            ensure_flow_node(
                    loaded_code_file_name,
                    created_by = "loaded_prior_code",
                    created_round = loaded_code_file_dict.get("created_round", 0),
                    details = {
                        "programs_file": programs_dict_read_file,
                        "analogy": loaded_code_file_dict.get("analogy"),
                        "reason": loaded_code_file_dict.get("reason"),
                        "rule": loaded_code_file_dict.get("rule"),
                        "objects": loaded_code_file_dict.get("objects"),
                        }
                    )
            if not loaded_prior_pipeline_flow:
                record_flow_event(
                        "loaded_prior_code",
                        target_code_file_name = loaded_code_file_name,
                        round_id = loaded_code_file_dict.get("created_round", 0),
                        details = {
                            "programs_file": programs_dict_read_file,
                            "analogy": loaded_code_file_dict.get("analogy"),
                            "reason": loaded_code_file_dict.get("reason"),
                            "rule": loaded_code_file_dict.get("rule"),
                            "objects": loaded_code_file_dict.get("objects"),
                            }
                        )


        # load parameters
        if 'circulate times' in programs_dict:
            circ_times = programs_dict['circulate times']


        example_result_dict = {}
        for code_file_name, code_file_dict in programs_dict.items():
            if code_file_name == 'circulate times':
                continue
            if code_file_dict == None:
                continue
            # load other parameters
            if 'mutation rate' not in code_file_dict:
                code_file_dict['mutation rate'] = 0
                mutation_rate_dict[code_file_name] = 0
            else:
                mutation_rate_dict[code_file_name] = code_file_dict['mutation rate']
            if 'former correct rate' not in code_file_dict:
                code_file_dict['former correct rate'] = 0
                former_correct_rate_dict[code_file_name] = 0
            else:
                former_correct_rate_dict[code_file_name] = code_file_dict['former correct rate']
            if 'small mutation rate' in code_file_dict:
                small_mutation_rate_dict[code_file_name] = code_file_dict['small mutation rate']
            elif 'mutation rate' in code_file_dict:
                small_mutation_rate_dict[code_file_name] = code_file_dict['mutation rate']
            else:
                small_mutation_rate_dict[code_file_name] = 0
            output_grid_list = []
            # compute all of the examples
            for exs_input_sig in range(len(exs)):
                input_json = json.dumps(exs[exs_input_sig][0])

                process = subprocess.Popen(
                        ['python3', code_file_name],
                        stdin = subprocess.PIPE,
                        stdout = subprocess.PIPE,
                        stderr = subprocess.PIPE,
                        text = True
                    )
                try:
                    stdout, stderr = communicate_code_process(process, input_json, code_file_name)
                except:
                    error_signal = True
                    error_message = stderr
                    break
                if process.returncode != 0:
                    error_signal = True
                    error_message = stderr
                    break
                else:
                    error_signal = False
                    error_message = ""

                try:
                    output_json = json.loads(stdout)
                    if output_json == None:
                        error_signal = True
                        error_message = "The output grid is None, which is not valid!"
                        break
                except:
                    error_signal = True
                    error_message = "The output of the function execute() can not be parsed correctly."
                    break
                if len(output_json) == 1:
                    output_json = output_json[0]
                output_grid_list.append(output_json)

            example_result_dict[code_file_name] = output_grid_list
            code_file_dict['error_signal'] = error_signal
            code_file_dict['error_message'] = error_message

        print("Finish code execution!")
        logging.info("Reload finished.")

    else:
        # Whole pipeline
        logging.info(f"Initialize {ex_name}.")
        if ablation_name == "direct_targets":
            print("Start direct analogy targets ablation!")
            logging.info("Direct analogy targets ablation start.")
            set_token_context("ablation_direct_targets")
            com_dict, com_generate = generate_direct_analogy_targets(
                    exs_url,
                    exs,
                    auxiliary_mc,
                    test_recog_one_file,
                    parse_answer,
                    )
            if com_dict is None:
                print("Direct analogy targets ablation failed!")
                logging.info("Direct analogy targets ablation failed.")
                if com_generate is not None:
                    logging.info(com_generate)
                finish_test_one_file(failed_reason = "ablation_direct_targets_failed")
                return None
            logging.info("Direct analogy targets ablation successed!")
            logging.info(com_generate)
            targets = com_dict['Analogy_list']
            pipeline_flow["ablation_details"] = {
                    "target_module": "direct_targets",
                    "raw_response": com_generate,
                    "targets": targets,
                    }
            print("Finish direct analogy targets ablation!")
            logging.info("Direct analogy targets ablation finished.")
        else:
            # Analogy part
            print("Start analogy part!")
            logging.info("Analogy start.")
            analogy_jobs = get_analogy_jobs()
            analogy_results = {}
            analogy_structured_results = {}

            def run_analogy_job(job_name, stage, recog_prompt):
                set_token_context(stage)
                return job_name, test_recog_one_file(recog_prompt, exs_url, auxiliary_mc, exs)

            analogy_workers = llm_worker_count(len(analogy_jobs), len(analogy_jobs))
            with ThreadPoolExecutor(max_workers = analogy_workers) as executor:
                future_to_job = {
                        executor.submit(run_analogy_job, job_name, stage, recog_prompt): job_name
                        for job_name, stage, recog_prompt in analogy_jobs
                        }
                for future in as_completed(future_to_job):
                    job_name = future_to_job[future]
                    try:
                        _, job_result = future.result()
                    except Exception as e:
                        job_result = None
                        print(f"{job_name.capitalize()} recog failed with exception: {e}")
                        logging.info(f"{job_name.capitalize()} recog failed with exception: {e}")
                    analogy_results[job_name] = job_result
                    structured_job_result = parse_single_analogy_target_response(job_result)
                    if structured_job_result is not None:
                        analogy_structured_results[job_name] = structured_job_result
                    if job_result == None:
                        print(f"{job_name.capitalize()} recog failed!")
                        logging.info(f"{job_name.capitalize()} recog failed!")
                    else:
                        logging.info(f"{job_name.capitalize()} recog successed!")
                        logging.info(job_result)
            print("Finish analogy part!")
            logging.info("Analogy finished.")
            
            # Concept expansion part
            print("Start concept expansion part!")
            logging.info("Concept expansion start.")
            concept_expansion = None
            concept_expansion_raw_response = None
            concept_expansion_status = "skipped_no_structured_analogy"
            if analogy_structured_results:
                concept_expansion_prompt = build_concept_expansion_prompt(analogy_structured_results)
                set_token_context("slippage_concept_expansion")
                concept_expansion_raw_response = test_recog_one_file(
                        concept_expansion_prompt,
                        exs_url,
                        auxiliary_mc,
                        exs,
                        )
                if concept_expansion_raw_response == None:
                    concept_expansion_status = "failed_empty_response"
                    print("Concept expansion failed!")
                    logging.info("Concept expansion failed.")
                else:
                    concept_expansion = parse_concept_expansion_response(concept_expansion_raw_response)
                    if concept_expansion is None:
                        concept_expansion_status = "failed_parse_response"
                        print("Concept expansion parsing failed; continue without expansion.")
                        logging.info("Concept expansion parsing failed; continue without expansion.")
                        logging.info(concept_expansion_raw_response)
                    else:
                        concept_expansion_status = "success"
                        logging.info("Concept expansion successed!")
                        logging.info(concept_expansion_raw_response)
            else:
                print("Concept expansion skipped: no structured analogy result.")
                logging.info("Concept expansion skipped: no structured analogy result.")
            print("Finish concept expansion part!")
            logging.info("Concept expansion finished.")

            # Slippage part
            print("Start slippage part!")
            logging.info("Slippage start.")
            recog_com_prompt = build_analogy_composite_prompt(analogy_results, concept_expansion)
            non_empty_analogy_count = count_non_empty_analogy_results(analogy_results)
            if recog_com_prompt is None:
                print("Composite recog failed: all analogy aspect results are empty.")
                logging.info("Composite recog failed: all analogy aspect results are empty.")
                finish_test_one_file(failed_reason = "all_analogy_aspects_empty")
                return None
            set_token_context("slippage_composite")
            com_generate = test_recog_one_file(recog_com_prompt, exs_url, auxiliary_mc, exs)
            if com_generate == None:
                print(f"Composite recog failed!")
                logging.info("Composite recog failed!")
                finish_test_one_file(failed_reason = "composite_recognition_failed")
                return None
            else:
                logging.info("Composite recog successed!")
                logging.info(com_generate)
            com_dict = parse_answer(com_generate, is_format="recog")
            if not isinstance(com_dict, dict) or "Analogy_list" not in com_dict:
                print(f"Composite recog parsing failed!")
                logging.info("Composite recog parsing failed.")
                finish_test_one_file(failed_reason = "composite_recognition_parse_failed")
                return None
            com_dict = normalize_analogy_targets(com_dict, required_count=3)
            if com_dict is None:
                print(f"Composite recog target normalization failed!")
                logging.info("Composite recog target normalization failed.")
                finish_test_one_file(failed_reason = "composite_recognition_target_normalization_failed")
                return None
            targets = com_dict['Analogy_list']
            pipeline_flow["ablation_details"] = {
                    "target_module": "analogy_slippage",
                    "analogy_aspects": list(ANALOGY_ASPECTS.keys()),
                    "non_empty_analogy_aspect_count": non_empty_analogy_count,
                    "analogy_results": analogy_results,
                    "analogy_structured_results": analogy_structured_results,
                    "concept_expansion_status": concept_expansion_status,
                    "concept_expansion": concept_expansion,
                    "concept_expansion_raw_response": concept_expansion_raw_response,
                    "raw_response": com_generate,
                    "targets": targets,
                    }
            print("Finish Slippage Part!")
            logging.info("Slippage finished.")

        if task_name_hint:
            pipeline_flow.setdefault("ablation_details", {}).update({
                    "task_name_hint": ex_name,
                    "task_name_hint_scope": "all_llm_calls",
                    "task_name_hint_prompt": task_name_hint,
                    })

        # Programming part
        print("Start programming part!")
        logging.info("Programming start.")
        programs_dict = {}
        example_result_dict = {}
        initial_code_jobs = []
        for sig in range(3):
            target_dict = targets[sig]
            answer_dict = {}
            target = None
            reason = None
            normalized_target_dict = normalize_analogy_target(target_dict)
            if isinstance(normalized_target_dict, dict):
                target = normalized_target_dict.get('Analogy')
                reason = normalized_target_dict.get('Reason')
            if not isinstance(target, str) or not target.strip():
                print(f"Target is a dict but is lack of the key 'Analogy'.")
                finish_test_one_file(failed_reason = "target_missing_analogy")
                return None
            answer_dict['Analogy'] = target.strip()
            if not isinstance(reason, str) or not reason.strip():
                print(f"Target is a dict but is lack of the key 'Reason'.")
                reason = "No explicit reason was provided."
            answer_dict['Reason'] = reason.strip()
            answer_dict['Rule'] = normalized_target_dict.get('Rule', '')
            answer_dict['Objects'] = normalized_target_dict.get('Objects', [])
            answer_dict['Used_expansion_concepts'] = normalized_target_dict.get('Used_expansion_concepts', [])
            answer_dict['Used_quantitative_mechanisms'] = normalized_target_dict.get('Used_quantitative_mechanisms', [])
            answer_dict['Implementation_notes'] = normalized_target_dict.get('Implementation_notes', [])
            answer_dict['Speculative_warnings'] = normalized_target_dict.get('Speculative_warnings', [])
            initial_code_jobs.append((sig, answer_dict))

        def run_initial_code_job(sig, answer_dict):
            print(f"-------------Start programming code{sig}--------------")
            logging.info(f"Programming code{sig}.")
            print("Coding.............")
            logging.info(f"Coding code{sig}")
            set_token_context(f"initial_programming_code{sig}")
            return sig, coding_target(answer_dict, is_reflect = 0, mc = mc, exs=code_prompt_dict, exs_url = exs_url)

        initial_code_results = {}
        initial_code_workers = llm_worker_count(len(initial_code_jobs), len(initial_code_jobs))
        with ThreadPoolExecutor(max_workers = initial_code_workers) as executor:
            future_to_sig = {
                    executor.submit(run_initial_code_job, sig, answer_dict): sig
                    for sig, answer_dict in initial_code_jobs
                    }
            for future in as_completed(future_to_sig):
                sig = future_to_sig[future]
                try:
                    _, code_dict = future.result()
                except Exception as e:
                    print(f"Coding code{sig} failed with exception: {e}")
                    logging.info(f"Coding code{sig} failed with exception: {e}")
                    code_dict = None
                initial_code_results[sig] = code_dict

        successful_initial_code_count = 0
        for sig in range(3):
            code_dict = initial_code_results.get(sig)
            if code_dict == None:
                print(f"Coding code{sig} failed; skip this initial target.")
                logging.info(f"Coding code{sig} failed; skip this initial target.")
                continue
            if not isinstance(code_dict.get('code'), str) or not code_dict.get('code').strip():
                print(f"Coding code{sig} returned empty code; skip this initial target.")
                logging.info(f"Coding code{sig} returned empty code; skip this initial target.")
                continue

            successful_initial_code_count += 1
            # save file
            code_file_name = programs_dir + "/code"+ str(sig) + "_" + ex_name + ".py"
            modified_code = modified_code_head + code_dict['code'] + modified_code_main
            with open(code_file_name, "w", encoding='utf-8') as f:
                f.write(modified_code)
            print(f"Code saved to {code_file_name}")
            logging.info(f"Code saved to {code_file_name}")
            code_dict['code_file_name'] = code_file_name

            # execute code
            print(f"-------------Start executing code{sig}--------------")
            output_grid_list, error_signal, error_message = run_code_on_inputs(
                    code_file_name,
                    [example_pair[0] for example_pair in exs]
                    )
            
            write_code_dict = {}
            for key, value in code_dict.items():
                write_code_dict[key] = value
            write_code_dict['error_signal'] = error_signal
            write_code_dict['error_message'] = error_message
            write_code_dict['former correct rate'] = 0
            write_code_dict['small mutation rate'] = 0
            write_code_dict['mutation rate'] = 0
            write_code_dict['created_by'] = 'initial_programming'
            write_code_dict['created_round'] = 0
            programs_dict[code_file_name] = write_code_dict
            example_result_dict[code_file_name] = output_grid_list
            former_correct_rate_dict[code_file_name] = 0
            mutation_rate_dict[code_file_name] = 0
            small_mutation_rate_dict[code_file_name] = 0
            ensure_flow_node(
                    code_file_name,
                    created_by = "initial_programming",
                    created_round = 0,
                    details = {
                        "initial_code_index": sig,
                        "analogy": write_code_dict.get("analogy"),
                        "reason": write_code_dict.get("reason"),
                        "rule": write_code_dict.get("rule"),
                        "objects": write_code_dict.get("objects"),
                        "used_expansion_concepts": write_code_dict.get("used_expansion_concepts"),
                        "used_quantitative_mechanisms": write_code_dict.get("used_quantitative_mechanisms"),
                        "implementation_notes": write_code_dict.get("implementation_notes"),
                        "speculative_warnings": write_code_dict.get("speculative_warnings"),
                        }
                    )
            record_flow_event(
                    "initial_programming",
                    target_code_file_name = code_file_name,
                    round_id = 0,
                    details = {
                        "initial_code_index": sig,
                        "analogy": write_code_dict.get("analogy"),
                        "reason": write_code_dict.get("reason"),
                        "rule": write_code_dict.get("rule"),
                        "objects": write_code_dict.get("objects"),
                        "used_expansion_concepts": write_code_dict.get("used_expansion_concepts"),
                        "used_quantitative_mechanisms": write_code_dict.get("used_quantitative_mechanisms"),
                        "implementation_notes": write_code_dict.get("implementation_notes"),
                        "speculative_warnings": write_code_dict.get("speculative_warnings"),
                        }
                    )

        if successful_initial_code_count == 0:
            print(f"All initial programming attempts failed!")
            logging.info("All initial programming attempts failed!")
            finish_test_one_file(failed_reason = "initial_programming_all_failed")
            return None

        save_all_current_code_visualizations(-1, "initial_programming", update_program_error = False)
        print("Finish Programming Part!")
        programs_dict['circulate times'] = 0
        programs_dict_file = os.path.join(programs_dir, f'programs_{ex_name}.json')
        program_write_dict = {}
        program_write_dict[ex_name] = programs_dict
        with open(programs_dict_file, "w") as f:
            json.dump(program_write_dict, f)
            print(f"Programs already saved to {programs_dict_file}")
            logging.info(f"Programs already saved to {programs_dict_file}")

    def persist_programs_state(checkpoint_round = None):
        program_write_dict[ex_name] = programs_dict
        with open(programs_dict_file, "w") as f:
            json.dump(program_write_dict, f)
        print(f"Programs already saved to {programs_dict_file}")
        logging.info(f"Programs already saved to {programs_dict_file}")
        if checkpoint_round is not None:
            programs_dict_file_circ = os.path.join(
                    programs_dir,
                    f'programs_{ex_name}_circ_{checkpoint_round}.json',
                    )
            with open(programs_dict_file_circ, "w") as f:
                json.dump(program_write_dict, f)
            print(f"Programs already saved to {programs_dict_file_circ}")
            logging.info(f"Programs already saved to {programs_dict_file_circ}")

    all_solved_code_filename = []
    break_sig = False
    circ_sig = circ_times
    for circ_sig in range(circ_times, max_circ_times):
        round_id = circ_sig + 1
        new_mutate_programs_dict = {}
        all_solved_code_filename_temp = []
        print(f"Start circulate {circ_sig+1}!")
        logging.info(f"Start circulate {circ_sig+1}!")
        # Judge examples output
        print("Start judging code outputs!")
        for judge_code_file_name, judge_code_result_dict in programs_dict.items():
            if judge_code_file_name == 'circulate times':
                continue
            if judge_code_result_dict is None:
                continue
            if judge_code_result_dict['error_signal']:
                continue
            judge_code_result_grid = example_result_dict[judge_code_file_name]
            if judge_code_result_grid is None or len(judge_code_result_grid) == 0:
                judge_code_result_dict['error_signal'] = True
                judge_code_result_dict['error_message'] = "The output grid is None, which is not valid!"
                continue
            all_right = True
            for ex_num_sig in range(len(exs)):
                try:
                    if judge_code_result_grid[ex_num_sig] != exs[ex_num_sig][1]:
                        all_right = False
                except Exception as e:
                    all_right = False
                    judge_code_result_dict['error_signal'] = True
                    judge_code_result_dict['error_message'] = f"Example result comparison failed: {e}"
                    break
            if all_right:
                print(f"All examples are right! Code is {judge_code_file_name}")
                logging.info(f"All examples are right! Code is {judge_code_file_name}")
                all_solved_code_filename_temp.append(judge_code_file_name)

        # compute current output of questions
        for code_file_name, code_result_dict in programs_dict.items():
            if code_file_name == 'circulate times':
                continue
            if code_result_dict == None:
                continue
            # execute code
            print(f"-------Start computing current output of {code_file_name}--------")
            output_grid_list_temp, error_signal, error_message = run_code_on_inputs(code_file_name, ques)
            code_result_dict['error_signal'] = error_signal
            code_result_dict['error_message'] = error_message
            output_grid_temp_dict[code_file_name] = output_grid_list_temp


        if all_solved_code_filename_temp:
            break_sig_sig = False
            print(f"Start break judging! Some codes are leaving!")
            logging.info(f"Start break judging! Some codes are leaving!")
            for judge_code_file_name in all_solved_code_filename_temp:
                code_file_dict = programs_dict[judge_code_file_name]
                output_result_one_program = output_grid_temp_dict[judge_code_file_name]
                introspection_result = run_model_introspection(
                        judge_code_file_name,
                        code_file_dict,
                        output_result_one_program,
                        round_id,
                        "pre_rectify",
                        )
                break_sig_t = introspection_result["is_valid"]
                break_judge_details = introspection_result["details"]
                final_rectify_prompt_content = introspection_result["rectify_prompt_content"]
                code_file_dict.setdefault("introspection_history", []).append(break_judge_details)
                if break_sig_t:
                    set_pipeline_validity(
                            judge_code_file_name,
                            True,
                            reason = "break_judge_valid",
                            round_id = round_id,
                            )
                    record_flow_event(
                            "pipeline_validated",
                            target_code_file_name = judge_code_file_name,
                            round_id = round_id,
                            details = break_judge_details,
                    )
                    if judge_code_file_name not in all_solved_code_filename:
                        all_solved_code_filename.append(judge_code_file_name)
                    break_sig = True
                    break_sig_sig = True
                else:
                    set_pipeline_validity(
                            judge_code_file_name,
                            False,
                            reason = "break_judge_abnormal",
                            round_id = round_id,
                            )
                    record_flow_event(
                            "pipeline_abnormal",
                            target_code_file_name = judge_code_file_name,
                            round_id = round_id,
                            details = break_judge_details,
                            )
                    print(f"--------Start all examples correct but abnormal code {judge_code_file_name}--------")
                    logging.info(f"Start rectify.")
                    if final_rectify_prompt_content is None:
                        print(f"Final rectify skipped on {judge_code_file_name}: question outputs are incomplete.")
                        record_flow_event(
                                "final_rectify",
                                source_code_file_name = judge_code_file_name,
                                target_code_file_name = judge_code_file_name,
                                round_id = round_id,
                                status = "failed",
                                details = {"reason": "incomplete_question_outputs"},
                                )
                        continue
                    set_token_context("final_rectify", round_id)
                    full_response = final_rectify(final_rectify_prompt_content, mc)
                    if full_response == None:
                        print(f"Final rectify failed on {judge_code_file_name}!")
                        record_flow_event(
                                "final_rectify",
                                source_code_file_name = judge_code_file_name,
                                target_code_file_name = judge_code_file_name,
                                round_id = round_id,
                                status = "failed",
                                )
                    else:
                        logging.info(full_response)
                        reasoning = extract_section(full_response, "REASONING:")
                        code = clean_code(extract_section(full_response, "CODE:"))
                        explanation = extract_section(full_response, "EXPLANATION:")
                        if not isinstance(code, str) or not code.strip():
                            print(f"Final rectify returned empty code on {judge_code_file_name}!")
                            record_flow_event(
                                    "final_rectify",
                                    source_code_file_name = judge_code_file_name,
                                    target_code_file_name = judge_code_file_name,
                                    round_id = round_id,
                                    status = "failed",
                                    details = {"reason": "empty_code"},
                                    )
                            continue
                        # Update dict
                        code_file_dict['code'] = code
                        code_file_dict['code reasoning'] = reasoning
                        code_file_dict['explanation'] = explanation
                        modified_code = modified_code_head + code_file_dict['code'] + modified_code_main
                        with open(judge_code_file_name, "w", encoding='utf-8') as f:
                            f.write(modified_code)
                            print(f"Modified code saved to {judge_code_file_name}")
                            logging.info(f"Modified code saved to {judge_code_file_name}")
                        persist_programs_state()
                        record_flow_event(
                                "final_rectify",
                                source_code_file_name = judge_code_file_name,
                                target_code_file_name = judge_code_file_name,
                                round_id = round_id,
                                status = "success",
                                )
                        rectified_example_outputs, example_error_signal, example_error_message = run_code_on_inputs(
                                judge_code_file_name,
                                [example_pair[0] for example_pair in exs],
                                )
                        example_result_dict[judge_code_file_name] = rectified_example_outputs
                        code_file_dict['error_signal'] = example_error_signal
                        code_file_dict['error_message'] = example_error_message
                        rectified_examples_right = (
                                not example_error_signal
                                and examples_all_correct(rectified_example_outputs)
                                )
                        if not rectified_examples_right:
                            set_pipeline_validity(
                                    judge_code_file_name,
                                    False,
                                    reason = "final_rectify_examples_failed",
                                    round_id = round_id,
                                    )
                            print(f"Final rectify no longer passes all examples: {judge_code_file_name}")
                            record_flow_event(
                                    "final_rectify_validation",
                                    target_code_file_name = judge_code_file_name,
                                    round_id = round_id,
                                    status = "failed",
                                    details = {
                                        "reason": "examples_failed",
                                        "error_signal": example_error_signal,
                                        "error_message": example_error_message,
                                        },
                                    )
                            persist_programs_state()
                            continue

                        rectified_question_outputs, question_error_signal, question_error_message = run_code_on_inputs(
                                judge_code_file_name,
                                ques,
                                )
                        output_grid_temp_dict[judge_code_file_name] = rectified_question_outputs
                        code_file_dict['error_signal'] = question_error_signal
                        code_file_dict['error_message'] = question_error_message
                        if question_error_signal or not outputs_complete(rectified_question_outputs, len(ques)):
                            set_pipeline_validity(
                                    judge_code_file_name,
                                    False,
                                    reason = "final_rectify_question_execution_failed",
                                    round_id = round_id,
                                    )
                            print(f"Final rectify question execution failed: {judge_code_file_name}")
                            record_flow_event(
                                    "final_rectify_validation",
                                    target_code_file_name = judge_code_file_name,
                                    round_id = round_id,
                                    status = "failed",
                                    details = {
                                        "reason": "question_execution_failed",
                                        "error_message": question_error_message,
                                        },
                                    )
                            persist_programs_state()
                            continue

                        post_rectify_result = run_model_introspection(
                                judge_code_file_name,
                                code_file_dict,
                                rectified_question_outputs,
                                round_id,
                                "post_rectify",
                                )
                        post_rectify_details = post_rectify_result["details"]
                        code_file_dict.setdefault("introspection_history", []).append(post_rectify_details)
                        if post_rectify_result["is_valid"]:
                            set_pipeline_validity(
                                    judge_code_file_name,
                                    True,
                                    reason = "post_rectify_break_judge_valid",
                                    round_id = round_id,
                                    )
                            if judge_code_file_name not in all_solved_code_filename:
                                all_solved_code_filename.append(judge_code_file_name)
                            break_sig = True
                            break_sig_sig = True
                            print(f"Final rectify passed examples and {introspection_model_key} introspection: {judge_code_file_name}")
                            record_flow_event(
                                    "pipeline_validated",
                                    target_code_file_name = judge_code_file_name,
                                    round_id = round_id,
                                    details = post_rectify_details,
                                    )
                        else:
                            set_pipeline_validity(
                                    judge_code_file_name,
                                    False,
                                    reason = "post_rectify_break_judge_abnormal",
                                    round_id = round_id,
                                    )
                            print(f"Final rectify still failed {introspection_model_key} introspection: {judge_code_file_name}")
                            record_flow_event(
                                    "pipeline_abnormal",
                                    target_code_file_name = judge_code_file_name,
                                    round_id = round_id,
                                    details = post_rectify_details,
                                    )
                        persist_programs_state()
                        save_code_visualization_snapshot(
                                judge_code_file_name,
                                circ_sig,
                                f"circ_{circ_sig + 1}_post_rectify",
                                question_outputs = rectified_question_outputs,
                                question_error_signal = False,
                                question_error_message = "",
                                update_program_error = False,
                                )
            if break_sig_sig:
                for solved_code_file_name in all_solved_code_filename_temp:
                    save_code_visualization_snapshot(
                            solved_code_file_name,
                            circ_sig,
                            f"circ_{circ_sig + 1}_solved",
                            question_outputs = output_grid_temp_dict.get(solved_code_file_name),
                            question_error_signal = False,
                            question_error_message = "",
                            update_program_error = False,
                            )
                programs_dict['circulate times'] = round_id
                persist_programs_state(checkpoint_round = round_id)
                break



        # metrics between code output and ground truth
        difference_grids_dict = {}
        best_correct_rate = 0
        best_file_name = None
        best_reason = ""
        best_analogy = ""
        worst_former_correct_rate = 1
        worst_former_file_name = None
        worst_correct_rate = 1
        worst_file_name = None
        invalid_code_file_num = 0
        all_code_file_num = len(programs_dict) - 1

        for judge_code_file_name, judge_code_result_dict in programs_dict.items():
            if judge_code_file_name == 'circulate times':
                continue
            if judge_code_result_dict == None:
                continue
            if judge_code_result_dict['error_signal']:
                continue
            difference_one_program_dict = {}
            judge_code_result_grid = example_result_dict[judge_code_file_name]
            difference_grids, grids_coor_list, correct_rate = metrics_code_grid(judge_code_result_dict, judge_code_result_grid, exs, judge_mask_exs)
            difference_one_program_dict['grids'] = difference_grids
            difference_one_program_dict['coordinates'] = grids_coor_list
            difference_one_program_dict['correct_rate'] = correct_rate
            difference_grids_dict[judge_code_file_name] = difference_one_program_dict
            if correct_rate > best_correct_rate:
                best_correct_rate = correct_rate
                best_file_name = judge_code_file_name
            if correct_rate < worst_correct_rate:
                worst_correct_rate = correct_rate
                worst_file_name = judge_code_file_name
            if former_correct_rate_dict[judge_code_file_name] < worst_former_correct_rate and former_correct_rate_dict[judge_code_file_name] != 0:
                worst_former_correct_rate = former_correct_rate_dict[judge_code_file_name]
                worst_file_name = judge_code_file_name
            elif former_correct_rate_dict[judge_code_file_name] == 0:
                invalid_code_file_num += 1

            # update mutation probablity
            if correct_rate > former_correct_rate_dict[judge_code_file_name]:
                mutation_rate_dict[judge_code_file_name] += delta_mutation_rate * coeff_right_delta_mutation
            else:
                mutation_rate_dict[judge_code_file_name] += delta_mutation_rate
            if correct_rate > former_correct_rate_dict[judge_code_file_name]:
                small_mutation_rate_dict[judge_code_file_name] = small_mutation_rate_dict[judge_code_file_name] - delta_small_mutation_rate if small_mutation_rate_dict[judge_code_file_name] - delta_small_mutation_rate > 0 else 0
            elif correct_rate == former_correct_rate_dict[judge_code_file_name]:
                small_mutation_rate_dict[judge_code_file_name] += delta_small_mutation_rate * 2 
            else:
                small_mutation_rate_dict[judge_code_file_name] += delta_small_mutation_rate * coeff_right_delta_small_mutation

            former_correct_rate_dict[judge_code_file_name] = correct_rate
            judge_code_result_dict['mutation rate'] = mutation_rate_dict[judge_code_file_name]
            judge_code_result_dict['small mutation rate'] = small_mutation_rate_dict[judge_code_file_name]
            judge_code_result_dict['former correct rate'] = correct_rate

            if correct_rate == 1:
                mutation_rate_dict[judge_code_file_name] = 0
                small_mutation_rate_dict[judge_code_file_name] = 0
                judge_code_result_dict['mutation rate'] = mutation_rate_dict[judge_code_file_name]
                judge_code_result_dict['small mutation rate'] = small_mutation_rate_dict[judge_code_file_name]

        # species elimination
        if all_code_file_num - invalid_code_file_num > 6:
            print(f"Species elimination starts to judge!")
            if worst_file_name != None and worst_file_name == worst_former_file_name:
                print(f"!!!Attention, species elimination happens on {worst_former_file_name}!!!")
                logging.info(f"!!!Attention, species elimination happens on {worst_former_file_name}!!!")
                programs_dict[worst_former_file_name] = None
            else:
                print(f"Everyone lives.")

        # prepare crossover prompts
        if best_file_name:
            best_dict = programs_dict[best_file_name]
            best_analogy = best_dict['analogy']
            best_reason = best_dict['reason']
            best_explanation = best_dict['explanation']
            best_code_prompt_content = [
                    {
                        "type": "text",
                        "text": "The better code is shown below:"
                        },
                    {
                        "type": "text",
                        "text": best_dict['code']
                    },
                    {
                        "type": "text",
                        "text": format_analogy_context(best_dict, "The analogy context of the better code")
                        },
                    {
                        "type": "text",
                        "text": "The explanation of the better code:" + best_explanation
                        }
                    ]
        print("Finish judging code outputs!")


        # reflection part, CoT and question
        print("Start modifying codes!")
        instruction_programs_dict = {}
        def modify_program_with_llm(job):
            code_file_name = job['code_file_name']
            code_file_dict = copy.deepcopy(job['code_file_dict'])
            result = {
                    'code_file_name': code_file_name,
                    'code_file_dict': code_file_dict,
                    'status': 'execute',
                    'write_code': None,
                    'instruction': None,
                    'small_mutation_rate': None,
                    'mutation_rate': None,
                    'new_mutation': None,
                    'events': [],
                    }

            if job.get('skip_solved'):
                print(f"Skip {code_file_name}.")
                return result

            print(f"-------------Start modifying {code_file_name}--------------")
            if code_file_dict['error_signal']:
                logging.info(f"Start rectifying {code_file_name}.")
                print(f"Start rectifying {code_file_name}.")
                set_token_context("rectify_error_code", round_id)
                rectified_code = rectify_code_file(code_file_dict, mc)
                if rectified_code != None:
                    code_file_dict['code'] = rectified_code
                    code_file_dict['error_signal'] = False
                    code_file_dict['error_message'] = ""
                    result['code_file_dict'] = code_file_dict
                    result['write_code'] = modified_code_head + rectified_code + modified_code_main
                    result['events'].append({
                        "type": "rectify",
                        "source_code_file_name": code_file_name,
                        "target_code_file_name": code_file_name,
                        "round_id": round_id,
                        "status": "success",
                        "details": {"reason": "error_signal"},
                        })
                else:
                    print(f"Rectify code failed! Code filename: {code_file_name}")
                    logging.info(f"Rectify code failed! Code filename: {code_file_name}")
                    result['events'].append({
                        "type": "rectify",
                        "source_code_file_name": code_file_name,
                        "target_code_file_name": code_file_name,
                        "round_id": round_id,
                        "status": "failed",
                        "details": {"reason": "error_signal"},
                        })
                    result['status'] = 'skip'
                return result

            question_prompt_content = job['question_prompt_content']
            code_prompt_content = job['code_prompt_content']
            crossover_prompt_content = job['crossover_prompt_content']
            abnormal_prompt_content = job['abnormal_prompt_content']
            small_mutation_prompt_content = job['small_mutation_prompt_content']

            # small mutation: add sub-concepts to the existing analogy
            # also known as concepts augmentation
            if job['do_small_mutation']:
                result['small_mutation_rate'] = job['new_small_mutation_rate']
                code_file_dict['small mutation rate'] = job['new_small_mutation_rate']

                print(f"-----!!!Attention, small mutation happens on {code_file_name}!!!-----")
                logging.info(f"-----!!!Attention, small mutation happens on {code_file_name}!!!-----")
                set_token_context("small_mutation_analogy", round_id)
                full_response_small_mutation = augmentation_analogy(small_mutation_prompt_content, auxiliary_mc)
                if full_response_small_mutation == None:
                    print("-----Small mutation (concept augmentation) Failed!-----")
                    logging.info("-----Small mutation (concept augmentation) Failed.-----")
                else:
                    logging.info(full_response_small_mutation)
                    small_mutation_analogy = extract_section(full_response_small_mutation, "ANALOGY:")
                    small_mutation_proposals = extract_section(full_response_small_mutation, "PROPOSALS:")
                    augment_analogy_target_dict = parse_single_analogy_target_response(small_mutation_analogy)
                    if augment_analogy_target_dict == None:
                        print("Parsing small mutation dict failed!")
                        logging.info("Parsing small mutation dict failed.")
                    else:
                        previous_context = normalize_pipeline_analogy_context(code_file_dict)
                        code_file_dict['analogy'] = augment_analogy_target_dict['Analogy']
                        code_file_dict['reason'] = augment_analogy_target_dict['Reason']
                        code_file_dict['rule'] = augment_analogy_target_dict.get('Rule', '')
                        code_file_dict['objects'] = augment_analogy_target_dict.get('Objects', [])
                        new_context = normalize_pipeline_analogy_context(code_file_dict)
                        result['events'].append({
                            "type": "small_mutation",
                            "source_code_file_name": code_file_name,
                            "target_code_file_name": code_file_name,
                            "round_id": round_id,
                            "status": "success",
                            "details": {
                                "new_small_mutation_rate": job['new_small_mutation_rate'],
                                "previous_analogy": previous_context.get("Analogy"),
                                "previous_reason": previous_context.get("Reason"),
                                "previous_rule": previous_context.get("Rule"),
                                "previous_objects": previous_context.get("Objects"),
                                "analogy": new_context.get("Analogy"),
                                "reason": new_context.get("Reason"),
                                "rule": new_context.get("Rule"),
                                "objects": new_context.get("Objects"),
                                "proposals": small_mutation_proposals,
                                },
                            })
                        question_prompt_content.append({
                            "type": "text",
                            "text": (
                                "Attention, the analogy context has been augmented in this execution.\n"
                                + format_analogy_context(code_file_dict, "Updated analogy context")
                                + "\nThe augmentation details and the modification proposals are shown below: "
                                + str(small_mutation_proposals)
                                )
                            })
                if full_response_small_mutation == None:
                    result['events'].append({
                        "type": "small_mutation",
                        "source_code_file_name": code_file_name,
                        "target_code_file_name": code_file_name,
                        "round_id": round_id,
                        "status": "failed",
                        "details": {"new_small_mutation_rate": job['new_small_mutation_rate']},
                        })

            # get instructions
            print("Start getting instructions!")
            logging.info(f"Start getting instructions on {code_file_name}!")
            set_token_context("question_instruction", round_id)
            instruction_reason, instruction_one_program = question_one_program(question_prompt_content, mc)
            instruction_one_program = instruction_one_program or ""
            result['instruction'] = instruction_one_program
            code_prompt_content.append({
                "type": "text",
                "text": "The modify instructions are below:" + instruction_one_program
                })

            # crossover codes
            if job['do_crossover']:
                print(f"!!!Attention, crossover happens on {code_file_name}!!!")
                logging.info(f"!!!Attention, crossover happens on {code_file_name}!!!")
                for best_code_content_dict in job['best_code_prompt_content']:
                    crossover_prompt_content.append(best_code_content_dict)
                set_token_context("crossover_instruction", round_id)
                full_response_crossover_instructions = crossover_two_programs(crossover_prompt_content, mc)
                if full_response_crossover_instructions != None:
                    logging.info(full_response_crossover_instructions)
                    crossover_instructions = extract_section(full_response_crossover_instructions, "INSTRUCTIONS:") or ""
                    result['events'].append({
                        "type": "crossover",
                        "source_code_file_name": job.get('best_file_name'),
                        "target_code_file_name": code_file_name,
                        "round_id": round_id,
                        "status": "success",
                        "details": {"instructions": crossover_instructions},
                        })
                    code_prompt_content.append({
                        "type": "text",
                        "text": "The modify instructions from analyzing the better code are below:" + crossover_instructions
                        })
                else:
                    print("Crossover failed!")
                    logging.info("Crossover failed.")
                    result['events'].append({
                        "type": "crossover_failed",
                        "source_code_file_name": job.get('best_file_name'),
                        "target_code_file_name": code_file_name,
                        "round_id": round_id,
                        "status": "failed",
                        "details": {},
                        })

            # finding abnormal part of the results
            logging.info(f"Finding abnormal part of the results on {code_file_name}.")
            set_token_context("abnormal_instruction", round_id)
            full_response_abnormal_instructions = finding_abnormal_from_result(abnormal_prompt_content, introspection_mc)
            if full_response_abnormal_instructions != None:
                logging.info(full_response_abnormal_instructions)
                abnormal_instructions = extract_section(full_response_abnormal_instructions, "INSTRUCTIONS:") or ""
                code_prompt_content.append({
                    "type": "text",
                    "text": "The modify instructions from analyzing the results from questions are below: " + abnormal_instructions
                    })
            else:
                print("Finding abnormal failed!")
                logging.info("Finding abnormal failed.")

            # modify codes
            print("Start modifying!")
            logging.info("Start modifying")
            set_token_context("modify_code", round_id)
            full_response_modifying = modify_one_program(code_prompt_content, mc)
            logging.info(full_response_modifying)
            if full_response_modifying == None:
                print(f"Modify failed! Code filename: {code_file_name}")
                logging.info(f"Modify failed! Code filename: {code_file_name}")
                return result
            reasoning = extract_section(full_response_modifying, "REASONING:")
            code = extract_section(full_response_modifying, "CODE:")
            explanation = extract_section(full_response_modifying, "EXPLANATION:")
            if code == None:
                print(f"Parsing modified code failed! Code filename: {code_file_name}")
                logging.info(f"Parsing modified code failed! Code filename: {code_file_name}")
                return result

            # mutation codes: change the analogy target and reasons, then modifying the code
            if job['do_mutation']:
                result['mutation_rate'] = job['new_mutation_rate']
                code_file_dict['mutation rate'] = job['new_mutation_rate']

                print(f"!!!Attention, mutation happens on {code_file_name}!!!")
                logging.info(f"!!!Attention, mutation happens on {code_file_name}!!!")

                mutate_analogy_content = [
                        {
                            "type": "text",
                            "text": mutate_analogy_prompt
                            },
                        {
                            "type":"text",
                            "text":"The visualization of examples are shown below:"
                            },
                        {
                            "type":"image_url",
                            "image_url": {"url": exs_url}
                            },
                        {
                            "type": "text",
                            "text": format_analogy_context(code_file_dict, "The main analogy context you should consider")
                            },
                        {
                            "type": "text",
                            "text": job['other_analogy_and_reason']
                            }
                        ]
                mutate_code_content = [
                        {
                            "type": "text",
                            "text": mutate_code_prompt
                            },
                        {
                            "type":"text",
                            "text":"The visualization of examples are shown below:"
                            },
                        {
                            "type":"image_url",
                            "image_url": {"url": exs_url}
                            },
                        {
                            "type":"text",
                            "text":"The matrix of examples are shown below:"
                            },
                        {
                            "type":"text",
                            "text":str(code_prompt_dict)
                            },
                        {
                            "type": "text",
                            "text": format_analogy_context(code_file_dict, "The former analogy context")
                            },
                        {
                            "type": "text",
                            "text": "The former code is shown below:"
                            },
                        {
                            "type": "text",
                            "text": code_file_dict['code']
                            },
                        ]

                set_token_context("mutation", round_id)
                new_code_file_dict = mutate_code_file(mutate_analogy_content, mutate_code_content, mc, analogy_mc = auxiliary_mc)
                if new_code_file_dict == None or new_code_file_dict.get('code') == None:
                    print(f"Mutation Failed!")
                    logging.info(f"Mutation Failed!")
                    result['events'].append({
                        "type": "mutation_failed",
                        "source_code_file_name": code_file_name,
                        "target_code_file_name": None,
                        "round_id": round_id,
                        "status": "failed",
                        "details": {"new_mutation_rate": job['new_mutation_rate']},
                        })
                else:
                    result['new_mutation'] = {
                            'code_file_dict': new_code_file_dict,
                            'write_code': modified_code_head + new_code_file_dict['code'] + modified_code_main,
                            'source_code_file_name': code_file_name,
                            'round_id': round_id,
                            'new_mutation_rate': job['new_mutation_rate'],
                            }

            # Update dict
            code_file_dict['code'] = code
            code_file_dict['code reasoning'] = reasoning
            code_file_dict['explanation'] = explanation
            result['code_file_dict'] = code_file_dict
            result['write_code'] = modified_code_head + code_file_dict['code'] + modified_code_main
            result['events'].append({
                "type": "modify",
                "source_code_file_name": code_file_name,
                "target_code_file_name": code_file_name,
                "round_id": round_id,
                "status": "success",
                "details": {},
                })
            return result

        modification_jobs = []
        for code_file_name, code_file_dict in list(programs_dict.items()):
            if code_file_name == 'circulate times':
                continue
            if code_file_dict == None:
                continue
            job = {
                    'code_file_name': code_file_name,
                    'code_file_dict': copy.deepcopy(code_file_dict),
                    'skip_solved': code_file_name in all_solved_code_filename_temp,
                    'do_small_mutation': False,
                    'do_crossover': False,
                    'do_mutation': False,
                    'new_small_mutation_rate': small_mutation_rate_dict.get(code_file_name, 0),
                    'new_mutation_rate': mutation_rate_dict.get(code_file_name, 0),
                    'best_file_name': best_file_name,
                    'best_code_prompt_content': best_code_prompt_content if best_file_name else [],
                    }
            if code_file_name in all_solved_code_filename_temp:
                modification_jobs.append(job)
                continue

            if code_file_dict['error_signal']:
                modification_jobs.append(job)
                continue

            # preparing prompts
            question_prompt_content = [
                    {
                        "type": "text",
                        "text": question_code_prompt
                    },
                    {
                        "type": "text",
                        "text": format_analogy_context(code_file_dict, "The analogy context of the question")
                        },
                    {
                        "type": "text",
                        "text": "The code:" + code_file_dict['code']
                        },
                    {
                        "type": "text",
                        "text": "The explanation of the code:" + code_file_dict["explanation"]
                        }
                    ]

            code_prompt_content = [
                    {
                        "type": "text",
                        "text": modify_code_prompt
                    },
                    {
                        "type": "text",
                        "text": format_analogy_context(code_file_dict, "The analogy context of the question")
                        },
                    {
                        "type": "text",
                        "text": "The code:" + code_file_dict['code']
                        },
                    {
                        "type": "text",
                        "text": "The explanation of the code:" + code_file_dict["explanation"]
                        }
                    ]
            crossover_prompt_content = [
                    {
                        "type": "text",
                        "text": crossover_code_prompt
                    },
                    {
                        "type": "text",
                        "text": format_analogy_context(code_file_dict, "The analogy context of the question")
                        },
                    {
                        "type": "text",
                        "text": "The code:" + code_file_dict['code']
                        },
                    {
                        "type": "text",
                        "text": "The explanation of the code:" + code_file_dict["explanation"]
                        },
                    {
                        "type":"text",
                        "text":"The visualization of examples are shown below:"
                        },
                    {
                        "type":"image_url",
                        "image_url": {"url": exs_url}
                        }
                    ]
            abnormal_prompt_content = [
                    {
                        "type": "text",
                        "text": abnormal_code_prompt
                    },
                    {
                        "type": "text",
                        "text": format_analogy_context(code_file_dict, "The analogy context of the question")
                        },
                    {
                        "type": "text",
                        "text": "The code:" + code_file_dict['code']
                        },
                    {
                        "type": "text",
                        "text": "The explanation of the code:" + code_file_dict["explanation"]
                        },
                    {
                        "type":"text",
                        "text":"The visualization of examples are shown below:"
                        },
                    {
                        "type":"image_url",
                        "image_url": {"url": exs_url}
                        }
                    ]
            small_mutation_prompt_content = [
                    {
                        "type": "text",
                        "text": small_mutation_code_prompt
                    },
                    {
                        "type": "text",
                        "text": format_analogy_context(code_file_dict, "The analogy context of the question")
                        },
                    {
                        "type": "text",
                        "text": "The code:" + code_file_dict['code']
                        },
                    {
                        "type": "text",
                        "text": "The explanation of the code:" + code_file_dict["explanation"]
                        }
                    ]


            # visualize difference grid
            difference_one_program_dict = difference_grids_dict[code_file_name]
            for exs_num_sig in range(len(exs)):
                one_ex_url, one_ex_b64 = vis_difference_grid_for_LLM(exs[exs_num_sig], example_result_dict[code_file_name][exs_num_sig], False)
                diff_ex_url, diff_ex_b64 = vis_difference_grid_for_LLM(difference_one_program_dict['grids'][exs_num_sig][0][0], difference_one_program_dict['grids'][exs_num_sig][0][1], True)
                question_prompt_content.append({
                    "type": "text",
                    "text": f"The visualization of input-output-groudtruth of example{exs_num_sig+1} is shown below:"
                    })
                question_prompt_content.append({
                    "type": "image_url",
                    "image_url": {"url": one_ex_url}
                    })
                question_prompt_content.append({
                    "type": "text",
                    "text": "The matrix of input is:" + str(exs[exs_num_sig][0])
                    })
                question_prompt_content.append({
                    "type": "text",
                    "text": "The matrix of code output is:" + str(example_result_dict[code_file_name][exs_num_sig])
                    })
                question_prompt_content.append({
                    "type": "text",
                    "text": "The matrix of groud truth output is:" + str(exs[exs_num_sig][1])
                    })
                question_prompt_content.append({
                    "type": "text",
                    "text": f"The visualization of difference grids of example{exs_num_sig+1} is shown below:"
                    })
                question_prompt_content.append({
                    "type": "image_url",
                    "image_url": {"url": diff_ex_url}
                    })
                question_prompt_content.append({
                    "type": "text",
                    "text": "The coordinates of the different grids are:" + str(difference_one_program_dict['coordinates'])
                    })
                code_prompt_content.append({
                    "type": "text",
                    "text": f"The visualization of input-output-groudtruth of example{exs_num_sig+1} is shown below:"
                    })
                code_prompt_content.append({
                    "type": "image_url",
                    "image_url": {"url": one_ex_url}
                    })
                code_prompt_content.append({
                    "type": "text",
                    "text": "The matrix of input is:" + str(exs[exs_num_sig][0])
                    })
                code_prompt_content.append({
                    "type": "text",
                    "text": "The matrix of code output is:" + str(example_result_dict[code_file_name][exs_num_sig])
                    })
                code_prompt_content.append({
                    "type": "text",
                    "text": "The matrix of groud truth output is:" + str(exs[exs_num_sig][1])
                    })
                small_mutation_prompt_content.append({
                    "type": "text",
                    "text": f"The visualization of input-output-groudtruth of example{exs_num_sig+1} is shown below:"
                    })
                small_mutation_prompt_content.append({
                    "type": "image_url",
                    "image_url": {"url": one_ex_url}
                    })
                small_mutation_prompt_content.append({
                    "type": "text",
                    "text": "The matrix of input is:" + str(exs[exs_num_sig][0])
                    })
                small_mutation_prompt_content.append({
                    "type": "text",
                    "text": "The matrix of code output is:" + str(example_result_dict[code_file_name][exs_num_sig])
                    })
                small_mutation_prompt_content.append({
                    "type": "text",
                    "text": "The matrix of groud truth output is:" + str(exs[exs_num_sig][1])
                    })
                small_mutation_prompt_content.append({
                    "type": "text",
                    "text": f"The visualization of difference grids of example{exs_num_sig+1} is shown below:"
                    })
                small_mutation_prompt_content.append({
                    "type": "image_url",
                    "image_url": {"url": diff_ex_url}
                    })
                small_mutation_prompt_content.append({
                    "type": "text",
                    "text": "The coordinates of the different grids are:" + str(difference_one_program_dict['coordinates'])
                    })

            # visualize result grids
            output_result_one_program = output_grid_temp_dict[code_file_name]
            for ques_sig_num in range(len(ques)):
                result_ques_url, result_ques_b64 = vis_result_grid_for_LLM(ques[ques_sig_num], output_result_one_program[ques_sig_num])
                abnormal_prompt_content.append({
                    "type": "text",
                    "text": f"The visualization of the question {ques_sig_num+1} input and the corresponding output from the code is shown below:"
                    })
                abnormal_prompt_content.append({
                    "type": "image_url",
                    "image_url": {"url": result_ques_url}
                    })
                abnormal_prompt_content.append({
                    "type": "text",
                    "text": f"The input matrix of the question {ques_sig_num+1} is " + str(ques[ques_sig_num])
                    })
                abnormal_prompt_content.append({
                    "type": "text",
                    "text": f"The corresponding output matrix of the question {ques_sig_num+1} from the code is " + str(output_result_one_program[ques_sig_num])
                    })

            current_small_mutation_rate = small_mutation_rate_dict.get(code_file_name, 0)
            if random.uniform(0, 1) < current_small_mutation_rate:
                job['do_small_mutation'] = True
                job['new_small_mutation_rate'] = current_small_mutation_rate - 4*delta_small_mutation_rate if current_small_mutation_rate - 4*delta_small_mutation_rate > 0 else 0

            if code_file_name != best_file_name and best_file_name:
                if random.uniform(0, 1) < crossover_rate:
                    job['do_crossover'] = True

            current_mutation_rate = mutation_rate_dict.get(code_file_name, 0)
            if random.uniform(0, 1) < current_mutation_rate:
                job['do_mutation'] = True
                job['new_mutation_rate'] = current_mutation_rate - 4*delta_mutation_rate if current_mutation_rate - 4*delta_mutation_rate > 0 else 0

            other_analogy_and_reason = format_other_analogy_contexts(programs_dict, code_file_name)

            job['question_prompt_content'] = question_prompt_content
            job['code_prompt_content'] = code_prompt_content
            job['crossover_prompt_content'] = crossover_prompt_content
            job['abnormal_prompt_content'] = abnormal_prompt_content
            job['small_mutation_prompt_content'] = small_mutation_prompt_content
            job['other_analogy_and_reason'] = other_analogy_and_reason
            modification_jobs.append(job)

        modification_results = []
        if modification_jobs:
            if api_route_name == "uni":
                modify_workers = int(os.environ.get("ARCANA_UNI_PIPELINE_LLM_WORKERS", "2"))
            else:
                modify_workers = int(os.environ.get("ARCANA_PIPELINE_MODIFY_WORKERS", "4"))
            modify_workers = max(1, min(modify_workers, len(modification_jobs)))
            print(f"Start parallel program modification with {modify_workers} workers.")
            logging.info(f"Start parallel program modification with {modify_workers} workers.")
            with ThreadPoolExecutor(max_workers = modify_workers) as executor:
                future_to_job = {
                        executor.submit(modify_program_with_llm, job): job
                        for job in modification_jobs
                        }
                for future in as_completed(future_to_job):
                    job = future_to_job[future]
                    try:
                        modification_results.append(future.result())
                    except Exception as exc:
                        code_file_name = job['code_file_name']
                        logging.exception(f"Modify job failed on {code_file_name}: {exc}")
                        print(f"Modify job failed on {code_file_name}: {exc}")
                        modification_results.append({
                            'code_file_name': code_file_name,
                            'code_file_dict': copy.deepcopy(job['code_file_dict']),
                            'status': 'execute',
                            'write_code': None,
                            'instruction': None,
                            'small_mutation_rate': None,
                            'mutation_rate': None,
                            'new_mutation': None,
                            'events': [{
                                "type": "modify",
                                "source_code_file_name": code_file_name,
                                "target_code_file_name": code_file_name,
                                "round_id": round_id,
                                "status": "failed",
                                "details": {"exception": str(exc)},
                                }],
                            })

        next_mutation_index = len([name for name in programs_dict if name != 'circulate times'])
        for modification_result in modification_results:
            code_file_name = modification_result['code_file_name']
            code_file_dict = modification_result['code_file_dict']
            for flow_event in modification_result.get('events', []):
                record_flow_event(
                        flow_event.get("type"),
                        source_code_file_name = flow_event.get("source_code_file_name"),
                        target_code_file_name = flow_event.get("target_code_file_name"),
                        round_id = flow_event.get("round_id"),
                        status = flow_event.get("status", "success"),
                        details = flow_event.get("details", {}),
                        )
            if modification_result['status'] == 'skip':
                continue

            if modification_result['small_mutation_rate'] != None:
                small_mutation_rate_dict[code_file_name] = modification_result['small_mutation_rate']
                code_file_dict['small mutation rate'] = modification_result['small_mutation_rate']
            if modification_result['mutation_rate'] != None:
                mutation_rate_dict[code_file_name] = modification_result['mutation_rate']
                code_file_dict['mutation rate'] = modification_result['mutation_rate']
            if modification_result['instruction'] != None:
                instruction_programs_dict[code_file_name] = modification_result['instruction']
            ensure_flow_node(
                    code_file_name,
                    details = {
                        "analogy": code_file_dict.get("analogy"),
                        "reason": code_file_dict.get("reason"),
                        "rule": code_file_dict.get("rule"),
                        "objects": code_file_dict.get("objects"),
                        }
                    )

            if modification_result['write_code'] != None:
                with open(code_file_name, "w", encoding='utf-8') as f:
                    f.write(modification_result['write_code'])
                    print(f"Modified code saved to {code_file_name}")
                    logging.info(f"Modified code saved to {code_file_name}")

            print("Start executing code!")
            output_grid_list, error_signal, error_message = run_code_on_inputs(
                    code_file_name,
                    [example_pair[0] for example_pair in exs]
                    )
            code_file_dict['error_signal'] = error_signal
            code_file_dict['error_message'] = error_message
            example_result_dict[code_file_name] = output_grid_list
            programs_dict[code_file_name] = code_file_dict

            new_mutation = modification_result['new_mutation']
            if new_mutation != None:
                while True:
                    new_code_file_name = programs_dir + "/code"+ str(next_mutation_index) + "_" + ex_name + ".py"
                    next_mutation_index += 1
                    if new_code_file_name not in programs_dict and new_code_file_name not in new_mutate_programs_dict:
                        break
                with open(new_code_file_name, "w", encoding='utf-8') as f:
                    f.write(new_mutation['write_code'])
                    print(f"Mutation code saved to {new_code_file_name}")
                    logging.info(f"Mutation code saved to {new_code_file_name}")

                print(f"-------------Start executing mutation code--------------")
                output_grid_list, error_signal, error_message = run_code_on_inputs(
                        new_code_file_name,
                        [example_pair[0] for example_pair in exs]
                        )

                write_code_dict = {}
                for key, value in new_mutation['code_file_dict'].items():
                    write_code_dict[key] = value
                write_code_dict['code_file_name'] = new_code_file_name
                write_code_dict['error_signal'] = error_signal
                write_code_dict['error_message'] = error_message
                write_code_dict['former correct rate'] = 0
                write_code_dict['mutation rate'] = 0
                write_code_dict['small mutation rate'] = 0
                write_code_dict['created_by'] = 'mutation'
                write_code_dict['created_round'] = new_mutation.get('round_id')
                write_code_dict['parent_code_file_name'] = new_mutation.get('source_code_file_name')
                former_correct_rate_dict[new_code_file_name] = 0
                new_mutate_programs_dict[new_code_file_name] = write_code_dict
                example_result_dict[new_code_file_name] = output_grid_list
                mutation_rate_dict[new_code_file_name] = 0
                small_mutation_rate_dict[new_code_file_name] = 0
                ensure_flow_node(
                        new_code_file_name,
                        created_by = "mutation",
                        created_round = new_mutation.get('round_id'),
                        details = {
                            "parent": flow_code_id(new_mutation.get('source_code_file_name')),
                            "analogy": write_code_dict.get("analogy"),
                            "reason": write_code_dict.get("reason"),
                            "rule": write_code_dict.get("rule"),
                            "objects": write_code_dict.get("objects"),
                            }
                        )
                record_flow_event(
                        "mutation",
                        source_code_file_name = new_mutation.get('source_code_file_name'),
                        target_code_file_name = new_code_file_name,
                        round_id = new_mutation.get('round_id'),
                        details = {
                            "new_mutation_rate": new_mutation.get('new_mutation_rate'),
                            "previous_analogy": programs_dict.get(new_mutation.get('source_code_file_name'), {}).get("analogy") if isinstance(programs_dict.get(new_mutation.get('source_code_file_name')), dict) else None,
                            "previous_reason": programs_dict.get(new_mutation.get('source_code_file_name'), {}).get("reason") if isinstance(programs_dict.get(new_mutation.get('source_code_file_name')), dict) else None,
                            "analogy": write_code_dict.get("analogy"),
                            "reason": write_code_dict.get("reason"),
                            "rule": write_code_dict.get("rule"),
                            "objects": write_code_dict.get("objects"),
                            },
                        )

        programs_dict['circulate times'] = circ_sig + 1
        for mutate_code_file_name, mutate_code_file_dict in new_mutate_programs_dict.items():
            programs_dict[mutate_code_file_name] = mutate_code_file_dict
        save_all_current_code_visualizations(circ_sig, f"circ_{circ_sig + 1}_end")
        persist_programs_state(checkpoint_round = circ_sig + 1)


    def summarize_pipeline_correctness(result_dict, total_tests):
        evaluated_programs = []
        best_program = None
        best_correct_num = -1
        best_all_num = total_tests
        best_correct_tests = []
        best_per_test_results = build_per_test_results([], ans)
        solved_programs = []
        partially_correct_programs = []

        for program_name, program_result in result_dict.items():
            if not isinstance(program_result, dict):
                continue
            if "correct_num" not in program_result or "all_num" not in program_result:
                continue
            correct_num = program_result.get("correct_num", 0) or 0
            all_num = program_result.get("all_num", total_tests) or total_tests
            correct_tests = program_result.get("correct_tests", [])
            per_test_results = program_result.get("per_test_results", [])
            evaluated_programs.append(program_name)
            if correct_num == all_num and all_num > 0:
                solved_programs.append(program_name)
            elif correct_num > 0:
                partially_correct_programs.append(program_name)
            if correct_num > best_correct_num:
                best_program = program_name
                best_correct_num = correct_num
                best_all_num = all_num
                best_correct_tests = correct_tests
                best_per_test_results = per_test_results

        if best_correct_num < 0:
            best_correct_num = 0
        best_correct_rate = best_correct_num / best_all_num if best_all_num else 0
        task_correct = best_all_num > 0 and best_correct_num == best_all_num
        task_partially_correct = (not task_correct) and best_correct_num > 0
        return {
                "task_correct": task_correct,
                "task_partially_correct": task_partially_correct,
                "best_program": best_program,
                "best_correct_num": best_correct_num,
                "all_num": best_all_num,
                "best_correct_rate": best_correct_rate,
                "best_correct_tests": best_correct_tests,
                "best_per_test_results": best_per_test_results,
                "evaluated_program_count": len(evaluated_programs),
                "evaluated_programs": evaluated_programs,
                "solved_programs": solved_programs,
	                "partially_correct_programs": partially_correct_programs,
	                }

    def summarize_pipeline_valid_correctness(result_dict):
        valid_programs = []
        valid_correct_programs = []
        valid_partially_correct_programs = []
        valid_wrong_programs = []
        for program_name, program_result in result_dict.items():
            if not isinstance(program_result, dict):
                continue
            if program_result.get("pipeline_valid") is not True:
                continue
            if "correct_num" not in program_result or "all_num" not in program_result:
                continue
            valid_programs.append(program_name)
            if program_result.get("is_correct"):
                valid_correct_programs.append(program_name)
            elif program_result.get("is_partially_correct"):
                valid_partially_correct_programs.append(program_name)
            else:
                valid_wrong_programs.append(program_name)
        valid_program_count = len(valid_programs)
        valid_correct_count = len(valid_correct_programs)
        return {
                "valid_program_count": valid_program_count,
                "valid_correct_count": valid_correct_count,
                "valid_partially_correct_count": len(valid_partially_correct_programs),
                "valid_wrong_count": len(valid_wrong_programs),
                "valid_correct_rate": valid_correct_count / valid_program_count if valid_program_count else 0,
                "valid_programs": valid_programs,
                "valid_correct_programs": valid_correct_programs,
                "valid_partially_correct_programs": valid_partially_correct_programs,
                "valid_wrong_programs": valid_wrong_programs,
                }

    def build_program_metadata(code_file_name):
        code_file_dict = programs_dict.get(code_file_name)
        if not isinstance(code_file_dict, dict):
            return {}
        metadata_keys = [
                "code_file_name",
                "analogy",
                "reason",
                "rule",
                "objects",
                "explanation",
                "code reasoning",
                "code",
                "error_signal",
                "error_message",
                "former correct rate",
                "mutation rate",
                "small mutation rate",
                "created_by",
                "created_round",
                "parent_code_file_name",
                "pipeline_valid",
                "pipeline_valid_reason",
                "pipeline_valid_round",
                "introspection_history",
                ]
        metadata = {
                "code_file_name": code_file_name,
                }
        for key in metadata_keys:
            if key in code_file_dict:
                metadata[key] = code_file_dict[key]
        return metadata

    def attach_program_metadata(result_entry, code_file_name):
        existing_pipeline_valid = None
        if code_file_name in programs_dict and isinstance(programs_dict[code_file_name], dict):
            existing_pipeline_valid = programs_dict[code_file_name].get("pipeline_valid")
        if existing_pipeline_valid is None:
            set_pipeline_validity(
                    code_file_name,
                    False,
                    reason = "pipeline_final_output_unvalidated",
                    round_id = None,
                    )
        metadata = build_program_metadata(code_file_name)
        ensure_flow_node(
                code_file_name,
                details = {
                    "analogy": metadata.get("analogy"),
                    "reason": metadata.get("reason"),
                    "rule": metadata.get("rule"),
                    "objects": metadata.get("objects"),
                    "explanation": metadata.get("explanation"),
                    "code_reasoning": metadata.get("code reasoning"),
                    }
                )
        result_entry["program_metadata"] = metadata
        result_entry["pipeline_valid"] = metadata.get("pipeline_valid", False)
        result_entry["pipeline_valid_reason"] = metadata.get("pipeline_valid_reason")
        result_entry["pipeline_valid_round"] = metadata.get("pipeline_valid_round")
        for source_key, result_key in [
                ("analogy", "analogy"),
                ("reason", "reason"),
                ("rule", "rule"),
                ("objects", "objects"),
                ("explanation", "explanation"),
                ("code reasoning", "code_reasoning"),
                ("created_by", "created_by"),
                ("created_round", "created_round"),
                ("parent_code_file_name", "parent_code_file_name"),
                ("mutation rate", "mutation_rate"),
                ("small mutation rate", "small_mutation_rate"),
                ("former correct rate", "former_correct_rate"),
                ("pipeline_valid", "pipeline_valid"),
                ("pipeline_valid_reason", "pipeline_valid_reason"),
                ("pipeline_valid_round", "pipeline_valid_round"),
                ("introspection_history", "introspection_history"),
                ]:
            if source_key in metadata:
                result_entry[result_key] = metadata[source_key]
        correct_num = result_entry.get("correct_num")
        all_num = result_entry.get("all_num")
        if correct_num is not None and all_num is not None:
            if result_entry.get("is_correct"):
                correctness_status = "correct"
            elif result_entry.get("is_partially_correct"):
                correctness_status = "partial"
            else:
                correctness_status = "wrong"
            code_id = ensure_flow_node(code_file_name)
            if code_id is not None:
                pipeline_flow["nodes"][code_id]["correctness"] = {
                        "status": correctness_status,
                        "correct_num": correct_num,
                        "all_num": all_num,
                        "correct_tests": result_entry.get("correct_tests", []),
                        }
        return result_entry

    result_programs_dict = {}
    all_exs_num = len(ques)
    if all_solved_code_filename:
        print("Start final test!")
        logging.info("Start final test!")
        result_programs_dict['example_all_correct'] = True
        for right_code_file_name in all_solved_code_filename:
            right_exs_num = 0
            # execute code
            result_programs_dict[right_code_file_name] = {}
            print(f"-------Start computing result of {right_code_file_name}--------")
            output_grid_list = []
            # compute all of the examples
            for exs_input_sig in range(len(ques)):
                input_json = json.dumps(ques[exs_input_sig])

                process = subprocess.Popen(
                        ['python3', right_code_file_name],
                        stdin = subprocess.PIPE,
                        stdout = subprocess.PIPE,
                        stderr = subprocess.PIPE,
                        text = True
                    )
                stdout, stderr = communicate_code_process(process, input_json, right_code_file_name)
                if process.returncode != 0:
                    error_signal = True
                    error_message = stderr
                    break
                else:
                    error_signal = False
                    error_message = ""

                try:
                    output_json = json.loads(stdout)
                    if output_json == None:
                        error_signal = True
                        error_message = "The output grid is None, which is not valid!"
                        break
                except:
                    error_signal = True
                    error_message = "The output of the function execute() can not be parsed correctly."
                    break
                if len(output_json) == 1:
                    output_json = output_json[0]
                output_grid_list.append(output_json)

            correct_tests = []
            for answer_grid_sig in range(len(output_grid_list)):
                if output_grid_list[answer_grid_sig] == ans[answer_grid_sig]:
                    right_exs_num += 1
                    correct_tests.append(answer_grid_sig)
            if right_exs_num == all_exs_num:
                print(f"All questions are solved on {ex_name}, by {right_code_file_name}!")
            result_programs_dict[right_code_file_name]['result'] = output_grid_list
            result_programs_dict[right_code_file_name]['all_num'] = all_exs_num
            result_programs_dict[right_code_file_name]['correct_num'] = right_exs_num
            result_programs_dict[right_code_file_name]['correct_tests'] = correct_tests
            result_programs_dict[right_code_file_name]['per_test_results'] = build_per_test_results(output_grid_list, ans)
            result_programs_dict[right_code_file_name]['is_correct'] = right_exs_num == all_exs_num
            result_programs_dict[right_code_file_name]['is_partially_correct'] = 0 < right_exs_num < all_exs_num
            attach_program_metadata(result_programs_dict[right_code_file_name], right_code_file_name)
            save_pipeline_visualization(
                    exs, example_result_dict[right_code_file_name], ques, output_grid_list,
                    0, right_code_file_name, temp = False, cot = False
                    )

    else:
        result_programs_dict['example_all_correct'] = False
        # Judge examples output
        print("Start final judging code outputs!")
        # metrics between code output and ground truth
        difference_grids_dict = {}
        best_correct_rate = 0
        best_file_name = None
        best_file_name_list = []
        best_reason = ""
        best_analogy = ""

        for judge_code_file_name, judge_code_result_dict in programs_dict.items():
            if judge_code_file_name == 'circulate times':
                continue
            if judge_code_result_dict == None:
                continue
            if judge_code_result_dict['error_signal']:
                continue
            difference_one_program_dict = {}
            judge_code_result_grid = example_result_dict[judge_code_file_name]
            difference_grids, grids_coor_list, correct_rate = metrics_code_grid(judge_code_result_dict, judge_code_result_grid, exs, judge_mask_exs)
            difference_one_program_dict['grids'] = difference_grids
            difference_one_program_dict['coordinates'] = grids_coor_list
            difference_one_program_dict['correct_rate'] = correct_rate
            difference_grids_dict[judge_code_file_name] = difference_one_program_dict
            if correct_rate > best_correct_rate:
                best_correct_rate = correct_rate
                best_file_name = judge_code_file_name
                best_file_name_list = []
            elif correct_rate == best_correct_rate:
                best_file_name_list.append(judge_code_file_name)
                best_file_name_list.append(best_file_name)
            output_grid_list = []
            # compute all of the questions
            for exs_input_sig in range(len(ques)):
                input_json = json.dumps(ques[exs_input_sig])

                process = subprocess.Popen(
                        ['python3', judge_code_file_name],
                        stdin = subprocess.PIPE,
                        stdout = subprocess.PIPE,
                        stderr = subprocess.PIPE,
                        text = True
                    )
                stdout, stderr = communicate_code_process(process, input_json, judge_code_file_name)
                if process.returncode != 0:
                    error_signal = True
                    error_message = stderr
                    break
                else:
                    error_signal = False
                    error_message = ""

                try:
                    output_json = json.loads(stdout)
                    if output_json == None:
                        error_signal = True
                        error_message = "The output grid is None, which is not valid!"
                        break
                except:
                    error_signal = True
                    error_message = "The output of the function execute() can not be parsed correctly."
                    break
                if len(output_json) == 1:
                    output_json = output_json[0]
                output_grid_list.append(output_json)
        # execute code
        if len(best_file_name_list) == 0:
            best_file_name_list.append(best_file_name)
        for code_file_name in best_file_name_list:
            result_programs_dict[code_file_name] = {}
            print(f"-------Start computing result of {code_file_name}--------")
            right_exs_num = 0
            output_grid_list = []
            # compute all of the examples
            for exs_input_sig in range(len(ques)):
                input_json = json.dumps(ques[exs_input_sig])

                process = subprocess.Popen(
                        ['python3', code_file_name],
                        stdin = subprocess.PIPE,
                        stdout = subprocess.PIPE,
                        stderr = subprocess.PIPE,
                        text = True
                    )
                stdout, stderr = communicate_code_process(process, input_json, code_file_name)
                if process.returncode != 0:
                    error_signal = True
                    error_message = stderr
                    break
                else:
                    error_signal = False
                    error_message = ""

                try:
                    output_json = json.loads(stdout)
                    if output_json == None:
                        error_signal = True
                        error_message = "The output grid is None, which is not valid!"
                        break
                except:
                    error_signal = True
                    error_message = "The output of the function execute() can not be parsed correctly."
                    break
                if len(output_json) == 1:
                    output_json = output_json[0]
                output_grid_list.append(output_json)

            correct_tests = []
            for answer_grid_sig in range(len(output_grid_list)):
                if output_grid_list[answer_grid_sig] == ans[answer_grid_sig]:
                    right_exs_num += 1
                    correct_tests.append(answer_grid_sig)
            if right_exs_num == all_exs_num:
                print(f"All questions are solved on {ex_name}, by {code_file_name}!")
            result_programs_dict[code_file_name]['result'] = output_grid_list
            result_programs_dict[code_file_name]['all_num'] = all_exs_num
            result_programs_dict[code_file_name]['correct_num'] = right_exs_num
            result_programs_dict[code_file_name]['correct_tests'] = correct_tests
            result_programs_dict[code_file_name]['per_test_results'] = build_per_test_results(output_grid_list, ans)
            result_programs_dict[code_file_name]['is_correct'] = right_exs_num == all_exs_num
            result_programs_dict[code_file_name]['is_partially_correct'] = 0 < right_exs_num < all_exs_num
            attach_program_metadata(result_programs_dict[code_file_name], code_file_name)
            save_pipeline_visualization(
                    exs, example_result_dict[code_file_name], ques, output_grid_list,
                    0, code_file_name, temp = False, cot = False
                    )

    pipeline_correctness = summarize_pipeline_correctness(result_programs_dict, all_exs_num)
    pipeline_valid_correctness = summarize_pipeline_valid_correctness(result_programs_dict)
    result_programs_dict["program_metadata"] = {
            code_file_name: build_program_metadata(code_file_name)
            for code_file_name, code_file_dict in programs_dict.items()
            if code_file_name != 'circulate times' and isinstance(code_file_dict, dict)
            }
    result_programs_dict["selected_program_metadata"] = {
            code_file_name: result_programs_dict["program_metadata"].get(code_file_name, {})
            for code_file_name in pipeline_correctness["evaluated_programs"]
            }
    result_programs_dict["pipeline_correctness"] = pipeline_correctness
    result_programs_dict["pipeline_valid_correctness"] = pipeline_valid_correctness
    pipeline_flow["pipeline_valid_correctness"] = pipeline_valid_correctness
    result_programs_dict["task_correct"] = pipeline_correctness["task_correct"]
    result_programs_dict["task_partially_correct"] = pipeline_correctness["task_partially_correct"]
    result_programs_dict["best_program"] = pipeline_correctness["best_program"]
    result_programs_dict["best_correct_num"] = pipeline_correctness["best_correct_num"]
    result_programs_dict["all_num"] = pipeline_correctness["all_num"]
    result_programs_dict["best_correct_rate"] = pipeline_correctness["best_correct_rate"]
    result_programs_dict["best_correct_tests"] = pipeline_correctness["best_correct_tests"]
    result_programs_dict["per_test_results"] = pipeline_correctness["best_per_test_results"]
    correctness_label = "correct" if pipeline_correctness["task_correct"] else "partially correct" if pipeline_correctness["task_partially_correct"] else "wrong"
    correctness_message = (
            f"Pipeline result for {ex_name}: {correctness_label} "
            f"({pipeline_correctness['best_correct_num']}/{pipeline_correctness['all_num']} tests correct"
            f", best_program={pipeline_correctness['best_program']})"
            )
    print(correctness_message)
    logging.info(correctness_message)
    finish_test_one_file(result_programs_dict)

def test_recog_one_file(recog_prompt, exs_url, mc, exs):
    temp_sig = 0
    client = openai.OpenAI()
    finished = False
    VL_messages = [
                    {
                        "role": "user",
                        "content": [{
                            "type":"text", 
                            "text":recog_prompt
                            },
                        {
                            "type":"text", 
                            "text":"The visualization of examples are shown below:"
                            },
                        {
                            "type": "image_url", 
                            "image_url": {"url": exs_url}
                            },
                        {
                            "type":"text", 
                            "text":"The matrix of examples are shown below:"
                            },
                        {
                            "type":"text", 
                            "text":str(exs)
                            },
                        ]
                    },
                ]
    while True:
        try:
            response = client.chat.completions.create(
                    model = mc,
                    messages = VL_messages
                    )
            finished = True
        except Exception as e:
            print(e)
            temp_sig += 1
            finished = False
        if finished:
            break
        if temp_sig > 2:
            return None

    return response.choices[0].message.content

def coding_target(answer_dict: dict, is_reflect: int, mc: str, exs: dict, exs_url) -> dict:
    client = openai.OpenAI()
    if not isinstance(answer_dict, dict):
        logging.info(f"Coding target failed: answer_dict is not a dict: {answer_dict}")
        return None
    target = answer_dict.get('Analogy') or answer_dict.get('analogy') or answer_dict.get('target') or answer_dict.get('Target')
    reason = answer_dict.get('Reason') or answer_dict.get('reason') or answer_dict.get('rule') or answer_dict.get('Rule')
    rule = answer_dict.get('Rule') or answer_dict.get('rule') or ""
    objects = answer_dict.get('Objects') or answer_dict.get('objects') or []
    used_expansion_concepts = answer_dict.get('Used_expansion_concepts') or answer_dict.get('used_expansion_concepts') or []
    used_quantitative_mechanisms = answer_dict.get('Used_quantitative_mechanisms') or answer_dict.get('used_quantitative_mechanisms') or []
    implementation_notes = answer_dict.get('Implementation_notes') or answer_dict.get('implementation_notes') or []
    speculative_warnings = answer_dict.get('Speculative_warnings') or answer_dict.get('speculative_warnings') or []
    if not isinstance(target, str) or not target.strip():
        logging.info(f"Coding target failed: missing analogy target in {answer_dict}")
        return None
    if not isinstance(reason, str) or not reason.strip():
        reason = "No explicit reason was provided."
    target = target.strip()
    reason = reason.strip()
    if isinstance(rule, str):
        rule = rule.strip()
    else:
        rule = ""
    if not isinstance(objects, list):
        objects = []
    if not isinstance(used_expansion_concepts, list):
        used_expansion_concepts = []
    if not isinstance(used_quantitative_mechanisms, list):
        used_quantitative_mechanisms = []
    if not isinstance(implementation_notes, list):
        implementation_notes = []
    if not isinstance(speculative_warnings, list):
        speculative_warnings = []
    VL_messages = [
            {
                "role": "system",
                "content": "You are an expert Python programmer. Always think step by step before writing code. Follow the exact format requested: REASONING, CODE, EXPLANATION."
                },
            {
                "role": "user",
                "content": [{
                        "type":"text", 
                        "text":code_prompt
                        },
                    {
                        "type":"text", 
                        "text":"The visualization of examples are shown below:"
                        },
                    {
                        "type":"image_url", 
                        "image_url": {"url": exs_url}
                        },
                    {
                        "type":"text", 
                        "text":"The matrix of examples are shown below:"
                        },
                    {
                        "type":"text", 
                        "text":str(exs)
                        },
                    {
                        "type": "text", 
                        "text": format_analogy_context({
                            "Analogy": target,
                            "Reason": reason,
                            "Rule": rule,
                            "Objects": objects,
                            "Used_expansion_concepts": used_expansion_concepts,
                            "Used_quantitative_mechanisms": used_quantitative_mechanisms,
                            "Implementation_notes": implementation_notes,
                            "Speculative_warnings": speculative_warnings,
                            }, "The deductive analogy context is provided as below")
                        }
                    ]
                }
            ]

    finished = False
    temp_sig = 0
    while True:
        try:
            response = client.chat.completions.create(
                    model = mc,
                    messages = VL_messages
                    )
            provider_error_message = extract_provider_error_message(response)
            if provider_error_message:
                print(f"Coding target provider error for {target}: {provider_error_message}")
                logging.info(f"Coding target provider error for {target}: {provider_error_message}. Response: {response}")
                temp_sig += 1
                finished = False
            else:
                finished = True
        except Exception as e:
            print(e)
            temp_sig += 1
            finished = False
        if finished:
            break
        if temp_sig > 2:
            logging.info(f"Coding target failed for {target}: provider/API retry limit exceeded.")
            print(f"Coding target failed for {target}: provider/API retry limit exceeded.")
            return None

    try:
        choices = getattr(response, "choices", None)
        if not choices:
            logging.info(f"Coding target failed for {target}: response has no choices. Response: {response}")
            print(f"Coding target failed for {target}: response has no choices.")
            return None
        message = getattr(choices[0], "message", None)
        full_response = getattr(message, "content", None)
    except Exception as e:
        logging.info(f"Coding target failed for {target}: unable to read response content: {e}. Response: {response}")
        print(f"Coding target failed for {target}: unable to read response content: {e}")
        return None
    if not isinstance(full_response, str) or not full_response.strip():
        provider_error_message = extract_provider_error_message(response)
        if provider_error_message:
            logging.info(f"Coding target failed for {target}: provider error after retry: {provider_error_message}. Response: {response}")
            print(f"Coding target failed for {target}: provider error after retry: {provider_error_message}")
        else:
            logging.info(f"Coding target failed for {target}: empty response content. Response: {response}")
            print(f"Coding target failed for {target}: empty response content.")
        return None
    logging.info(full_response)
    reasoning = extract_section(full_response, "REASONING:")
    code = extract_section(full_response, "CODE:")
    explanation = extract_section(full_response, "EXPLANATION:")
    if not isinstance(code, str) or not code.strip():
        logging.info(f"Coding target failed for {target}: CODE section missing. Full response: {full_response}")
        print(f"Coding target failed for {target}: CODE section missing.")
        return None

    code = clean_code(code)
    if not code.strip():
        logging.info(f"Coding target failed for {target}: CODE section is empty after cleaning. Full response: {full_response}")
        print(f"Coding target failed for {target}: CODE section is empty after cleaning.")
        return None
    is_safe, safe_message = is_safe_code(code)
    if not is_safe:
        print(f"\n Warning: {safe_message}")
        logging.info(f"Coding target warning for {target}: {safe_message}")
    return {
            'analogy': target,
            'reason': reason,
            'rule': rule,
            'objects': objects,
            'used_expansion_concepts': used_expansion_concepts,
            'used_quantitative_mechanisms': used_quantitative_mechanisms,
            'implementation_notes': implementation_notes,
            'speculative_warnings': speculative_warnings,
            'code reasoning': reasoning,
            'explanation': explanation,
            'code': code
        }

def rectify_code_file(programs_dict: dict, mc: dict) -> str:
    client = openai.OpenAI()
    L_messages = [
            {
                "role": "system",
                "content": "You are an expert Python programmer. Always think step by step before writing code. Follow the exact format requested: REASONING, CODE, EXPLANATION."
                },
            {
                "role": "user",
                "content": [{
                    "type":"text", 
                    "text":rectify_code_prompt
                        },
                    {
                        "type":"text", 
                        "text":"The code is shown below:"
                        },
                    {
                        "type": "text", 
                        "text": programs_dict['code']
                        },
                    {
                        "type": "text", 
                        "text": "The error messages are shown below:"
                        },
                    {
                        "type": "text", 
                        "text": programs_dict['error_message']
                        }
                    ]
                }
            ]

    finished = False
    temp_sig = 0
    while True:
        try:
            response = client.chat.completions.create(
                    model = mc,
                    messages = L_messages
                    )
            finished = True
        except Exception as e:
            print(e)
            temp_sig += 1
            finished = False
        if finished:
            break
        if temp_sig > 4:
            return None

    full_response = response.choices[0].message.content
    logging.info(full_response)
    reasoning = extract_section(full_response, "REASONING:")
    code = extract_section(full_response, "CODE:")
    explanation = extract_section(full_response, "EXPLANATION:")

    code = clean_code(code)
    is_safe, safe_message = is_safe_code(code)
    if not is_safe:
        print(f"\n Warning: {safe_message}")

    return code

def question_one_program(question_prompt_content: list, mc: str) -> str:
    client = openai.OpenAI()
    VL_messages = [
                {
                    "role": "system", 
                    "content": "You are a helpful assistant and an expert Python programmer. Always think step by step before writing code. Follow the exact format requested: REASONING, INSTRUCTIONS."
                    },
                {
                    "role": "user", 
                    "content": question_prompt_content
                    }
                ]
    finished = False
    temp_sig = 0
    while True:
        try:
            response = client.chat.completions.create(
                    model = mc,
                    messages = VL_messages
                    )
            finished = True
            full_response = response.choices[0].message.content
        except Exception as e:
            print(e)
            temp_sig += 1
            finished = False
        if finished:
            break
        if temp_sig > 2:
            return None
    logging.info(full_response)
    reasoning = extract_section(full_response, "REASONING:")
    instructions = extract_section(full_response, "INSTRUCTIONS:")
    return reasoning, instructions

def modify_one_program(code_prompt_content: list, mc: str) -> str:
    client = openai.OpenAI()
    VL_messages = [
                {
                    "role": "system", 
                    "content": "You are a helpful assistant and an expert Python programmer. Always think step by step before writing code. Follow the exact format requested: REASONING, CODE, EXPLANATION."
                    },
                {
                    "role": "user", 
                    "content": code_prompt_content
                    }
                ]
    finished = False
    temp_sig = 0
    while True:
        try:
            response = client.chat.completions.create(
                    model = mc,
                    messages = VL_messages
                    )
            finished = True
            full_response = response.choices[0].message.content
        except Exception as e:
            print(e)
            temp_sig += 1
            finished = False
        if finished:
            break
        if temp_sig > 2:
            return None


    return full_response

def crossover_two_programs(crossover_prompt_content: list, mc: str) -> str:
    client = openai.OpenAI()
    VL_messages = [
                {
                    "role": "system", 
                    "content": "You are a helpful assistant and an expert Python programmer. Always think step by step before writing code. Follow the exact format requested: REASONING, INSTRUCTIONS."
                    },
                {
                    "role": "user", 
                    "content": crossover_prompt_content
                    }
                ]
    finished = False
    temp_sig = 0
    while True:
        try:
            response = client.chat.completions.create(
                    model = mc,
                    messages = VL_messages
                    )
            finished = True
        except Exception as e:
            print(e)
            temp_sig += 1
            finished = False
        if finished:
            break
        if temp_sig > 2:
            return None
    full_response = response.choices[0].message.content
    return full_response

def mutate_code_file(mutate_analogy_content: list, mutate_code_content: list, mc: str, analogy_mc: str = None) -> dict:
    com_generate = mutate_analogy(mutate_analogy_content, analogy_mc or mc)
    if com_generate == None:
        print(f"Mutate analogy failed!")
        logging.info("Mutate analogy failed!")
        return None
    else:
        logging.info("Mutate analogy successed!")
        logging.info(com_generate)
    analogy_target_dict = parse_single_analogy_target_response(com_generate)
    if analogy_target_dict is None:
        print(f"Parsing mutate analogy failed!")
        logging.info("Parsing mutate analogy failed.")
        return None
    mutate_code_file_dict = mutate_code(mutate_code_content, analogy_target_dict, mc)
    if mutate_code_file_dict == None:
        print(f"Mutate code failed!")
        logging.info("Mutate code failed!")
        return None

    return mutate_code_file_dict

def mutate_analogy(mutate_analogy_content: list, mc: str) -> str:
    temp_sig = 0
    client = openai.OpenAI()
    finished = False
    VL_messages = [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that is good at picture assoiciation and ARC Test. Always think before answering." 
                        },
                    {
                        "role": "user",
                        "content": mutate_analogy_content
                        }
                ]
    while True:
        try:
            response = client.chat.completions.create(
                    model = mc,
                    messages = VL_messages
                    )
            finished = True
        except Exception as e:
            print(e)
            temp_sig += 1
            finished = False
        if finished:
            break
        if temp_sig > 4:
            return None

    return response.choices[0].message.content

def mutate_code(mutate_code_content: list, analogy_target_dict: dict, mc: str) -> dict:
    logging.info("Start mutating code.")
    analogy_context = normalize_pipeline_analogy_context(analogy_target_dict)
    target = analogy_context['Analogy']
    reason = analogy_context['Reason']
    rule = analogy_context['Rule']
    objects = analogy_context['Objects']
    used_expansion_concepts = analogy_context.get('Used_expansion_concepts', [])
    used_quantitative_mechanisms = analogy_context.get('Used_quantitative_mechanisms', [])
    implementation_notes = analogy_context.get('Implementation_notes', [])
    speculative_warnings = analogy_context.get('Speculative_warnings', [])
    if not target:
        logging.info(f"Mutate code failed: missing analogy target in {analogy_target_dict}")
        return None
    mutate_code_content.append({
            "type": "text",
            "text": format_analogy_context(analogy_context, "The deductive analogy context is below")
        })
    client = openai.OpenAI()
    VL_messages = [
            {
                "role": "system",
                "content": "You are an expert Python programmer. Always think step by step before writing code. Follow the exact format requested: REASONING, CODE, EXPLANATION."
                },
            {
                "role": "user",
                "content": mutate_code_content
                }
            ]

    finished = False
    temp_sig = 0
    while True:
        try:
            response = client.chat.completions.create(
                    model = mc,
                    messages = VL_messages
                    )
            finished = True
        except Exception as e:
            print(e)
            temp_sig += 1
            finished = False
        if finished:
            break
        if temp_sig > 4:
            return None

    full_response = response.choices[0].message.content
    logging.info(full_response)
    reasoning = extract_section(full_response, "REASONING:")
    code = extract_section(full_response, "CODE:")
    explanation = extract_section(full_response, "EXPLANATION:")

    code = clean_code(code)
    is_safe, safe_message = is_safe_code(code)
    if not is_safe:
        print(f"\n Warning: {safe_message}")
    return {
            'analogy': target,
            'reason': reason,
            'rule': rule,
            'objects': objects,
            'used_expansion_concepts': used_expansion_concepts,
            'used_quantitative_mechanisms': used_quantitative_mechanisms,
            'implementation_notes': implementation_notes,
            'speculative_warnings': speculative_warnings,
            'code reasoning': reasoning,
            'explanation': explanation,
            'code': code
        }

def finding_abnormal_from_result(abnormal_prompt_content: list, mc: str) -> str:
    client = openai.OpenAI()
    VL_messages = [
                {
                    "role": "system", 
                    "content": "You are a helpful assistant who is good at image association and an expert Python programmer. Please provide the instructions about how to improve the code. Follow the exact format requested: REASONING, INSTRUCTIONS."
                    },
                {
                    "role": "user", 
                    "content": abnormal_prompt_content
                    }
                ]
    finished = False
    temp_sig = 0
    while True:
        try:
            response = client.chat.completions.create(
                    model = mc,
                    messages = VL_messages
                    )
            finished = True
        except Exception as e:
            print(e)
            temp_sig += 1
            finished = False
        if finished:
            break
        if temp_sig > 2:
            return None
    full_response = response.choices[0].message.content
    return full_response

def augmentation_analogy(small_mutation_prompt_content: list, mc: str) -> str:
    client = openai.OpenAI()
    VL_messages = [
                {
                    "role": "system", 
                    "content": "You are a helpful assistant who is good at image association and an expert Python programmer. Follow the exact format requested: REASONING, ANALOGY, PROPOSALS."
                    },
                {
                    "role": "user", 
                    "content": small_mutation_prompt_content
                    }
                ]
    finished = False
    temp_sig = 0
    while True:
        try:
            response = client.chat.completions.create(
                    model = mc,
                    messages = VL_messages
                    )
            finished = True
        except Exception as e:
            print(e)
            temp_sig += 1
            finished = False
        if finished:
            break
        if temp_sig > 2:
            return None
    full_response = response.choices[0].message.content
    return full_response

def get_breaking_instruction(breaking_prompt_content: list, mc: str):
    client = openai.OpenAI()
    VL_messages = [
                {
                    "role": "system", 
                    "content": "You are a helpful assistant who is good at image association. Follow the exact format requested: REASONING, PROPOSALS."
                    },
                {
                    "role": "user", 
                    "content": breaking_prompt_content
                    }
                ]

    finished = False
    temp_sig = 0
    while True:
        try:
            response = client.chat.completions.create(
                    model = mc,
                    messages = VL_messages
                    )
            finished = True
        except Exception as e:
            print(e)
            temp_sig += 1
            finished = False
        if finished:
            break
        if temp_sig > 2:
            logging.info("Judging failed!")
            return False, None, {
                    "parse_success": False,
                    "error": "api_call_failed",
                    }
    full_response = response.choices[0].message.content
    if not isinstance(full_response, str) or not full_response.strip():
        logging.info("Judging returned empty response content.")
        return False, None, {
                "parse_success": False,
                "error": "empty_response",
                }
    logging.info(full_response)
    reasoning = extract_section(full_response, "REASONING:")
    prop = extract_section(full_response, "PROPOSALS:")
    prop_dict = parse_answer(prop, is_format = "final")
    if prop_dict is None:
        return False, None, {
                "parse_success": False,
                "error": "proposal_parse_failed",
                "reasoning": reasoning,
                }
    audit_details = {
            "parse_success": True,
            "reasoning": reasoning,
            "blocking_issues": prop_dict.get("blocking_issues", []),
            "contract_audit": prop_dict.get("contract_audit", []),
            "question_stress_test": prop_dict.get("question_stress_test", []),
            "component_traces": prop_dict.get("component_traces", []),
            "overlapping_operations": prop_dict.get("overlapping_operations", []),
            "counterfactual_checks": prop_dict.get("counterfactual_checks", []),
            }
    if prop_dict['judge'] == "True":
        if audit_details["blocking_issues"]:
            audit_details["format_consistent"] = False
            return False, (
                    prop_dict['instruct']
                    or "Resolve the blocking issues reported by introspection before accepting the code."
                    ), audit_details
        audit_details["format_consistent"] = True
        return True, prop_dict['instruct'], audit_details
    else:
        audit_details["format_consistent"] = bool(audit_details["blocking_issues"])
        return False, prop_dict['instruct'], audit_details

def final_rectify(final_rectify_prompt_content: list, mc: str) -> str:
    client = openai.OpenAI()
    VL_messages = [
                {
                    "role": "system", 
                    "content": "You are a helpful assistant and an expert Python programmer. Always think step by step before writing code. Follow the exact format requested: REASONING, CODE, EXPLANATION."
                    },
                {
                    "role": "user", 
                    "content": final_rectify_prompt_content
                    }
                ]
    finished = False
    temp_sig = 0
    while True:
        try:
            response = client.chat.completions.create(
                    model = mc,
                    messages = VL_messages
                    )
            finished = True
        except Exception as e:
            print(e)
            temp_sig += 1
            finished = False
        if finished:
            break
        if temp_sig > 2:
            return None

    full_response = response.choices[0].message.content

    return full_response
