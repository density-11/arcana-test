"""Parsing and comparison helpers for the direct-grid challenger."""

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


def _is_grid(value):
    if not isinstance(value, list) or not value:
        return False
    if not all(isinstance(row, list) and row for row in value):
        return False
    width = len(value[0])
    for row in value:
        if len(row) != width:
            return False
        for cell in row:
            if not isinstance(cell, int) or cell < 0 or cell > 9:
                return False
    return True


def _same_shape(grid, reference):
    return (
        _is_grid(grid)
        and isinstance(reference, list)
        and len(grid) == len(reference)
        and (not grid or len(grid[0]) == len(reference[0]))
    )


def _prediction_list(parsed, keys):
    if not isinstance(parsed, dict):
        return []
    for key in keys:
        value = parsed.get(key)
        if isinstance(value, list):
            return value
    return []


def _first_value(obj, keys, default=None):
    if not isinstance(obj, dict):
        return default
    for key in keys:
        if key in obj:
            return obj.get(key)
    return default


def _string_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _jsonable_value(value, default):
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    return default


def _normalize_prediction_items(items, count):
    normalized = [None for _ in range(count)]
    for seq_index, item in enumerate(items):
        if isinstance(item, dict):
            raw_index = item.get("index", item.get("Index", seq_index))
            output = _first_value(item, ["output", "Output", "output_grid", "Output_grid", "grid", "Grid"])
            confidence = item.get("confidence", item.get("Confidence", ""))
            reason = item.get("reason", item.get("Reason", ""))
            check = item.get("check", item.get("Check", ""))
        else:
            raw_index = seq_index
            output = item
            confidence = ""
            reason = ""
            check = ""
        try:
            index = int(raw_index)
        except Exception:
            index = seq_index
        if 0 <= index < count:
            normalized[index] = {
                "index": index,
                "output": output,
                "confidence": str(confidence or ""),
                "reason": str(reason or ""),
                "check": str(check or ""),
            }
    return normalized


def parse_direct_grid_prediction_response(response, exs, ques):
    parsed = _extract_json_like_object(response)
    if not isinstance(parsed, dict):
        return {
            "parse_success": False,
            "error_message": "response is not a JSON object",
        }
    example_predictions = _normalize_prediction_items(
        _prediction_list(parsed, ["Example_predictions", "example_predictions", "Examples", "examples"]),
        len(exs),
    )
    question_predictions = _normalize_prediction_items(
        _prediction_list(parsed, ["Question_predictions", "question_predictions", "Test_predictions", "test_predictions", "Questions", "questions"]),
        len(ques),
    )
    valid_examples = []
    correct_examples = []
    for index, prediction in enumerate(example_predictions):
        if prediction is None:
            continue
        output = prediction.get("output")
        if not _same_shape(output, exs[index][1]):
            prediction["valid_shape"] = False
            continue
        prediction["valid_shape"] = True
        valid_examples.append(index)
        if output == exs[index][1]:
            correct_examples.append(index)
    valid_questions = []
    for index, prediction in enumerate(question_predictions):
        if prediction is None:
            continue
        output = prediction.get("output")
        valid_shape = _same_shape(output, ques[index])
        prediction["valid_shape"] = valid_shape
        if valid_shape:
            valid_questions.append(index)
    example_all_num = len(exs)
    question_all_num = len(ques)
    return {
        "parse_success": True,
        "rule_summary": str(parsed.get("Rule_summary", parsed.get("rule_summary", "")) or ""),
        "mechanism_spec": _jsonable_value(_first_value(parsed, ["Mechanism_spec", "mechanism_spec"], {}), {}),
        "example_traces": _jsonable_value(_first_value(parsed, ["Example_traces", "example_traces"], []), []),
        "rejected_shortcuts": _string_list(_first_value(parsed, ["Rejected_shortcuts", "rejected_shortcuts"])),
        "test_trace": _jsonable_value(_first_value(parsed, ["Test_trace", "test_trace"], {}), {}),
        "key_observations": _string_list(_first_value(parsed, ["Key_observations", "key_observations", "Observations", "observations"])),
        "invariants": _string_list(_first_value(parsed, ["Invariants", "invariants"])),
        "transformation_steps": _string_list(_first_value(parsed, ["Transformation_steps", "transformation_steps", "Steps", "steps"])),
        "uncertainty": str(_first_value(parsed, ["Uncertainty", "uncertainty"], "") or ""),
        "example_predictions": example_predictions,
        "question_predictions": question_predictions,
        "example_pred_corr_num": len(correct_examples),
        "example_pred_all_num": example_all_num,
        "example_pred_all_correct": example_all_num > 0 and len(correct_examples) == example_all_num,
        "correct_examples": correct_examples,
        "valid_examples": valid_examples,
        "question_pred_all_num": question_all_num,
        "valid_questions": valid_questions,
        "question_pred_all_valid": question_all_num > 0 and len(valid_questions) == question_all_num,
    }


def compare_direct_and_code_outputs(direct_prediction, code_question_outputs):
    if not isinstance(direct_prediction, dict) or not direct_prediction.get("parse_success"):
        return {
            "code_question_match": False,
            "matched_questions": [],
            "mismatched_questions": [],
            "comparison_available": False,
        }
    question_predictions = direct_prediction.get("question_predictions") or []
    matched = []
    mismatched = []
    for index, prediction in enumerate(question_predictions):
        if prediction is None or not prediction.get("valid_shape"):
            mismatched.append(index)
            continue
        if index >= len(code_question_outputs):
            mismatched.append(index)
            continue
        if prediction.get("output") == code_question_outputs[index]:
            matched.append(index)
        else:
            mismatched.append(index)
    total = len(question_predictions)
    available = total > 0 and len(code_question_outputs) >= total
    return {
        "code_question_match": available and len(mismatched) == 0,
        "matched_questions": matched,
        "mismatched_questions": mismatched,
        "comparison_available": available,
    }


def parse_direct_grid_arbitration_response(response):
    parsed = _extract_json_like_object(response)
    if not isinstance(parsed, dict):
        return {
            "parse_success": False,
            "preferred": "uncertain",
            "judgement": "False",
            "instructions": "Direct/code arbitration response could not be parsed.",
        }
    preferred = str(parsed.get("Preferred", parsed.get("preferred", "uncertain")) or "uncertain").strip().lower()
    if preferred not in ["code", "direct", "uncertain"]:
        preferred = "uncertain"
    judgement = str(parsed.get("Judgement", parsed.get("judgement", "False")) or "False").strip()
    instructions = str(parsed.get("Instructions", parsed.get("instructions", "")) or "")
    reason = str(parsed.get("Reason", parsed.get("reason", "")) or "")
    return {
        "parse_success": True,
        "preferred": preferred,
        "judgement": judgement,
        "instructions": instructions,
        "reason": reason,
    }
