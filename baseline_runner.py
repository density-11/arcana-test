import asyncio
import glob
import json
import logging
import os
import re
import subprocess
from datetime import datetime

import openai
from tqdm import tqdm

from api_routing import (
    normalize_api_route,
    resolve_openai_client_kwargs,
)
from model_routing import arc_model_supports_images, resolve_arc_model
from prompts import (
    base1_sys_prompt, cot1_sys_prompt, ana1_sys_prompt, anacot1_sys_prompt,
    base1_sys_prompt_code, cot1_sys_prompt_code, ana1_sys_prompt_code, anacot1_sys_prompt_code,
)
from utils.common_utils import (
    _read_task_file, build_per_test_results, calculate_cost, extract_section,
    judge_ans_detail, parse_confidence,
)
from utils.visualization import (
    save_vis_data_temp, vis_data_for_VLM,
)


BASELINE_METHODS = ("base", "cot", "ana", "anacot")


def resolve_baseline_test_signals(baseline_method="all", code_sig=False):
    normalized_method = str(baseline_method or "all").strip().lower()
    if normalized_method != "all" and normalized_method not in BASELINE_METHODS:
        choices = ", ".join(("all",) + BASELINE_METHODS)
        raise ValueError(
                f"Unsupported baseline method '{baseline_method}'. Choose one of: {choices}."
                )
    selected_methods = BASELINE_METHODS if normalized_method == "all" else (normalized_method,)
    suffix = "messages_code" if code_sig else "messages"
    return normalized_method, [f"{method}1_{suffix}" for method in selected_methods]


