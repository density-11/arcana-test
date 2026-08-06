"""Shared data, execution, evaluation, and cost helpers."""

import ast
import json
import os
import re
from typing import Any, Dict, List, Tuple

Grid = List[List[int]]
ExamplePair = Tuple[Grid, Grid]

def _read_task_file(path: str)-> Tuple[List[ExamplePair], List[Grid], List[Grid]]:
    """
    Read a sigle JSON task file and extract:
    - examples: list of (input_grid, out_grid) pair
    - questions: list of test input grids
    - answers: list or test answer/output grids
    """
    with open(path, "r", encoding="utf-8") as f:
        data: Dict[str, Any] = json.load(f)

    examples_raw = data.get("train")
    if examples_raw is None:
        examples_raw = data.get("examples", [])
    examples_raw = examples_raw or []
    examples: List[ExamplePair] = []
    for i, ex in enumerate(examples_raw):
        if not isinstance(ex, dict):
            continue
        inp = ex.get("input")
        out = ex.get("output")
        if inp is None or out is None:
            continue
        examples.append((inp, out))

    questions: List[Grid] = []
    answers: List[Grid] = []
    test = data.get("test")

    def _append_test_case(inp: Any, ans: Any) -> None:
        if inp is None or ans is None:
            return
        questions.append(inp)
        answers.append(ans)

    if isinstance(test, dict):
        test_inp = test.get("input")
        if "answer" in test:
            test_ans = test.get("answer")
        elif "output" in test:
            test_ans = test.get("output")
        _append_test_case(test_inp, test_ans)
    elif isinstance(test, list):
        for t in test:
            if not isinstance(t, dict):
                continue
            test_inp = t.get("input")
            if "answer" in t:
                test_ans = t.get("answer")
            elif "output" in t:
                test_ans = t.get("output")
            _append_test_case(test_inp, test_ans)
            
    return examples, questions, answers

def extract_tagged_json(text: str):
    pattern = r"```json\s*([\s\S]*?)```"
    blocks = re.findall(pattern, text)
    all_re = [b.strip()for b in blocks]
    return json.loads(all_re[0])

def parse_answer(ans: str, is_format: str)->Dict[str, List[Any]]:
    """
    Parse a string into a dict with a single key 'answer' whose value is a list.
    """

    if not isinstance(ans, str) or not ans.strip():
        return None
    ans = ans.strip()
    # ans = ans.replace("\n", "")

    obj: Any = None
    errors: List[Exception] = []

    try:
        #obj = json.loads(ans)
        obj = extract_tagged_json(ans)
    except Exception as e:
        errors.append(e)

    if obj is None:
        try:
            obj = json.loads(ans)
        except Exception as e:
            errors.append(e)

    if obj is None:
        try:
            obj = ast.literal_eval(ans)
        except Exception as e:
            errors.append(e)

    if obj is None:
        err_msgs = "|".join(f"{type(e).__name__}: {e}" for e in errors)
        print(f"Unable to parse input as JSON or python literal. Details: {err_msgs}")
        return None

    if is_format == "answer":
        # Normalize/validate into {"answer": list}
        if isinstance(obj, list):
            answer = obj
        elif isinstance(obj, dict):
            if "answer" not in obj:
                print("Parsed object is a dict but missing the 'answer' key.")
                return None
            answer = obj["answer"]
            if "target" in obj:
                target = obj["target"]
            else:
                target = ""
        else:
            print("Parsed object must be a list or a dict containing the 'answer' key.")
            return None

        if not isinstance(answer, list):
            print("The 'answer value must be a list.'")
            return None

        return {"answer": answer, "target": target}
    elif is_format == "recog":
        # Normalize/validate into {"Analogy_list": list}
        if isinstance(obj, list):
            answer = obj
        elif isinstance(obj, dict):
            if "Analogy_list" not in obj:
                print("Parsed object is a dict but missing the 'Analogy_list' key.")
                return None
            answer = obj["Analogy_list"]
        else:
            print("Parsed object must be a list or a dict containing the 'answer' key.")
            return None

        if not isinstance(answer, list):
            print("The 'answer value must be a list.'")
            return None

        return {"Analogy_list": answer}

    elif is_format == "mutate":
        if isinstance(obj, list):
            answer = obj[0]
        else:
            answer = obj
        if isinstance(answer, dict):
            if "Analogy" not in answer:
                print("Parsed object is a dict but missing the 'Analogy' key.")
                return None
            answer_analogy = answer["Analogy"]
            if "Reason" not in answer:
                print("Parsed object is a dict but missing the 'Reason' key.")
                return None
            answer_reason = answer["Reason"]
            answer_rule = answer.get("Rule", "")
            answer_objects = answer.get("Objects", [])
            return {
                    "analogy": answer_analogy,
                    "reason": answer_reason,
                    "rule": answer_rule,
                    "objects": answer_objects,
                    }
        else:
            print("Parsed object must be a list or a dict containing the 'Analogy', 'Reason', 'Rule' and 'Objects' keys.")
            return None
    elif is_format == "final":
        if isinstance(obj, list):
            answer = obj[0] if obj else None
        else:
            answer = obj
        if isinstance(answer, dict):
            if "Judgement" not in answer:
                print("Parsed object is a dict but missing the 'Judgement' key.")
                return None
            if "Instructions" not in answer:
                print("Parsed object is a dict but missing the 'Instructions' key.")
                return None
            judgement = answer["Judgement"]
            if isinstance(judgement, bool):
                judgement = "True" if judgement else "False"
            elif isinstance(judgement, str):
                normalized_judgement = judgement.strip().lower()
                if normalized_judgement == "true":
                    judgement = "True"
                elif normalized_judgement == "false":
                    judgement = "False"
            if judgement not in ["True", "False"]:
                print("The 'Judgement' value must be True or False.")
                return None
            return {
                    "judge": judgement,
                    "instruct": answer["Instructions"],
                    "blocking_issues": answer.get("Blocking_issues", []),
                    "contract_audit": answer.get("Contract_audit", []),
                    "question_stress_test": answer.get("Question_stress_test", []),
                    "component_traces": answer.get("Component_traces", []),
                    "overlapping_operations": answer.get("Overlapping_operations", []),
                    "counterfactual_checks": answer.get("Counterfactual_checks", []),
                    }
        else:
            print("Parsed object must be a list or a dict containing the 'Judgement' and 'Instructions' key.")
            return None

def calculate_cost(model:str, input_tokens: int, output_tokens: int) -> float:
    price_dict = {
            "openai/gpt-5.2": {"input": 1.75, "output": 14},
            "openai/gpt-5.5": {"input": 5, "output": 30},
            "google/gemini-3.1-pro-preview": {"input": 2, "output": 12},
            "google/gemini-3.5-flash": {"input": 1.5, "output": 9},
            "qwen/qwen3.7-max": {"input": 1.475, "output": 4.425},
            "anthropic/claude-fable-5": {"input": 10, "output": 50},
            "anthropic/claude-opus-4.5": {"input": 5, "output": 25},
            }
    if model not in price_dict:
        return 0
    cost = input_tokens / 1000000 * price_dict[model]["input"] + output_tokens / 1000000 * price_dict[model]["output"]
    return cost

def _normalize_answer_list(m_ans, ans):
    if isinstance(m_ans, dict):
        rt_ans = m_ans.get("answer")
    else:
        rt_ans = m_ans
    if not isinstance(rt_ans, list):
        return []
    if len(ans) == 1:
        if len(rt_ans) == 1 and isinstance(rt_ans[0], list):
            return rt_ans
        return [rt_ans]
    if len(rt_ans) == len(ans):
        return rt_ans
    if len(rt_ans) == 1 and isinstance(rt_ans[0], list) and len(rt_ans[0]) == len(ans):
        return rt_ans[0]
    return rt_ans

def judge_ans_detail(m_ans, ans, path):
    """
    Judge answers per ground-truth test case and return matched test indexes.
    all_num is always the number of ground-truth tests, so multi-test tasks do not
    over-count or under-count when a model returns a malformed answer shape.
    """
    rt_ans = _normalize_answer_list(m_ans, ans)
    corr_num = 0
    correct_tests = []
    for sig, true_ans in enumerate(ans):
        if sig >= len(rt_ans) or not isinstance(rt_ans[sig], list):
            print(f"Output form of test {sig} is not expected! The file is {path}")
            continue
        if true_ans == rt_ans[sig]:
            corr_num += 1
            correct_tests.append(sig)
    return corr_num, len(ans), correct_tests


def build_per_test_results(m_ans, ans):
    """Build additive per-test details without changing the existing judge."""
    rt_ans = _normalize_answer_list(m_ans, ans)
    per_test_results = []
    for test_index, true_ans in enumerate(ans):
        prediction_present = test_index < len(rt_ans)
        prediction_valid = prediction_present and isinstance(rt_ans[test_index], list)
        correct = prediction_valid and rt_ans[test_index] == true_ans
        if correct:
            status = "correct"
        elif not prediction_present:
            status = "missing"
        elif not prediction_valid:
            status = "malformed"
        else:
            status = "wrong"
        per_test_results.append({
                "test_index": test_index,
                "test_number": test_index + 1,
                "correct": correct,
                "status": status,
                "prediction_present": prediction_present,
                "prediction_valid": prediction_valid,
                })
    return per_test_results

def extract_section(text, section_name):
    """Extract certain part of the text"""
    sections = ["REASONING:", "CODE:", "EXPLANATION:", "INSTRUCTIONS:", "ANALOGY:", "PROPOSALS:", "CONFIDENCE:", "ANSWER:"]
    if section_name is None or text is None:
        return ""
    if section_name not in text:
        return ""
    start = text.find(section_name) + len(section_name)

    end = len(text)
    for next_section in sections:
        if next_section in sections:
            if next_section != section_name:
                pos = text.find(next_section, start)
                if pos != -1 and pos < end:
                    end = pos

    return text[start:end].strip()