async def batch_test_baseline(
        data_dir,
        code_sig=False,
        rerun_code=False,
        use_prior_code=True,
        target_file=None,
        output_dir=None,
        api_route="default",
        model_chosen="GPT5",
        baseline_method="all",
        ):
    if isinstance(code_sig, str):
        code_sig = code_sig.lower() == 't'
    if isinstance(rerun_code, str):
        rerun_code = rerun_code.lower() == 't'
    if isinstance(use_prior_code, str):
        if use_prior_code.lower() == 'f':
            use_prior_code = False
        elif use_prior_code.lower() == 't':
            use_prior_code = True
        else:
            print("The parameter upc should be t or f, not others, Default t is set.")
            use_prior_code = True
    if isinstance(target_file, str) and target_file.lower() == "none":
        target_file = None
    if isinstance(output_dir, str) and output_dir.lower() == "none":
        output_dir = None
    baseline_method, all_test_signal = resolve_baseline_test_signals(
            baseline_method,
            code_sig,
    )
    api_route_name = normalize_api_route(api_route)
    openrouter_provider = None
    uni_generation = None
    uni_streaming = None
    if api_route_name == "uni":
        from providers.uni import generation as uni_generation
        from providers.uni import streaming as uni_streaming
    else:
        from providers import openrouter as openrouter_provider
    requested_model_chosen = model_chosen
    model_key, baseline_model_id, _ = resolve_arc_model(
            model_chosen,
            api_route_name,
            require_vision=False,
            )
    use_vision_inputs = arc_model_supports_images(baseline_model_id, api_route_name)
    input_mode = "vision_and_matrix" if use_vision_inputs else "matrix_only"
    uni_generation_settings = (
            uni_generation.resolve_uni_generation_settings("baseline", model_id=baseline_model_id)
            if api_route_name == "uni"
            else None
            )
    openrouter_reasoning_effort = (
            openrouter_provider.OPENROUTER_BASELINE_REASONING_EFFORT
            if api_route_name == "default"
            else None
            )
    api_client_kwargs = None
    batch_size_env = "ARCANA_UNI_BASELINE_BATCH_SIZE" if api_route_name == "uni" else "ARCANA_BASELINE_BATCH_SIZE"
    default_batch_size = 25
    try:
        baseline_batch_size = max(1, int(os.environ.get(batch_size_env, default_batch_size)))
    except ValueError:
        raise ValueError(f"{batch_size_env} must be a positive integer.")
    single_file_mode = target_file is not None
    if single_file_mode:
        if os.path.isabs(target_file):
            target_file_path = target_file
        else:
            target_file_path = os.path.join(data_dir, target_file)
        target_file_path = os.path.normpath(target_file_path)
        if not os.path.exists(target_file_path):
            raise FileNotFoundError(f"Baseline target file does not exist: {target_file_path}")
    else:
        target_file_path = None
    model_dict = [baseline_model_id]
    abbre_model_dict = {"anthropic/claude-opus-4.5": "CLAUDE", "x-ai/grok-4.1-fast": "GROK",\
            "x-ai/grok-4-fast": "GROK-4",\
            "gpt-5.2-2025-12-11": "GPT", "google/gemini-3-pro-preview": "GEMINI", "openai/gpt-5.2-pro": "GPT5p2p",\
            "openai/gpt-5.2": "GPT", "qwen/qwen3.6-plus": "QWEN", "openai/gpt-5.5": "GPT5p5"}
    abbre_model_dict.setdefault(baseline_model_id, model_key)
    max_iter = 5
    code_timeout_seconds = float(os.environ.get("ARCANA_CODE_TIMEOUT_SECONDS", "10"))
    VL_group = ["ana1_messages", "anacot1_messages"]
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
    def append_jsonl(path, record):
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def save_baseline_program_from_response(mc, test_signal, code_file_name, response):
        if not code_sig or response is None:
            return None
        stranswer = extract_section(response, "ANSWER:")
        if not stranswer:
            return None
        ex_code_file_name = baseline_code_file_path(code_file_name, test_signal, mc)
        os.makedirs(os.path.dirname(ex_code_file_name), exist_ok=True)
        modified_code = modified_code_head + stranswer + modified_code_main
        with open(ex_code_file_name, "w", encoding="utf-8") as f:
            f.write(modified_code)
        return ex_code_file_name

    def usage_value(usage, key):
        if usage is None:
            return 0
        if isinstance(usage, dict):
            return usage.get(key, 0) or 0
        value = getattr(usage, key, None)
        if value is not None:
            return value or 0
        model_extra = getattr(usage, "model_extra", None)
        if isinstance(model_extra, dict):
            return model_extra.get(key, 0) or 0
        return 0

    def usage_metrics(usage, model_name):
        input_tokens = usage_value(usage, "prompt_tokens")
        output_tokens = usage_value(usage, "completion_tokens")
        total_tokens = usage_value(usage, "total_tokens") or input_tokens + output_tokens
        cost = calculate_cost(model=model_name, input_tokens=input_tokens, output_tokens=output_tokens)
        if cost == 0:
            try:
                cost = float(usage_value(usage, "cost"))
            except (TypeError, ValueError):
                cost = 0
        return input_tokens, output_tokens, total_tokens, cost

    def sanitize_api_error(error):
        message = str(error)
        if api_client_kwargs:
            for sensitive_value in (
                    api_client_kwargs.get("base_url"),
                    api_client_kwargs.get("api_key"),
                    ):
                if sensitive_value:
                    message = message.replace(str(sensitive_value), "<redacted>")
        return message

    async def create_completion(mc, client, VL_messages, index, code_file_name, test_signal, log_file_path, run_id):
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        cost = 0
        for temp_sig in range(max_iter):
            try:
                request_kwargs = {
                        "model": mc,
                        "temperature": 1,
                        "messages": VL_messages,
                        }
                if openrouter_reasoning_effort is not None:
                    request_kwargs = openrouter_provider.apply_openrouter_reasoning_effort(
                            request_kwargs,
                            openrouter_reasoning_effort,
                            )
                elif api_route_name == "uni":
                    request_kwargs = uni_generation.apply_uni_generation_settings(
                            request_kwargs,
                            uni_generation_settings,
                            )
                response = await client.chat.completions.create(**request_kwargs)
                if api_route_name == "uni":
                    response = await uni_streaming.collect_async_chat_completion_stream(response)
                content = response.choices[0].message.content
                confidence, confidence_raw = parse_confidence(content)
                input_tokens, output_tokens, total_tokens, cost = usage_metrics(response.usage, mc)
                saved_program_path = save_baseline_program_from_response(mc, test_signal, code_file_name, content)
                print(f"Finish {code_file_name}")
                append_jsonl(log_file_path, {
                        "event": "response",
                        "run_id": run_id,
                        "timestamp": datetime.now().isoformat(),
                        "model": mc,
                        "api_route": api_route_name,
                        "reasoning_effort": openrouter_reasoning_effort,
                        "test_signal": test_signal,
                        "task_file": code_file_name,
                        "index": index,
                        "attempt": temp_sig + 1,
                        "status": "success",
                        "stream": api_route_name == "uni",
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": total_tokens,
                        "cost": cost,
                        "confidence": confidence,
                        "confidence_raw": confidence_raw,
                        "saved_program_path": saved_program_path,
                        "response": content
                        })
                return {
                        "index": index,
                        "response": content,
                        "timestamp": datetime.now().isoformat(),
                        "code_file_name": code_file_name,
                        "status": "success",
                        "api_route": api_route_name,
                        "reasoning_effort": openrouter_reasoning_effort,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": total_tokens,
                        "cost": cost,
                        "confidence": confidence,
                        "confidence_raw": confidence_raw,
                        "saved_program_path": saved_program_path
                        }
            except openai.APIStatusError as e:
                body = getattr(e, "body", None)
                usage = body.get("usage") if isinstance(body, dict) else None
                input_tokens, output_tokens, total_tokens, cost = usage_metrics(usage, mc)
                status_code = getattr(e, "status_code", None)
                error_message = sanitize_api_error(body if body is not None else e)
                print(f"Requests for {index+1} failed, status code: {status_code}")
                print(f"Error message: {error_message}")
                append_jsonl(log_file_path, {
                        "event": "response_error",
                        "run_id": run_id,
                        "timestamp": datetime.now().isoformat(),
                        "model": mc,
                        "api_route": api_route_name,
                        "reasoning_effort": openrouter_reasoning_effort,
                        "test_signal": test_signal,
                        "task_file": code_file_name,
                        "index": index,
                        "attempt": temp_sig + 1,
                        "status": "http_error",
                        "http_status": status_code,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": total_tokens,
                        "cost": cost,
                        "error": error_message
                        })
                if api_route_name == "uni" and temp_sig + 1 < max_iter:
                    await asyncio.sleep(min(60, 5 * (2 ** temp_sig)))
            except Exception as e:
                input_tokens = 0
                output_tokens = 0
                total_tokens = 0
                cost = 0
                error_message = sanitize_api_error(e)
                print(f"{error_message} on {code_file_name}")
                append_jsonl(log_file_path, {
                        "event": "response_error",
                        "run_id": run_id,
                        "timestamp": datetime.now().isoformat(),
                        "model": mc,
                        "api_route": api_route_name,
                        "reasoning_effort": openrouter_reasoning_effort,
                        "test_signal": test_signal,
                        "task_file": code_file_name,
                        "index": index,
                        "attempt": temp_sig + 1,
                        "status": "exception",
                        "error": error_message,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": total_tokens,
                        "cost": cost
                        })
                if api_route_name == "uni" and temp_sig + 1 < max_iter:
                    await asyncio.sleep(min(60, 5 * (2 ** temp_sig)))
        print(f"Failure happens on {code_file_name}!")
        return {
                "index": index,
                "response": None,
                "timestamp": datetime.now().isoformat(),
                "code_file_name": code_file_name,
                "status": "failure",
                "api_route": api_route_name,
                "reasoning_effort": openrouter_reasoning_effort,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "cost": cost
                }

    async def batch_process(model_chosen, test_signal, messages_list, log_file_path, run_id, batch_size: int = 50):
        all_responses = []
        client = openai.AsyncOpenAI(
                **api_client_kwargs,
                timeout=3600,
                max_retries=0,
                )
        try:
            for temp_sig in range(0, len(messages_list), batch_size):
                batch = messages_list[temp_sig: temp_sig + batch_size] if temp_sig + batch_size < len(messages_list) else messages_list[temp_sig:]
                print(f"\n Processing{temp_sig//batch_size + 1}/{(len(messages_list)-1)//batch_size + 1}")

                tasks = [
                        create_completion(model_chosen, client, messages["messages"], temp_sig+idx, messages["code_file_name"], test_signal, log_file_path, run_id) for idx, messages in enumerate(batch)
                    ]

                batch_results = await asyncio.gather(*tasks)
                all_responses.extend(batch_results)

                if temp_sig + batch_size < len(messages_list):
                    await asyncio.sleep(1)

            return all_responses
        finally:
            await client.close()

    def get_messages(exs, ques, exs_url, exs_b64, ques_url, ques_b64, code_file_name, test_signal):
        code_prompt_dict = {}
        for sig in range(len(exs)):
            code_prompt_dict[f"example{sig}"] = {}
            code_prompt_dict[f"example{sig}"]["input"] = exs[sig][0]
            code_prompt_dict[f"example{sig}"]["output"] = exs[sig][1]
        for sig in range(len(ques)):
            code_prompt_dict[f"question{sig}"] = {}
            code_prompt_dict[f"question{sig}"]["input"] = ques[sig]
        question_prompt = f"""
        Solve the following ARC task and follow the output rules:

        {str(code_prompt_dict)}
        """
        if not use_vision_inputs:
            question_prompt += (
                    "\nNo image input is attached for this model. Solve the task from the "
                    "exact matrices above; they contain all task information.\n"
                    )
        VL_question_prompt = [
                {
                    "type": "text",
                    "text": question_prompt
                    },
                {
                    "type": "text",
                    "text": "The visualization of the examples is below:"
                    },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": exs_url
                        }
                    },
                {
                    "type": "text",
                    "text": "The visualization of the questions is below:"
                    },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": ques_url
                        }
                    }
                ]
        RE_dict = {"base1_messages": base1_sys_prompt,\
                "cot1_messages": cot1_sys_prompt,\
                "ana1_messages": ana1_sys_prompt,\
                "anacot1_messages": anacot1_sys_prompt, \
                "base1_messages_code": base1_sys_prompt_code, \
                "cot1_messages_code": cot1_sys_prompt_code, \
                "ana1_messages_code": ana1_sys_prompt_code, \
                "anacot1_messages_code": anacot1_sys_prompt_code } 
        ans_messages_dict = {}
        ans_messages = []
        ans_messages.append({"role": "system", "content": RE_dict[test_signal]})
        if test_signal in VL_group and use_vision_inputs:
            ans_messages.append({"role": "user", "content": VL_question_prompt})
        else:
            ans_messages.append({"role": "user", "content": question_prompt})
        ans_messages_dict["messages"] = ans_messages
        ans_messages_dict["code_file_name"] = code_file_name

        return ans_messages_dict

    def count_tbt_num(tbt_file_dict):
        for key, value in tbt_file_dict.items():
            for test_sig, test_value in value.items():
                if test_sig not in all_test_signal:
                    continue
                if len(test_value['tbt_file_list']) != 0:
                    return False
        return True

    def remove_letters(text):
        result = re.sub(r'[a-zA-Z]', '', text)
        return result

    def communicate_code_process(process, input_json, code_file_name):
        try:
            return process.communicate(input=input_json, timeout=code_timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            timeout_message = f"Code execution timed out after {code_timeout_seconds} seconds: {code_file_name}"
            if stderr:
                timeout_message = timeout_message + "\n" + stderr
            return stdout, timeout_message

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
        if process.returncode != 0:
            return None, stderr
        try:
            output_json = json.loads(stdout)
        except Exception:
            return None, "The output of the function execute() can not be parsed correctly."
        if output_json == None:
            return None, "The output grid is None, which is not valid!"
        if isinstance(output_json, list) and len(output_json) == 1:
            output_json = output_json[0]
        return output_json, ""

    def judge_example_outputs(example_outputs, exs):
        correct_examples = []
        for ex_sig, example_pair in enumerate(exs):
            if ex_sig < len(example_outputs) and example_outputs[ex_sig] == example_pair[1]:
                correct_examples.append(ex_sig)
        return len(correct_examples), len(exs), correct_examples

    def summarize_one_result(result_entry, true_answers, code_file_name, exs = None, example_outputs = None):
        best_corr = -1
        best_all = len(true_answers)
        best_pass = None
        best_correct_tests = []
        per_pass_test_results = []
        for pass_sig, pass_answer in enumerate(result_entry.get("answer", [])):
            corr_num_one, all_num_one, correct_tests = judge_ans_detail(pass_answer, true_answers, code_file_name)
            per_pass_test_results.append({
                    "pass_index": pass_sig,
                    "per_test_results": build_per_test_results(pass_answer, true_answers),
                    })
            if corr_num_one > best_corr:
                best_corr = corr_num_one
                best_all = all_num_one
                best_pass = pass_sig
                best_correct_tests = correct_tests
        if best_corr < 0:
            return None
        result_entry["best_pass"] = best_pass
        result_entry["corr_num"] = best_corr
        result_entry["all_num"] = best_all
        result_entry["correct_tests"] = best_correct_tests
        result_entry["per_pass_test_results"] = per_pass_test_results
        result_entry["per_test_results"] = per_pass_test_results[best_pass]["per_test_results"]
        if exs is not None and example_outputs is not None:
            example_corr_num, example_all_num, correct_examples = judge_example_outputs(example_outputs, exs)
            result_entry["example_outputs"] = example_outputs
            result_entry["example_corr_num"] = example_corr_num
            result_entry["example_all_num"] = example_all_num
            result_entry["correct_examples"] = correct_examples
        return best_corr, best_all, best_correct_tests

    def build_code_result_entry(previous_entry, m_ans, true_answers, code_file_name, exs = None, example_outputs = None, code_error = ""):
        result_entry = {
                "answer": m_ans,
                "input_tokens": previous_entry.get("input_tokens", 0),
                "output_tokens": previous_entry.get("output_tokens", 0),
                "total_tokens": previous_entry.get("total_tokens", 0),
                "cost": previous_entry.get("cost", 0)
                }
        if "api_route" in previous_entry:
            result_entry["api_route"] = previous_entry["api_route"]
        if "analogy" in previous_entry:
            result_entry["analogy"] = previous_entry["analogy"]
        if "confidence" in previous_entry:
            result_entry["confidence"] = previous_entry["confidence"]
        if "confidence_raw" in previous_entry:
            result_entry["confidence_raw"] = previous_entry["confidence_raw"]
        if code_error:
            result_entry["code_error"] = code_error
        summary = summarize_one_result(result_entry, true_answers, code_file_name, exs, example_outputs)
        if summary is not None:
            return result_entry, summary
        result_entry["best_pass"] = None
        result_entry["corr_num"] = 0
        result_entry["all_num"] = len(true_answers)
        result_entry["correct_tests"] = []
        result_entry["per_pass_test_results"] = []
        result_entry["per_test_results"] = build_per_test_results([], true_answers)
        if exs is not None and example_outputs is not None:
            example_corr_num, example_all_num, correct_examples = judge_example_outputs(example_outputs, exs)
            result_entry["example_outputs"] = example_outputs
            result_entry["example_corr_num"] = example_corr_num
            result_entry["example_all_num"] = example_all_num
            result_entry["correct_examples"] = correct_examples
        return result_entry, (0, len(true_answers), [])

    def update_code_summary_buckets(summary_buckets, code_file_name, result_entry):
        if "example_corr_num" not in result_entry:
            return
        examples_all_correct = result_entry["example_corr_num"] == result_entry["example_all_num"]
        tests_all_correct = result_entry["corr_num"] == result_entry["all_num"]
        tests_partially_correct = 0 < result_entry["corr_num"] < result_entry["all_num"]
        tests_any_correct = result_entry["corr_num"] > 0
        record = {
                "file": code_file_name,
                "example_corr_num": result_entry["example_corr_num"],
                "example_all_num": result_entry["example_all_num"],
                "correct_examples": result_entry["correct_examples"],
                "corr_num": result_entry["corr_num"],
                "all_num": result_entry["all_num"],
                "correct_tests": result_entry["correct_tests"]
                }
        if examples_all_correct and tests_all_correct:
            summary_buckets["code_all_correct"].append(record)
        elif examples_all_correct and (tests_partially_correct or not tests_any_correct):
            summary_buckets["examples_all_correct_tests_not_all_correct"].append(record)
        elif (not examples_all_correct) and tests_any_correct:
            summary_buckets["tests_correct_examples_not_all_correct"].append(record)

    def make_code_summary_buckets():
        return {
                "code_all_correct": [],
                "examples_all_correct_tests_not_all_correct": [],
                "tests_correct_examples_not_all_correct": []
                }

    def collect_per_test_result_records(model_results):
        records = []
        for code_file_name, result_entry in model_results.items():
            if not isinstance(result_entry, dict):
                continue
            for test_result in result_entry.get("per_test_results", []):
                if not isinstance(test_result, dict):
                    continue
                records.append({
                        "file": code_file_name,
                        "best_pass": result_entry.get("best_pass"),
                        **test_result,
                        })
        return records

    def first_existing_path(*paths):
        for path in paths:
            if path and os.path.exists(path):
                return path
        return None

    def model_dir_name(model_name):
        return abbre_model_dict.get(model_name, re.sub(r"[^A-Za-z0-9_.-]+", "_", model_name).strip("_") or "model")

    def model_stats_dir(model_name):
        path = os.path.join(stats_dir, model_dir_name(model_name))
        os.makedirs(path, exist_ok=True)
        return path

    def model_to_be_test_path(model_name):
        return os.path.join(model_stats_dir(model_name), "to_be_test.json")

    def model_all_result_path(model_name):
        return os.path.join(model_stats_dir(model_name), "batch_baseline_answer_dict.json")

    def model_log_path(model_name):
        path = os.path.join(logs_dir, model_dir_name(model_name), run_id, "batch_full_response.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def load_partitioned_json(path_func):
        merged_dict = {}
        for model_name in model_dict:
            path = path_func(model_name)
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                model_data = json.load(f)
            merged_dict[model_name] = model_data.get(model_name, model_data)
        return merged_dict

    def select_current_model_partition(data):
        if not isinstance(data, dict):
            return {}
        model_data = data.get(baseline_model_id)
        if not isinstance(model_data, dict):
            return {}
        return {baseline_model_id: model_data}

    def merge_model_partition(path, current_data):
        merged_data = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                if isinstance(existing_data, dict):
                    merged_data.update(existing_data)
            except (OSError, json.JSONDecodeError) as e:
                print(f"Reading existing aggregate result {path} failed. Error: {e}")
        merged_data.update(current_data)
        return merged_data

    def token_task_keys(task_file_name):
        keys = {task_file_name}
        norm_key = os.path.normpath(task_file_name)
        keys.add(norm_key)
        if not norm_key.startswith(".") and not os.path.isabs(norm_key):
            keys.add(f"./{norm_key}")
        return keys

    def load_logged_token_entries():
        token_entries = {}
        if not os.path.exists(logs_dir):
            return token_entries
        for root, _, file_names in os.walk(logs_dir):
            for file_name in file_names:
                if not file_name.endswith(".jsonl"):
                    continue
                log_path = os.path.join(root, file_name)
                try:
                    with open(log_path, "r", encoding="utf-8") as f:
                        for line in f:
                            if not line.strip():
                                continue
                            try:
                                record = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            if record.get("event") != "response" or record.get("status") != "success":
                                continue
                            model_name = record.get("model")
                            test_signal = record.get("test_signal")
                            task_file_name = record.get("task_file") or record.get("code_file_name")
                            if not model_name or not test_signal or not task_file_name:
                                continue
                            token_entry = {
                                    "input_tokens": record.get("input_tokens", 0),
                                    "output_tokens": record.get("output_tokens", 0),
                                    "total_tokens": record.get("total_tokens", 0),
                                    "cost": record.get("cost", 0),
                                    "api_route": record.get("api_route", "default"),
                                    "confidence": record.get("confidence"),
                                    "confidence_raw": record.get("confidence_raw", ""),
                                    }
                            model_tokens = token_entries.setdefault(model_name, {})
                            signal_tokens = model_tokens.setdefault(test_signal, {})
                            for key in token_task_keys(task_file_name):
                                signal_tokens[key] = token_entry
                except OSError as e:
                    print(f"Reading log {log_path} failed. Error: {e}")
        return token_entries

    def fill_missing_tokens_from_logs(previous_entry, logged_token_entries, model_name, test_signal, task_file_name):
        result_entry = dict(previous_entry)
        logged_entry = None
        for key in token_task_keys(task_file_name):
            logged_entry = logged_token_entries.get(model_name, {}).get(test_signal, {}).get(key)
            if logged_entry:
                break
        if not logged_entry:
            return result_entry
        for token_key in ("input_tokens", "output_tokens", "total_tokens", "cost"):
            if not result_entry.get(token_key):
                result_entry[token_key] = logged_entry.get(token_key, 0)
        for metadata_key in ("confidence", "confidence_raw"):
            if metadata_key not in result_entry:
                result_entry[metadata_key] = logged_entry.get(metadata_key)
        return result_entry

    def write_baseline_result_files(tbt_dict, all_result_dict):
        merged_tbt_dict = merge_model_partition(to_be_test_list, tbt_dict)
        merged_result_dict = merge_model_partition(all_result_dict_dir, all_result_dict)
        with open(to_be_test_list, "w", encoding="utf-8") as f:
            json.dump(merged_tbt_dict, f)
        with open(all_result_dict_dir, "w", encoding="utf-8") as f:
            json.dump(merged_result_dict, f)
        for model_name in sorted(set(tbt_dict) | set(all_result_dict)):
            with open(model_to_be_test_path(model_name), "w", encoding="utf-8") as f:
                json.dump({model_name: tbt_dict.get(model_name, {})}, f)
            with open(model_all_result_path(model_name), "w", encoding="utf-8") as f:
                json.dump({model_name: all_result_dict.get(model_name, {})}, f)

    def baseline_visual_path(code_file_name, model_name, test_sig, pass_sig):
        rel_path = os.path.relpath(code_file_name, data_dir)
        rel_stem = os.path.splitext(rel_path)[0]
        png_path = os.path.join(visuals_dir, model_dir_name(model_name), test_sig, f"{rel_stem}_{pass_sig}.png")
        os.makedirs(os.path.dirname(png_path), exist_ok=True)
        return png_path

    def baseline_code_file_path(task_file_name, test_sig, model_name):
        abbre_code_file_name = os.path.relpath(task_file_name, data_dir).replace(".json", "")
        return os.path.join(programs_dir, model_dir_name(model_name), abbre_code_file_name, f"code_{abbre_code_file_name}_{test_sig}.py")

    def legacy_baseline_code_file_paths(task_file_name, test_sig):
        abbre_code_file_name = os.path.relpath(task_file_name, data_dir).replace(".json", "")
        return [
                os.path.join(programs_dir, abbre_code_file_name, f"code_{abbre_code_file_name}_{test_sig}.py"),
                os.path.join("./baseline_programs", abbre_code_file_name, f"code_{abbre_code_file_name}_{test_sig}.py")
                ]


    # getting response
    baseline_base_dir = "./baseline_code" if code_sig else "./baseline"
    output_run_name = None
    if output_dir is None:
        baseline_dir = baseline_base_dir
        stats_dir = os.path.join(baseline_dir, "results")
        visuals_dir = os.path.join(baseline_dir, "visualizations")
        logs_dir = os.path.join(baseline_dir, "logs")
        programs_dir = os.path.join(baseline_dir, "programs")
        output_dir_was_existing = os.path.exists(baseline_dir)
    else:
        if os.path.isabs(output_dir) or os.sep in output_dir or output_dir.startswith("."):
            output_run_name = os.path.normpath(output_dir)
            baseline_dir = output_run_name
            stats_dir = os.path.join(baseline_dir, "results")
            visuals_dir = os.path.join(baseline_dir, "visualizations")
            logs_dir = os.path.join(baseline_dir, "logs")
            programs_dir = os.path.join(baseline_dir, "programs")
        else:
            output_run_name = output_dir
            baseline_dir = baseline_base_dir
            stats_dir = os.path.join(baseline_dir, "results", output_run_name)
            visuals_dir = os.path.join(baseline_dir, "visualizations", output_run_name)
            logs_dir = os.path.join(baseline_dir, "logs", output_run_name)
            programs_dir = os.path.join(baseline_dir, "programs", output_run_name)
        output_dir_was_existing = any(os.path.exists(path) for path in [stats_dir, visuals_dir, logs_dir, programs_dir])
    print(f"Baseline result outputs will be saved to {stats_dir}")
    print(f"Baseline artifact root is {baseline_dir}")
    os.makedirs(stats_dir, exist_ok=True)
    os.makedirs(visuals_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)
    if code_sig:
        os.makedirs(programs_dir, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_log_dir = os.path.join(logs_dir, "runs")
    os.makedirs(run_log_dir, exist_ok=True)
    raw_response_log_path = os.path.join(run_log_dir, f"{run_id}.jsonl")
    if not rerun_code:
        append_jsonl(raw_response_log_path, {
                "event": "run_start",
                "run_id": run_id,
                "timestamp": datetime.now().isoformat(),
                "baseline_dir": baseline_dir,
                "stats_dir": stats_dir,
                "visualizations_dir": visuals_dir,
                "logs_dir": logs_dir,
                "programs_dir": programs_dir,
                "code_mode": code_sig,
                "rerun_code": rerun_code,
                "api_route": api_route_name,
                "requested_model": requested_model_chosen,
                "resolved_model": baseline_model_id,
                "model_storage_name": model_key,
                "batch_size": baseline_batch_size,
                "stream": api_route_name == "uni",
                "input_mode": input_mode,
                "uni_generation_settings": uni_generation_settings,
                "use_prior_code": use_prior_code,
                "single_file_mode": single_file_mode,
                "target_file": target_file_path,
                "output_dir": output_run_name,
                "baseline_method": baseline_method,
                "test_signals": all_test_signal,
                "models": model_dict
                })
    to_be_test_list = f"{stats_dir}/to_be_test.json"
    all_result_dict_dir = f"{stats_dir}/batch_baseline_answer_dict.json"
    legacy_to_be_test_list = f"{baseline_dir}/to_be_test.json"
    legacy_all_result_dict_dir = f"{baseline_dir}/batch_baseline_answer_dict.json"
    overwrite_target_file = False

    def task_path_matches(candidate_path, target_path):
        if not candidate_path or not target_path:
            return False
        try:
            return os.path.normpath(candidate_path) == os.path.normpath(target_path)
        except TypeError:
            return False

    def result_dict_contains_task(result_dict, target_path, test_signals=None):
        model_results = result_dict.get(baseline_model_id, {}) if isinstance(result_dict, dict) else {}
        if not isinstance(model_results, dict):
            return False
        selected_signals = set(test_signals or model_results)
        for test_signal, signal_results in model_results.items():
            if test_signal not in selected_signals:
                continue
            if not isinstance(signal_results, dict):
                continue
            if any(task_path_matches(task_path, target_path) for task_path in signal_results):
                return True
        return False

    def prune_task_from_result_dict(result_dict, target_path, test_signals=None):
        model_results = result_dict.get(baseline_model_id, {}) if isinstance(result_dict, dict) else {}
        if not isinstance(model_results, dict):
            return
        selected_signals = set(test_signals or model_results)
        for test_signal, signal_results in model_results.items():
            if test_signal not in selected_signals:
                continue
            if not isinstance(signal_results, dict):
                continue
            for task_path in list(signal_results):
                if task_path_matches(task_path, target_path):
                    del signal_results[task_path]

    def result_path_contains_task(path, target_path, test_signals=None):
        if not path or not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                return result_dict_contains_task(json.load(f), target_path, test_signals)
        except Exception as e:
            print(f"Checking existing baseline result {path} failed. Error: {e}")
            return False

    def baseline_output_contains_task(target_path, test_signals=None):
        candidate_paths = [all_result_dict_dir, legacy_all_result_dict_dir]
        for model_name in model_dict:
            candidate_paths.append(os.path.join(stats_dir, model_dir_name(model_name), "batch_baseline_answer_dict.json"))
        return any(
                result_path_contains_task(path, target_path, test_signals)
                for path in candidate_paths
                )

    if (
            output_dir is not None
            and output_dir_was_existing
            and single_file_mode
            and baseline_output_contains_task(target_file_path, all_test_signal)
            ):
        prompt = (
                f"Existing baseline result for {target_file_path} was found in {stats_dir}. "
                "Overwrite and rerun API? [y/N]: "
                )
        answer = input(prompt).strip().lower()
        if answer not in {"y", "yes"}:
            print("Baseline run cancelled. Existing result was kept; no API call was made.")
            return
        overwrite_target_file = True
    multiple_sig = False
    suffix_sig = ["messages_code", "messages"]
    passat_prefix_sig = ["1"]
    analogy_prefix_sig = ["ana", "anacot"]
    analogy_test_signal = [f"{pre}{pas}_{suf}" for pre in analogy_prefix_sig for pas in passat_prefix_sig for suf in suffix_sig] 
    for png_dir in [model_dir_name(model_name) for model_name in model_dict]:
        for test_sig_png in all_test_signal:
            os.makedirs(os.path.join(visuals_dir, png_dir, test_sig_png), exist_ok=True)
    if rerun_code:
        if not code_sig:
            raise ValueError("--rerun_code t is only supported together with --code t.")
        if single_file_mode:
            files = [target_file_path]
        else:
            pattern = os.path.join(data_dir, "*.json")
            files = sorted(glob.glob(pattern))
        existing_result_dict_path = first_existing_path(all_result_dict_dir, legacy_all_result_dict_dir) if use_prior_code else None
        if use_prior_code and existing_result_dict_path:
            with open(existing_result_dict_path, "r", encoding="utf-8") as f:
                all_result_dict = select_current_model_partition(json.load(f))
            if not all_result_dict:
                all_result_dict = load_partitioned_json(model_all_result_path)
        elif use_prior_code and code_sig and os.path.exists("./baseline/batch_baseline_answer_dict.json"):
            with open("./baseline/batch_baseline_answer_dict.json", "r", encoding="utf-8") as f:
                old_result_dict = json.load(f)
            all_result_dict = {}
            for old_model, old_model_results in select_current_model_partition(old_result_dict).items():
                all_result_dict[old_model] = {
                        old_sig: old_entries for old_sig, old_entries in old_model_results.items()
                        if old_sig.endswith("_code")
                        }
        elif use_prior_code:
            all_result_dict = load_partitioned_json(model_all_result_path)
        else:
            all_result_dict = {}
        if single_file_mode and overwrite_target_file:
            prune_task_from_result_dict(all_result_dict, target_file_path, all_test_signal)
        existing_tbt_path = first_existing_path(to_be_test_list, legacy_to_be_test_list) if use_prior_code else None
        if use_prior_code and existing_tbt_path:
            with open(existing_tbt_path, "r", encoding="utf-8") as f:
                tbt_dict = select_current_model_partition(json.load(f))
            if not tbt_dict:
                tbt_dict = load_partitioned_json(model_to_be_test_path)
        elif use_prior_code:
            tbt_dict = load_partitioned_json(model_to_be_test_path)
        else:
            tbt_dict = {}
        logged_token_entries = load_logged_token_entries()
        for mc in model_dict:
            if mc not in all_result_dict:
                all_result_dict[mc] = {}
            if mc not in tbt_dict:
                tbt_dict[mc] = {}
            for test_sig in all_test_signal:
                previous_result_entries = all_result_dict[mc].get(test_sig, {})
                all_result_dict[mc][test_sig] = {}
                tbt_file_list = []
                all_corr_num = 0
                all_all_num = 0
                all_solved = []
                partial_correct = []
                code_summary_buckets = make_code_summary_buckets()
                for code_file_name in tqdm(files):
                    ex_code_file_name = first_existing_path(
                            baseline_code_file_path(code_file_name, test_sig, mc),
                            *legacy_baseline_code_file_paths(code_file_name, test_sig)
                            )
                    if not ex_code_file_name:
                        tbt_file_list.append(code_file_name)
                        continue
                    exs, ques, true_answers = _read_task_file(code_file_name)
                    previous_entry = fill_missing_tokens_from_logs(
                            previous_result_entries.get(code_file_name, {}),
                            logged_token_entries,
                            mc,
                            test_sig,
                            code_file_name
                            )
                    output_grid_list = []
                    answer = []
                    error_message = ""
                    for exs_input_sig in range(len(exs)):
                        output_json, error_message = run_code_on_grid(ex_code_file_name, exs[exs_input_sig][0])
                        if error_message:
                            break
                        output_grid_list.append(output_json)
                    if error_message:
                        print(f"Code execution failed on examples for {code_file_name}: {error_message}")
                        tbt_file_list.append(code_file_name)
                        result_entry, summary = build_code_result_entry(
                                previous_entry, [[]], true_answers, code_file_name,
                                exs, output_grid_list, error_message
                                )
                        corr_num, all_num, correct_tests = summary
                        all_result_dict[mc][test_sig][code_file_name] = result_entry
                        update_code_summary_buckets(code_summary_buckets, code_file_name, result_entry)
                        all_corr_num += corr_num
                        all_all_num += all_num
                        if corr_num > 0:
                            partial_correct.append({
                                "file": code_file_name,
                                "corr_num": corr_num,
                                "all_num": all_num,
                                "correct_tests": correct_tests
                                })
                        continue
                    for ques_sig in range(len(ques)):
                        output_json, error_message = run_code_on_grid(ex_code_file_name, ques[ques_sig])
                        if error_message:
                            break
                        answer.append(output_json)
                    if error_message:
                        print(f"Code execution failed on questions for {code_file_name}: {error_message}")
                        tbt_file_list.append(code_file_name)
                    m_ans = [answer]
                    result_entry, summary = build_code_result_entry(
                            previous_entry, m_ans, true_answers, code_file_name,
                            exs, output_grid_list, error_message
                            )
                    corr_num, all_num, correct_tests = summary
                    all_result_dict[mc][test_sig][code_file_name] = result_entry
                    update_code_summary_buckets(code_summary_buckets, code_file_name, result_entry)
                    all_corr_num += corr_num
                    all_all_num += all_num
                    if corr_num == all_num:
                        all_solved.append(code_file_name)
                    elif corr_num > 0:
                        partial_correct.append({
                            "file": code_file_name,
                            "corr_num": corr_num,
                            "all_num": all_num,
                            "correct_tests": correct_tests
                            })
                    png_path = baseline_visual_path(code_file_name, mc, test_sig, 0)
                    try:
                        save_vis_data_temp(exs, output_grid_list, ques, answer, 0, code_file_name, path = png_path)
                    except Exception as e:
                        print(f"Visualization for {code_file_name} failed, times 0. Error: {e}")
                tbt_dict[mc][test_sig] = {
                        "all_num": all_all_num,
                        "corr_num": all_corr_num,
                        "solved": all_solved,
                        "partial_correct": partial_correct,
                        "tbt_file_list": tbt_file_list,
                        "per_test_results": collect_per_test_result_records(all_result_dict[mc][test_sig]),
                        **code_summary_buckets
                        }
        write_baseline_result_files(tbt_dict, all_result_dict)
        print("Code-only baseline rerun finished.")
        return
    api_client_kwargs = resolve_openai_client_kwargs(
            api_route_name,
            default_base_url_env="OPENAI_BASE_URL",
            default_api_key_env="OPENAI_API_KEY",
            )
    print(f"API route: {api_route_name}")
    print(f"Model mapping: {requested_model_chosen} -> {baseline_model_id}")
    print(f"Model storage folder: {model_key}")
    print(f"ARC input mode: {input_mode}")
    print(f"Baseline method: {baseline_method} ({', '.join(all_test_signal)})")
    print(f"Baseline API concurrency: {baseline_batch_size}")
    if openrouter_reasoning_effort is not None:
        print(f"OpenRouter baseline reasoning effort: {openrouter_reasoning_effort}")
    if uni_generation_settings:
        print(
                "UNI generation settings: "
                f"max_length={uni_generation_settings['max_length'] or 'provider default'}, "
                "thinking=" + (
                    "provider default"
                    if uni_generation_settings["enable_thinking"] is None
                    else "on" if uni_generation_settings["enable_thinking"] else "off"
                )
                )
    if single_file_mode:
        files = [target_file_path]
    else:
        pattern = os.path.join(data_dir, "*.json")
        files = sorted(glob.glob(pattern))
    existing_tbt_path = first_existing_path(to_be_test_list, legacy_to_be_test_list) if use_prior_code else None
    if use_prior_code and existing_tbt_path:
        with open(existing_tbt_path, 'r', encoding='utf-8') as f:
            tbt_dict = select_current_model_partition(json.load(f))
        if not tbt_dict:
            tbt_dict = load_partitioned_json(model_to_be_test_path)
        multiple_sig = bool(tbt_dict) and not single_file_mode
    else:
        tbt_dict = load_partitioned_json(model_to_be_test_path) if use_prior_code else {}
        if use_prior_code and tbt_dict:
            multiple_sig = not single_file_mode
    existing_result_dict_path = first_existing_path(all_result_dict_dir, legacy_all_result_dict_dir) if use_prior_code else None
    if use_prior_code and existing_result_dict_path:
        with open(existing_result_dict_path, "r") as f:
            all_result_dict = select_current_model_partition(json.load(f))
        if not all_result_dict:
            all_result_dict = load_partitioned_json(model_all_result_path)
    else:
        all_result_dict = load_partitioned_json(model_all_result_path) if use_prior_code else {}
    if single_file_mode and overwrite_target_file:
        prune_task_from_result_dict(all_result_dict, target_file_path, all_test_signal)
    t_dict = {}
    print("Processing data!")
    if multiple_sig:
        for model_key, file_list in tbt_dict.items():
            t_dict[model_key] = {}
            for test_sig, tbt_file_dict_total in file_list.items():
                if test_sig not in all_test_signal:
                    continue
                tbt_file_list = tbt_file_dict_total["tbt_file_list"]
                t_dict[model_key][test_sig] = {}
                all_answers = {}
                all_messages = []
                for path in tqdm(tbt_file_list):
                    exs, ques, ans = _read_task_file(path)
                    if use_vision_inputs:
                        exs_url, exs_b64 = vis_data_for_VLM(exs, in_out = True)
                        ques_url, ques_b64 = vis_data_for_VLM(ques, in_out = False)
                    else:
                        exs_url = exs_b64 = ques_url = ques_b64 = None
                    one_task_messages = get_messages(exs, ques, exs_url, exs_b64, ques_url, ques_b64, path, test_sig)
                    all_messages.append(one_task_messages)
                    all_answers[path] = ans
                t_dict[model_key][test_sig]["all_messages"] = all_messages
                t_dict[model_key][test_sig]["all_answers"] = all_answers
    else:
        all_answers = {}
        all_messages_dict = {}
        for test_sig in all_test_signal:
            all_messages_dict[test_sig] = []
        for path in tqdm(files):
            exs, ques, ans = _read_task_file(path)
            if use_vision_inputs:
                exs_url, exs_b64 = vis_data_for_VLM(exs, in_out = True)
                ques_url, ques_b64 = vis_data_for_VLM(ques, in_out = False)
            else:
                exs_url = exs_b64 = ques_url = ques_b64 = None
            all_answers[path] = ans
            for test_sig in all_test_signal:
                one_task_messages = get_messages(exs, ques, exs_url, exs_b64, ques_url, ques_b64, path, test_sig)
                all_messages_dict[test_sig].append(one_task_messages)

        for model_key in model_dict:
            tbt_dict[model_key] = {}
            t_dict[model_key] = {}
            for test_sig in all_test_signal:
                tbt_dict[model_key][test_sig] = {}
                tbt_dict[model_key][test_sig]["all_num"] = 0
                tbt_dict[model_key][test_sig]["corr_num"] = 0
                tbt_dict[model_key][test_sig]["solved"] = []
                t_dict[model_key][test_sig] = {}
                t_dict[model_key][test_sig]["all_messages"] = all_messages_dict[test_sig]
                t_dict[model_key][test_sig]["all_answers"] = all_answers
    circ_times = 0
    ana_target_dict = {}
    for test_sig in analogy_test_signal:
        ana_target_dict[test_sig] = {}
    while True:
        for mc, test_files in t_dict.items():
            logging.info(f"--------------{mc} begins-------------------")
            if mc not in all_result_dict:
                all_result_dict[mc] = {}
            model_response_log_path = model_log_path(mc)
            append_jsonl(model_response_log_path, {
                    "event": "model_run_start",
                    "run_id": run_id,
                    "timestamp": datetime.now().isoformat(),
                    "model": mc,
                    "api_route": api_route_name,
                    "input_mode": input_mode,
                    "baseline_dir": baseline_dir,
                    "code_mode": code_sig,
                    "rerun_code": rerun_code,
                    "stream": api_route_name == "uni",
                    "uni_generation_settings": uni_generation_settings,
                    "baseline_method": baseline_method,
                    "test_signals": all_test_signal,
                    })
            for test_sig, test_file_dicts in test_files.items():
                if test_sig not in all_result_dict[mc]:
                    all_result_dict[mc][test_sig] = {}
                logging.info(f"---------------{test_sig} begins--------------")
                all_answers = test_file_dicts["all_answers"]
                append_jsonl(model_response_log_path, {
                        "event": "signal_start",
                        "run_id": run_id,
                        "timestamp": datetime.now().isoformat(),
                        "model": mc,
                        "api_route": api_route_name,
                        "test_signal": test_sig,
                        "num_tasks": len(test_file_dicts["all_messages"])
                        })
                results = await batch_process(
                        mc,
                        test_sig,
                        test_file_dicts["all_messages"],
                        model_response_log_path,
                        run_id,
                        batch_size=baseline_batch_size,
                        )
                append_jsonl(model_response_log_path, {
                        "event": "signal_end",
                        "run_id": run_id,
                        "timestamp": datetime.now().isoformat(),
                        "model": mc,
                        "api_route": api_route_name,
                        "test_signal": test_sig,
                        "num_results": len(results),
                        "num_success": sum(1 for result in results if result.get("status") == "success"),
                        "num_failure": sum(1 for result in results if result.get("status") != "success")
                        })
                results.sort(key=lambda x: x['index'])
                successful_responses = {}
                example_outputs_by_file = {}
                to_be_test_file_next = []
                tokens_dict = {}
                tokens_dict["input_tokens"] = {} 
                tokens_dict["output_tokens"] = {} 
                tokens_dict["total_tokens"] = {}
                tokens_dict["cost"] = {}
                confidence_dict = {}
                confidence_raw_dict = {}
                failed_responses = {}

                def mark_to_be_test(code_file_name):
                    if code_file_name not in to_be_test_file_next:
                        to_be_test_file_next.append(code_file_name)

                def remember_failed_result(code_file_name, token_entry, code_error, m_ans = None, example_outputs = None):
                    if m_ans is None:
                        m_ans = [[]]
                    exs_current, _, true_answers = _read_task_file(code_file_name)
                    result_entry, _ = build_code_result_entry(
                            token_entry, m_ans, true_answers, code_file_name,
                            exs_current if code_sig else None,
                            example_outputs if code_sig else None,
                            code_error
                            )
                    if test_sig in analogy_test_signal:
                        result_entry["analogy"] = ana_target_dict[test_sig].get(code_file_name, "")
                    failed_responses[code_file_name] = result_entry

                for task_results in tqdm(results):
                    if task_results['status'] == "success":
                        response = task_results['response']
                        code_file_name = task_results['code_file_name']
                        cost = task_results['cost']
                        input_tokens = task_results['input_tokens']
                        output_tokens = task_results['output_tokens']
                        total_tokens = task_results['total_tokens']
                        confidence = task_results.get("confidence")
                        confidence_raw = task_results.get("confidence_raw", "")
                        stranswer = extract_section(response, "ANSWER:")
                        tokens_dict["input_tokens"][code_file_name] = input_tokens 
                        tokens_dict["output_tokens"][code_file_name] = output_tokens 
                        tokens_dict["total_tokens"][code_file_name] = total_tokens
                        tokens_dict["cost"][code_file_name] = cost
                        confidence_dict[code_file_name] = confidence
                        confidence_raw_dict[code_file_name] = confidence_raw
                        token_entry = {
                                "input_tokens": input_tokens,
                                "output_tokens": output_tokens,
                                "total_tokens": total_tokens,
                                "cost": cost,
                                "api_route": task_results.get("api_route", api_route_name),
                                "confidence": confidence,
                                "confidence_raw": confidence_raw,
                                }
                        if test_sig in analogy_test_signal:
                            try:
                                stranalogy = extract_section(response, "ANALOGY:")
                                ana_target_dict[test_sig][code_file_name] = stranalogy
                            except:
                                print("No analogy.")
                                ana_target_dict[test_sig][code_file_name] = ""
                        if stranswer is None:
                            mark_to_be_test(code_file_name)
                            if code_sig:
                                remember_failed_result(code_file_name, token_entry, "No ANSWER section found in response.")
                            continue
                        if not code_sig:
                            stranswer = stranswer.replace('[[[[', '[[[').replace(']]]]', ']]]')
                            stranswer = remove_letters(stranswer)
                            try:
                                tbr_answer = json.loads(stranswer)
                            except Exception as e:
                                print(e)
                                mark_to_be_test(code_file_name)
                                continue
                            tbr_answer = [tbr_answer]
                            if not isinstance(tbr_answer, list):
                                print("Output is not a list!")
                                mark_to_be_test(code_file_name)
                                continue
                            answer = []
                            for temp_sig_tbr in range(len(tbr_answer)):
                                oc_answer = tbr_answer[temp_sig_tbr]
                                if len(oc_answer)!= 1 and len(oc_answer) != 2:
                                    answer.append([oc_answer])
                                else:
                                    answer.append(oc_answer)
                        else:
                            # save file
                            ex_code_file_name = baseline_code_file_path(code_file_name, test_sig, mc)
                            os.makedirs(os.path.dirname(ex_code_file_name), exist_ok=True)
                            modified_code = modified_code_head + stranswer + modified_code_main
                            with open(ex_code_file_name, "w", encoding='utf-8') as f:
                                f.write(modified_code)

                            # execute code
                            output_grid_list = []
                            answer = []
                            error_signal = False
                            # compute all of the examples
                            exs, ques, ans = _read_task_file(code_file_name)
                            for exs_input_sig in range(len(exs)):
                                input_json = json.dumps(exs[exs_input_sig][0])

                                process = subprocess.Popen(
                                        ['python3', ex_code_file_name],
                                        stdin = subprocess.PIPE,
                                        stdout = subprocess.PIPE,
                                        stderr = subprocess.PIPE,
                                        text = True
                                    )
                                stdout, stderr = communicate_code_process(process, input_json, ex_code_file_name)
                                if process.returncode != 0:
                                    error_signal = True
                                    error_message = stderr
                                    mark_to_be_test(code_file_name)
                                    break
                                else:
                                    error_signal = False
                                    error_message = ""

                                try:
                                    output_json = json.loads(stdout)
                                    if output_json == None:
                                        error_signal = True
                                        error_message = "The output grid is None, which is not valid!"
                                        mark_to_be_test(code_file_name)
                                        break
                                except:
                                    error_signal = True
                                    error_message = "The output of the function execute() can not be parsed correctly."
                                    mark_to_be_test(code_file_name)
                                    break
                                if len(output_json) == 1:
                                    output_json = output_json[0]
                                output_grid_list.append(output_json)
                            if error_signal:
                                remember_failed_result(code_file_name, token_entry, error_message, [[]], output_grid_list)
                                continue
                            for exs_input_sig in range(len(ques)):
                                input_json = json.dumps(ques[exs_input_sig])
                                process = subprocess.Popen(
                                        ['python3', ex_code_file_name],
                                        stdin = subprocess.PIPE,
                                        stdout = subprocess.PIPE,
                                        stderr = subprocess.PIPE,
                                        text = True
                                    )
                                stdout, stderr = communicate_code_process(process, input_json, ex_code_file_name)
                                if process.returncode != 0:
                                    error_signal = True
                                    error_message = stderr
                                    mark_to_be_test(code_file_name)
                                    break
                                else:
                                    error_signal = False
                                    error_message = ""

                                try:
                                    output_json = json.loads(stdout)
                                    if output_json == None:
                                        error_signal = True
                                        error_message = "The output grid is None, which is not valid!"
                                        mark_to_be_test(code_file_name)
                                        break
                                except:
                                    error_signal = True
                                    error_message = "The output of the function execute() can not be parsed correctly."
                                    mark_to_be_test(code_file_name)
                                    break
                                if len(output_json) == 1:
                                    output_json = output_json[0]
                                answer.append(output_json)
                            if error_signal:
                                remember_failed_result(code_file_name, token_entry, error_message, [answer], output_grid_list)
                                continue
                            answer = [answer]
                            example_outputs_by_file[code_file_name] = output_grid_list
                        successful_responses[code_file_name] = answer
                        exs, ques, ans = _read_task_file(code_file_name)
                        exs_ans = []
                        for temp_sig in range(len(exs)):
                            exs_ans.append(exs[temp_sig][1])
                        for ans_pass_sig in range(len(answer)):
                            png_path = baseline_visual_path(code_file_name, mc, test_sig, ans_pass_sig)
                            try:
                                if not code_sig:
                                    save_vis_data_temp(exs, exs_ans, ques, answer[ans_pass_sig], 0, code_file_name, path = png_path)
                                else:
                                    save_vis_data_temp(exs, output_grid_list, ques, answer[ans_pass_sig], 0, code_file_name, path = png_path)
                            except Exception as e:
                                print(f"Visualization for {code_file_name} failed, times {ans_pass_sig}. Error: {e}")
                    else:
                        mark_to_be_test(task_results['code_file_name'])
                if to_be_test_file_next is not None:
                    tbt_dict[mc][test_sig]["tbt_file_list"] = to_be_test_file_next
                all_result_dict[mc][test_sig].update(failed_responses)
                for code_file_name, m_ans in successful_responses.items():
                    success_signal = False
                    for pass_sig in range(len(m_ans)):
                        try:
                            judge_ans_detail(m_ans[pass_sig], all_answers[code_file_name], code_file_name)
                            success_signal = True
                        except Exception as e:
                            print(f"Judging {code_file_name} failed! Times {pass_sig}. Error: {e}")
                    if not success_signal:
                        tbt_dict[mc][test_sig]["tbt_file_list"].append(code_file_name)
                        continue
                    all_result_dict[mc][test_sig][code_file_name] = {}
                    all_result_dict[mc][test_sig][code_file_name]["answer"] = m_ans
                    all_result_dict[mc][test_sig][code_file_name]["input_tokens"] = tokens_dict["input_tokens"][code_file_name]
                    all_result_dict[mc][test_sig][code_file_name]["output_tokens"] = tokens_dict["output_tokens"][code_file_name]
                    all_result_dict[mc][test_sig][code_file_name]["total_tokens"] = tokens_dict["total_tokens"][code_file_name]
                    all_result_dict[mc][test_sig][code_file_name]["cost"] = tokens_dict["cost"][code_file_name]
                    all_result_dict[mc][test_sig][code_file_name]["api_route"] = api_route_name
                    all_result_dict[mc][test_sig][code_file_name]["confidence"] = confidence_dict.get(code_file_name)
                    all_result_dict[mc][test_sig][code_file_name]["confidence_raw"] = confidence_raw_dict.get(code_file_name, "")
                    if code_sig and code_file_name in example_outputs_by_file:
                        exs_current, _, true_answers = _read_task_file(code_file_name)
                        summarize_one_result(
                                all_result_dict[mc][test_sig][code_file_name],
                                true_answers,
                                code_file_name,
                                exs_current,
                                example_outputs_by_file[code_file_name]
                                )
                    if test_sig in analogy_test_signal:
                        all_result_dict[mc][test_sig][code_file_name]["analogy"] = ana_target_dict[test_sig][code_file_name]

                all_corr_num = 0
                all_all_num = 0
                all_solved = []
                partial_correct = []
                code_summary_buckets = make_code_summary_buckets()
                for code_file_name, result_entry in all_result_dict[mc][test_sig].items():
                    try:
                        exs, _, true_answers = _read_task_file(code_file_name)
                    except Exception as e:
                        print(f"Reading {code_file_name} failed during summary rebuild. Error: {e}")
                        continue
                    try:
                        if code_sig and "example_outputs" in result_entry:
                            summary = summarize_one_result(result_entry, true_answers, code_file_name, exs, result_entry["example_outputs"])
                        else:
                            summary = summarize_one_result(result_entry, true_answers, code_file_name)
                    except Exception as e:
                        print(f"Judging {code_file_name} failed during summary rebuild. Error: {e}")
                        continue
                    if summary is None:
                        continue
                    best_corr, best_all, best_correct_tests = summary
                    if code_sig:
                        update_code_summary_buckets(code_summary_buckets, code_file_name, result_entry)
                    all_corr_num += best_corr
                    all_all_num += best_all
                    if best_corr == best_all:
                        all_solved.append(code_file_name)
                    elif best_corr > 0:
                        partial_correct.append({
                            "file": code_file_name,
                            "corr_num": best_corr,
                            "all_num": best_all,
                            "correct_tests": best_correct_tests
                            })
                tbt_dict[mc][test_sig]["all_num"] = all_all_num
                tbt_dict[mc][test_sig]["corr_num"] = all_corr_num
                tbt_dict[mc][test_sig]["solved"] = all_solved
                tbt_dict[mc][test_sig]["partial_correct"] = partial_correct
                tbt_dict[mc][test_sig]["per_test_results"] = collect_per_test_result_records(
                        all_result_dict[mc][test_sig]
                        )
                if code_sig:
                    tbt_dict[mc][test_sig].update(code_summary_buckets)
        write_baseline_result_files(tbt_dict, all_result_dict)
        if count_tbt_num(tbt_dict):
            print("All test finished!")
            append_jsonl(raw_response_log_path, {
                    "event": "run_end",
                    "run_id": run_id,
                    "timestamp": datetime.now().isoformat(),
                    "status": "all_finished"
                    })
            break
        for mc, model_answers in tbt_dict.items():
            for test_sig_answers, test_sig_values in model_answers.items():
                if test_sig_answers not in all_test_signal:
                    continue
                next_messages = []
                for one_task_messages in t_dict[mc][test_sig_answers]["all_messages"]:
                    if one_task_messages["code_file_name"] in tbt_dict[mc][test_sig_answers]["tbt_file_list"]:
                        next_messages.append(one_task_messages)
                t_dict[mc][test_sig_answers]["all_messages"] = next_messages
        if circ_times < 3:
            circ_times +=1
        else:
            append_jsonl(raw_response_log_path, {
                    "event": "run_end",
                    "run_id": run_id,
                    "timestamp": datetime.now().isoformat(),
                    "status": "max_retry_reached"
                    })
            break