def parse_confidence(text):
    raw_confidence = extract_section(text, "CONFIDENCE:")
    if not raw_confidence:
        return None, ""
    match = re.search(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(%)?", raw_confidence)
    if match is None:
        return None, raw_confidence
    confidence = float(match.group(1))
    if match.group(2) or confidence > 1:
        confidence /= 100
    if confidence < 0 or confidence > 1:
        return None, raw_confidence
    return confidence, raw_confidence

def clean_code(code):
    code = re.sub(r'^```python\s*\n?', '', code, flags=re.MULTILINE)
    code = re.sub(r'^```\s*\n?', '', code, flags=re.MULTILINE)
    code = re.sub(r'\n?```\s*$', '', code, flags=re.MULTILINE)
    return code.strip()

def is_safe_code(code):
    dangerous_patterns = [
            'os.system', 'subprocess.call', 'eval(', 'exec(', '__import__', 'open(', 'rmdir', 'remove'
            ]
    for pattern in dangerous_patterns:
        if pattern in code:
            return False, f"Find dangerous pattern: {pattern}"
    try:
        ast.parse(code)
        return True, "Code is valid"
    except SyntaxError as e:
        return False, f"Grammar error: {e}"

def get_similarity_mask_batch(exs: list) -> list:
    exs_mask_list = []
    for ex_num_sig in range(len(exs)):
        ex_mask = get_similarity_mask(exs[ex_num_sig][0], exs[ex_num_sig][1])
        exs_mask_list.append(ex_mask)
    return exs_mask_list

def get_similarity_mask(ex_input: list, ex_output: list) -> list:
    if len(ex_input) != len(ex_output):
        raise ValueError("The length of input and output are not equal, which can not use the 'changed' and 'unchanged' metric! The code will change to the other metric strategy. Or please check your example lists.")

    mask = []
    for i in range(len(ex_input)):
        if len(ex_input[i]) != len(ex_output[i]):
            raise ValueError("The length of input and output are not equal, which can not use the 'changed' and 'unchanged' metric! The code will change to the other metric strategy. Or please check your example lists.")

        row_mask = []
        for j in range(len(ex_input[i])):
            if ex_input[i][j] == ex_output[i][j]:
                row_mask.append(1)
            else:
                row_mask.append(0)
        mask.append(row_mask)

    return mask

def metrics_code_grid(j_result_dict: dict, j_result_grid: list, gt_exs: list, gt_mask: list):
    if j_result_dict['error_signal']:
        return None, None, None
    difference_grid_list = []
    coor_list_list = []
    stat_all_grids_num = 0
    stat_wrong_grids_num = 0
    for ex_num_sig in range(len(gt_exs)):
        if gt_mask == None:
            difference_grid, coor_list, wrong_grids_num, all_grids_num = metrics_one_times(j_result_grid[ex_num_sig], gt_exs[ex_num_sig][1], None)
        else:
            difference_grid, coor_list, wrong_grids_num, all_grids_num = metrics_one_times(j_result_grid[ex_num_sig], gt_exs[ex_num_sig][1], gt_mask[ex_num_sig])
        difference_grid_list.append(difference_grid)
        coor_list_list.append(coor_list)
        stat_all_grids_num += all_grids_num
        stat_wrong_grids_num += wrong_grids_num
    correct_rate = 1 - stat_wrong_grids_num / stat_all_grids_num
    return difference_grid_list, coor_list_list, correct_rate

def metrics_one_times(matrix1: list, matrix2: list, mask: list):
    difference_matrix_list = []
    mask_list = []
    diff_coor_list = []

    all_grids_num = len(matrix1) * len(matrix1[0])

    # create masks
    ones_mask = [[1 for _ in row] for row in matrix1]
    mask_list.append(ones_mask)
    if mask != None:
        mask_list.append(mask)
        anti_mask = [[1-_ for _ in row] for row in mask]
        mask_list.append(anti_mask)

    # calculate different mask
    for mask_sig in range(len(mask_list)):
        judge_mask = mask_list[mask_sig]
        difference_one_matrix1 = []
        difference_one_matrix2 = []
        diff_coor_one_list = []
        for i in range(len(matrix1)):
            difference_one_row1 = []
            difference_one_row2 = []
            for j in range(len(matrix1[i])):
                if judge_mask[i][j] == 0:
                    difference_one_row1.append(11)
                    difference_one_row2.append(11)
                elif matrix1[i][j] == matrix2[i][j]:
                    difference_one_row1.append(10)
                    difference_one_row2.append(10)
                else:
                    difference_one_row1.append(matrix1[i][j])
                    difference_one_row2.append(matrix2[i][j])
                    diff_coor_one_list.append((i,j))
            difference_one_matrix1.append(difference_one_row1)
            difference_one_matrix2.append(difference_one_row2)
        diff_coor_list.append(diff_coor_one_list)
        difference_matrix_list.append((difference_one_matrix1, difference_one_matrix2))
    wrong_grids_num = len(diff_coor_list[0])
    return difference_matrix_list, diff_coor_list, wrong_grids_num, all_grids_num
