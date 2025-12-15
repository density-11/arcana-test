# test ARCANA tests on models
# python import
import torch
import numpy
import json
import openai
import os
import time
import glob
import ast
from tqdm import tqdm
from typing import Any, Dict, List, Tuple
import matplotlib.pyplot as plt
import base64
import io
import matplotlib.colors as mcolors
from matplotlib.colors import ListedColormap
import argparse
import google.generativeai as genai
from google.genai.errors import APIError
import re
import ast
import subprocess
import pickle
import tempfile
import random
import logging

# prompts import
from prompts import p_prompt, pv_prompt, np_prompt, npv_prompt, check_prompt, check_p_prompt, recog_prompt_color, recog_prompt_shape, recog_prompt_dynamic, recog_prompt_full, recog_com_head, code_prompt, rectify_code_prompt, question_code_prompt, modify_code_prompt, crossover_code_prompt, mutate_analogy_prompt, mutate_code_prompt, abnormal_code_prompt, small_mutation_code_prompt, final_rectify_code_prompt, breaking_code_prompt, cot_code_prompt 

from test_prompt import basket_prompt, bell_prompt 


# debug import
import ipdb

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

    examples_raw = data.get("examples", []) or []
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
        test_ans = test.get("answer", test.get("output"))
        _append_test_case(test_inp, test_ans)
    elif isinstance(test, list):
        for t in test:
            if not isinstance(t, dict):
                continue
            test_inp = t.get("input")
            test_ans = t.get("answer", t.get("output"))
            _append_test_case(test_inp, test_ans)
            
    return examples, questions, answers


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
            if "Reason" not in obj:
                print("Parsed object is a dict but missing the 'Reason' key.")
                return None
            answer_reason = answer["Reason"]
            return {"analogy": answer_analogy, "reason": answer_reason}
        else:
            print("Parsed object must be a list or a dict containing the 'Analogy' and 'Reason' key.")
            return None
    elif is_format == "final":
        if isinstance(obj, list):
            answer = obj[0]
        else:
            answer = obj
        if isinstance(answer, dict):
            if "Judgement" not in answer:
                print("Parsed object is a dict but missing the 'Judgement' key.")
                return None
            answer_analogy = answer["Judgement"]
            if "Instructions" not in obj:
                print("Parsed object is a dict but missing the 'Instructions' key.")
                return None
            answer_reason = answer["Instructions"]
            return {"judge": answer_analogy, "instruct": answer_reason}
        else:
            print("Parsed object must be a list or a dict containing the 'Judgement' and 'Instructions' key.")
            return None




def test_json_grids(data_dir: str, model_chosen: str, prompted: str, vision: str, cot: str) -> Tuple[List[ExamplePair], List[Grid], List[Grid]]:
    """
    Read all json files from the data directory and return examples, questions and answers. Test them through models
    """
    pattern = os.path.join(data_dir, "*.json")
    files = sorted(glob.glob(pattern))
    all_exs = 0
    all_corr = 0
    answers = {}
    targets = {}
    recur = 0
    max_recur = 2
    results_dir = f'./cot_results_{model_chosen}'
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
    programs_dir = f'./cot_programs_{model_chosen}'
    if not os.path.exists(programs_dir):
        os.makedirs(programs_dir)
    if prompted == 't':
        prompted_state = True
    elif prompted == 'f':
        prompted_state = False
    else:
        print("The parameter --p should be t or f, not others. Default t is set.")
        prompted_state = True

    if vision == 't':
        VL_state = True
    elif vision == 'f':
        VL_state = False
    else:
        print("The parameter --v should be t or f, not others. Default t is set.")
        VL_state = True

    if cot == 't':
        cot_state = True
    elif cot == 'f':
        cot_state = False
    else:
        print("The parameter --cot should be t or f, not others. Default t is set.")
        cot_state = True

    while len(files) != 0:
        untested_file = []
        temp_count = 0
        for path in tqdm(files):
            exs, ques, ans = _read_task_file(path)
            ex_name = path.replace(data_dir, "").replace(".json", "")
            code_file_name = programs_dir + "/code_" + ex_name + ".py"
            code_result_file_name = results_dir + "/results_" + ex_name + ".json"
            if os.path.exists(code_result_file_name):
                continue
            if not cot_state:
                str_m_ans = test_model(exs, ques, model_chosen, prompted_state, VL_state)
                #ipdb.set_trace()
                if str_m_ans is None:
                    print(f"Network error during {path}")
                    untested_file.append(path)
                    continue
                str_m_ans = str_m_ans.replace("```", "").replace("json", "")
                m_ans = parse_answer(str_m_ans, is_format = "answer")
                if m_ans is None:
                    print(f"The answer string of {path} cannot be transported into dicts")
                    untested_file.append(path)
                    continue
            else:
                m_ans = cot_get_code_response(exs, ques, model_chosen, prompted_state, code_file_name)
                if m_ans == None:
                    untested_file.append(path)
                    continue
            try:
                corr_num, all_num = judge_ans(m_ans, ans, path)
            except Exception as e:
                print(f"File {path} error happen: {e}")
                untested_file.append(path)
                continue
            saved_ans_dict = {"answer": m_ans}
            exs_ans = []
            for idx in range(len(exs)):
                exs_ans.append(exs[idx][1])
            save_vis_data_temp(exs, exs_ans, ques, m_ans, 0, code_result_file_name, temp = False, cot = True)
            with open(code_result_file_name, "w", encoding="utf-8") as f:
                json.dump(saved_ans_dict, f)
            all_exs += all_num
            all_corr += corr_num
            answers[path] = m_ans
            temp_count += 1
            #if temp_count == 5:
            #    break

        print(untested_file)
        print(f"All questions number: {all_exs}, correct answers number: {all_corr}")
        files = untested_file
        recur += 1
        with open("one_chance_answers.json", "w") as outfile:
            json.dump(answers, outfile)
        if recur > max_recur:
            print("No Money!!!!!!!")
            print(files)
            with open("untested_files.json", "w") as uf:
                json.dump(files, uf)
                break
        if len(files) != 0:
            print("Now test for the network error examples.")
        else:
            print("All examples have been tested.")
    checkpoint_file_name = results_dir + "/checkpoint.json"
    if os.path.exists(checkpoint_file_name):
        with open(checkpoint_file_name, "r", encoding="utf-8") as f:
            checkpoint_dict = json.load(checkpoint_file_name)
        all_exs_cp = checkpoint_dict['all_exs']
        all_corr_cp = checkpoint_dict['all_corr']
        checkpoint_dict['all_exs'] = all_exs_cp + all_exs
        checkpoint_dict['all_corr'] = all_corr_cp + all_corr
    else:
        checkpoint_dict = {}
        checkpoint_dict['all_exs'] = all_exs
        checkpoint_dict['all_corr'] = all_corr

    with open(checkpoint_file_name, "w", encoding="utf-8") as f:
        json.dump(checkpoint_dict, f)


def vis_data_for_VLM(tar, in_out = True):
    cmap = ListedColormap(["#FFFFFF","#4A90E2","#50E3C2","#F5A623","#7ED321","#BD10E0","#D0021B","#F8E71C","#8B572A","#000000"])
    tar_n = len(tar)
    i_o_n = 1
    subtitle = 'test question'
    if in_out == True:
        i_o_n = 2
        subtitle = 'train example'
    fig, axes = plt.subplots(i_o_n, tar_n, figsize=(4 * tar_n, 4 * i_o_n))
    plt.suptitle("Visualization", fontsize=20)
    for idx, train_ex in enumerate(tar):
        if in_out:
            axes[0, idx].pcolormesh(train_ex[0], cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth=0.005)
            axes[0, idx].invert_yaxis()
            axes[0, idx].set_title(subtitle + f' {idx+1}')
            axes[1, idx].pcolormesh(train_ex[1], cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth=0.005)
            axes[1, idx].invert_yaxis()
        else:
            if len(tar) > 1:
                axes[idx].pcolormesh(train_ex, cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth=0.005)
                axes[idx].invert_yaxis()
                axes[idx].set_title(subtitle + f' {idx+1}')
            else:
                axes.pcolormesh(train_ex, cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth=0.005)
                axes.invert_yaxis()
                axes.set_title(subtitle + f' {idx+1}')

            
    buf = io.BytesIO()
    fig.savefig(buf, format = 'png', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)

    img_b64 = base64.b64encode(buf.read()).decode('ascii')
    data_url = f"data:image/png;base64,{img_b64}"
    return data_url, img_b64

def test_model(exs, ques, model_chosen = "GPT5", prompted = True, vision = True):
    # model hub
    Qwen = "/models/Qwen2.5-VL-72B-Instruct"
    deepseek = "deepseek-r1-250528"
    gpt5 = "gpt-5-2025-08-07"
    gpt4p1 = "gpt-4.1-2025-04-14"
    gpt4o = "gpt-4o-2024-11-20"
    doubao = "doubao-seed-1-6-vision-250815"
    gemini = "gemini-2.5-flash"

    model_hub_dict = {"Qwen": Qwen, "deepseek": deepseek, "GPT5": gpt5, "GPT4.1": gpt4p1, "GPT4o": gpt4o, "doubao": doubao, "gemini": gemini}

    check_format = False

    # Gemini test
    google_api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not google_api_key and model_chosen == "gemini":
        raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set.")

    #state
    if model_chosen in model_hub_dict:
        mc = model_hub_dict[model_chosen]
    else:
        raise ValueError("Model can not be found in model hub! The model you can choose: Qwen, deepseek, GPT5, GPT4.1, GPT4o, doubao, gemini")

    exs_url, exs_b64 = vis_data_for_VLM(exs, in_out = True)
    ques_url, ques_b64 = vis_data_for_VLM(ques, in_out = False)
    if model_chosen == "gemini":
        genai.configure(api_key = google_api_key)
        client = genai.GenerativeModel('gemini-3.0-pro-thinking')
        # print(f"Gemini chosen!")
    else:
        client = openai.OpenAI()

    if vision:
        if prompted:
            chosen_prompt = pv_prompt
        else:
            chosen_prompt = npv_prompt
    else:
        if prompted:
            chosen_prompt = p_prompt
        else:
            chosen_prompt = np_prompt
    

    # Messages form
    matrix_message = "The matrixs of the question are below: examples:"+str(exs)+"questions:"+str(ques)
    if model_chosen == "gemini":
        VL_messages = [chosen_prompt, 
                "The visualization of examples are shown below:", 
                {"mime_type": "image/png", "data": exs_b64},
                "The visualization of questions are shown below:",
                {"mime_type": "image/png", "data": ques_b64},
                matrix_message
                ]
        L_messages = [chosen_prompt, matrix_message]
    else:
        VL_messages = [
                        {
                            "role": "user",
                            "content": [{"type":"text", "text":chosen_prompt
                                },
                            {
                                "type":"text", "text":"The visualization of examples are shown below:"
                                },
                            {
                                "type": "image_url", "image_url": {"url": exs_url}
                                },
                            {
                                "type":"text", "text":"The visualization of questions are shown below:"
                                },
                            {
                                "type":"image_url", "image_url": {"url": ques_url}
                                },
                            {
                                "type": "text",
                                "text": "The matrixs of the question are below: examples:"+str(exs)+"questions:"+str(ques)
                                }
                            ]
                            },
                        ]
        L_messages = [
                {
                    "role": "system",
                    "content": chosen_prompt
                    },
                {
                    "role": "user",
                    "content": "The matrixs of the question are below: examples:"+str(exs)+"questions:"+str(ques)
                    }
                ]
    
    if vision:
        chosen_messages = VL_messages
    else:
        chosen_messages = L_messages

    retry_times = 2
    for attempt in range(retry_times):
        try:
            if model_chosen == "gemini":
                response = client.generate_content(
                        chosen_messages, request_options={"timeout": 1800}
                        )
            else:
                response = client.chat.completions.create(
                        model = mc,
                        messages = L_messages
                        )
        except Exception as e:
            if "503" in str(e):
                if attempt < retry_times - 1:
                    print(f"Try for the {attempt+1} time.")
                    time.sleep(2)
                    continue
                else:
                    print(f"All attempts failed. {e}")
                    return None
            else:
                print(f"{e}")
                return None

    if check_format:
        dict_to_be_rec = response.choices[0].message.content
        #ipdb.set_trace()

        try:
            response = client.chat.completions.create(
                    model = deepseek,
                    messages = [
                        {
                            "role": "system",
                            "content": check_p_prompt
                            },
                        {
                            "role": "user",
                            "content": "The dict to be rectified is below:"+dict_to_be_rec
                            }
                        ]
                    )
        except Exception as e:
            print(f"checking error: {e}")
            return dict_to_be_rec
        #ipdb.set_trace()
    if model_chosen == "gemini":
        return response.text
    else:
        return response.choices[0].message.content

def cot_get_code_response(exs, ques, model_chosen, prompted_state, code_file_name):
    # model hub
    Qwen = "/models/Qwen2.5-VL-72B-Instruct"
    deepseek = "deepseek-r1-250528"
    gpt5 = "gpt-5.1-2025-11-13"
    gpt4p1 = "gpt-4.1-2025-04-14"
    gpt4o = "gpt-4o-2024-11-20"
    doubao = "doubao-seed-1-6-vision-250815"
    gemini = "gemini-3.0-pro-thinking"

    model_hub_dict = {"Qwen": Qwen, "deepseek": deepseek, "GPT5": gpt5, "GPT4.1": gpt4p1, "GPT4o": gpt4o, "doubao": doubao, "gemini": gemini}


    # Gemini test
    google_api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not google_api_key and model_chosen == "gemini":
        raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set.")

    #state
    if model_chosen in model_hub_dict:
        mc = model_hub_dict[model_chosen]
    else:
        raise ValueError("Model can not be found in model hub! The model you can choose: Qwen, deepseek, GPT5, GPT4.1, GPT4o, doubao, gemini")

    exs_url, exs_b64 = vis_data_for_VLM(exs, in_out = True)
    ques_url, ques_b64 = vis_data_for_VLM(ques, in_out = False)
    if model_chosen == "gemini":
        genai.configure(api_key = google_api_key)
        client = genai.GenerativeModel('gemini-3.0-pro-thinking')
        # print(f"Gemini chosen!")
    else:
        client = openai.OpenAI()

    modified_code_head = """import json
import sys

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
    code_prompt_dict = {}
    for sig in range(len(exs)):
        code_prompt_dict[f"example{sig}"] = {}
        code_prompt_dict[f"example{sig}"]["input"] = exs[sig][0]
        code_prompt_dict[f"example{sig}"]["output"] = exs[sig][1]
    if not prompted_state:
        chosen_prompt = cot_code_prompt

    if model_chosen == "gemini":
        VL_messages = [
                "You are an expert Python programmer and good at solving puzzles. Always think step by step before writing code. Follow the exact format requested: REASONING, CODE.",
                chosen_prompt,
                "The matrix of the task is given below:",
                str(code_prompt_dict),
                "The image of examples are shown below:", 
                {"mime_type": "image/png", "data": exs_b64},
                "The image of questions are shown below:",
                {"mime_type": "image/png", "data": ques_b64},
                ]
        finished = False
        temp_sig = 0
        while True:
            try:
                response = client.generate_content(
                        VL_messages, request_options={"timeout": 1800}
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
    else:
        VL_messages = [
                {
                    "role": "system",
                    "content": "You are an expert Python programmer and good at solving puzzles. Always think step by step before writing code. Follow the exact format requested: REASONING, CODE."
                    },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": chosen_prompt
                            },
                        {
                            "type": "text",
                            "content": "The matrix of the task is given below: " + str(code_prompt_dict)
                            },
                        {
                            "type":"text", 
                            "text":"The image of examples are shown below:"
                            },
                        {
                            "type":"image_url", 
                            "image_url": {"url": exs_url}
                            },
                        {
                            "type":"text", 
                            "text":"The image of questions are shown below:"
                            },
                        {
                            "type":"image_url", 
                            "image_url": {"url": ques_url}
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

    reasoning = extract_section(full_response, "REASONING:")
    code = extract_section(full_response, "CODE:")

    code = clean_code(code)
    is_safe, safe_message = is_safe_code(code)
    if not is_safe:
        print(f"Warning: {safe_message}")
    modified_code = modified_code_head + code + modified_code_main
    with open(code_file_name, "w", encoding='utf-8') as f:
        f.write(modified_code)
    output_grid_list = []
    # compute all of the examples
    for exs_input_sig in range(len(ques)):
        input_json = json.dumps(exs[exs_input_sig][0])

        process = subprocess.Popen(
                ['python3', code_file_name],
                stdin = subprocess.PIPE,
                stdout = subprocess.PIPE,
                stderr = subprocess.PIPE,
                text = True
            )
        stdout, stderr = process.communicate(input=input_json)
        if process.returncode != 0:
            error_signal = True
            error_message = stderr
            break
        else:
            error_signal = False
            error_message = ""

        output_json = json.loads(stdout)
        if output_json == None:
            error_signal = True
            error_message = "The output grid is None, which is not valid!"
            break
        if len(output_json) == 1:
            output_json = output_json[0]
        output_grid_list.append(output_json)
    if error_signal:
        print(f"Error happens! Error message is {error_message}.")
        return None
    else:
        return output_grid_list

def judge_ans(m_ans, ans, path):
    """
    Judge whether the answers models return and the true answer, support both multiple answers and single answer. 
    """
    if isinstance(m_ans, dict):
        rt_ans = m_ans["answer"]
        #print(f"Output form is not expected! The file is {path}")
        #return
    else:
        rt_ans = m_ans
    corr_num, all_num = 0, 0
    if len(rt_ans) != 1 and len(rt_ans) != 2:
        rt_ans = [rt_ans]
    for sig in range(len(rt_ans)):
        rt_t = rt_ans[sig]
        if not isinstance(rt_t, list):
            print(f"Output form of single answer is not expected! The file is {path}")
            continue
        true_ans = ans[sig]
        all_num += 1
        if true_ans == rt_t:
            corr_num += 1
    if all_num == corr_num:
        print(f"{path} is totally correct, solved by model.")

    return corr_num, all_num


def test_one_file(data_dir, file_name, model_chosen: str, prompted: str, vision: str, upc: str, debug:str):
    if file_name == None:
        print(f"file name should not be None")
        return

    path = os.path.join(data_dir, file_name)

    if prompted == 't':
        prompted_state = True
    elif prompted == 'f':
        prompted_state = False
    else:
        print("The parameter --p should be t or f, not others. Default t is set.")
        prompted_state = True

    if vision == 't':
        VL_state = True
    elif vision == 'f':
        VL_state = False
    else:
        print("The parameter --v should be t or f, not others. Default t is set.")
        VL_state = True

    if upc == 'f':
        use_prior_code = False
    elif upc == 't':
        use_prior_code = True
    else:
        print("The parameter upc should be t or f, not others, Default f is set.")
        use_prior_code = False

    if debug == 'f':
        debug_mode = False
    elif debug == 't':
        debug_mode = True
    else:
        print("The parameter --debug should be t or f, not others, Default f is set.")
        debug_mode = False

    Qwen = "/models/Qwen2.5-VL-72B-Instruct"
    deepseek = "deepseek-r1-250528"
    gpt5 = "gpt-5-2025-08-07"
    gpt4p1 = "gpt-4.1-2025-04-14"
    gpt4o = "gpt-4o-2024-11-20"
    doubao = "doubao-seed-1-6-vision-250815"
    gemini = "gemini-2.5-flash"

    model_hub_dict = {"Qwen": Qwen, "deepseek": deepseek, "GPT5": gpt5, "GPT4.1": gpt4p1, "GPT4o": gpt4o, "doubao": doubao, "gemini": gemini}

    if model_chosen in model_hub_dict:
        mc = model_hub_dict[model_chosen]
    else:
        raise ValueError("Model can not be found in model hub! The model you can choose: Qwen, deepseek, GPT5, GPT4.1, GPT4o, doubao, gemini")
    exs, ques, ans = _read_task_file(path)

    exs_url, exs_b64 = vis_data_for_VLM(exs, in_out = True)
    ques_url, ques_b64 = vis_data_for_VLM(ques, in_out = False)

    ex_name = file_name.replace(".json", "")

    # important parameters
    crossover_rate = 0.4
    circ_times = 0
    max_circ_times = 7
    delta_mutation_rate = 0.1
    coeff_right_delta_mutation = 0.5
    delta_small_mutation_rate = 0.1
    coeff_right_delta_small_mutation = 0.5

    # mutation probablity calculation
    mutation_rate_dict = {}
    small_mutation_rate_dict = {}
    former_correct_rate_dict = {}

    # logging config
    logging.basicConfig(
            level = logging.INFO,
            format = '%(asctime)s - %(levelname)s - %(message)s',
            filename = f'{ex_name}_test.log',
            filemode = 'a'
            )

    # directory examination
    programs_dir = f'./programs/{ex_name}'
    if not os.path.exists(programs_dir):
        os.makedirs(programs_dir)
    results_dir = f'./results/{ex_name}'
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
    programs_dict_file = programs_dir + f'/programs_{ex_name}.json'
    if os.path.exists(programs_dict_file):
        use_prior_code = True
    else:
        use_prior_code = False

    # code wrapper for execution
    modified_code_head = """import json
import sys

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

    # Calculate mask and choose metric strategy
    try:
        judge_mask_exs = get_similarity_mask_batch(exs)
        judge_by_mask = True
    except Exception as e:
        judge_mask_exs = None
        judge_by_mask = False

    ### Debug mode contents
    if debug_mode:
        basket_code_content = [
                {
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
                    "text": "The deductive rule and reason, and their code accomplishment instructiosn are provided as below:"
                    },
                {
                    "type": "text",
                    "text":bell_prompt
                    }
        ]
        VL_messages = [
                {
                    "role": "system",
                    "content": "You are an expert Python programmer. Always think step by step before writing code. Follow the exact format requested: REASONING, CODE, EXPLANATION."
                    },
                {
                    "role": "user",
                    "content": basket_code_content 
                    }
                ]
        client = openai.OpenAI()
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
        logging.info(full_response)
        reasoning = extract_section(full_response, "REASONING:")
        code = extract_section(full_response, "CODE:")
        explanation = extract_section(full_response, "EXPLANATION:")
        modified_code = modified_code_head + code + modified_code_main
        code_file_name = f'./{ex_name}_test.py'
        with open(code_file_name, "w", encoding='utf-8') as f:
            f.write(modified_code)
            print(f"Modified code saved to {code_file_name}")
            logging.info(f"Modified code saved to {code_file_name}")
        output_grid_list_ex = []
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
            stdout, stderr = process.communicate(input=input_json)
            if process.returncode != 0:
                error_signal = True
                error_message = stderr
                break
            else:
                error_signal = False
                error_message = ""

            output_json = json.loads(stdout)
            if output_json == None:
                error_signal = True
                error_message = "The output grid is None, which is not valid!"
                break
            if len(output_json) == 1:
                output_json = output_json[0]
            output_grid_list_ex.append(output_json)

        output_grid_list_temp = []
        for exs_input_sig in range(len(ques)):
            input_json = json.dumps(ques[exs_input_sig])

            process = subprocess.Popen(
                    ['python3', code_file_name],
                    stdin = subprocess.PIPE,
                    stdout = subprocess.PIPE,
                    stderr = subprocess.PIPE,
                    text = True
                )
            stdout, stderr = process.communicate(input=input_json)
            if process.returncode != 0:
                error_signal = True
                error_message = stderr
                break
            else:
                error_signal = False
                error_message = ""

            output_json = json.loads(stdout)
            if output_json == None:
                error_signal = True
                error_message = "The output grid is None, which is not valid!"
                break
            if len(output_json) == 1:
                output_json = output_json[0]
            output_grid_list_temp.append(output_json)
        save_vis_data_temp(exs, output_grid_list_ex, ques, output_grid_list_temp, -1, code_file_name, temp = True)
        return



    if use_prior_code:
        print("Start code execution!")
        logging.info("Reload programs.")

        ## directly execute the code

        # load programs file
        program_write_dict = {}
        with open(programs_dict_file, "r") as f:
            program_write_dict = json.load(f)
        programs_dict = program_write_dict[ex_name]


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
                stdout, stderr = process.communicate(input=input_json)
                if process.returncode != 0:
                    error_signal = True
                    error_message = stderr
                    break
                else:
                    error_signal = False
                    error_message = ""

                output_json = json.loads(stdout)
                if output_json == None:
                    error_signal = True
                    error_message = "The output grid is None, which is not valid!"
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
        # Analogy part
        print("Start analogy part!")
        logging.info("Analogy start.")
        color_generate = test_recog_one_file(recog_prompt_color, exs_url, mc)
        if color_generate == None:
            print(f"Color recog failed!")
            logging.info("Color recog failed!")
        else:
            logging.info("Color recog successed!")
            logging.info(color_generate)
        shape_generate = test_recog_one_file(recog_prompt_shape, exs_url, mc)
        if shape_generate == None:
            print(f"Shape recog failed!")
            logging.info("Shape recog failed!")
        else:
            logging.info("Shape recog successed!")
            logging.info(shape_generate)
        dynamic_generate = test_recog_one_file(recog_prompt_dynamic, exs_url, mc)
        if dynamic_generate == None:
            print(f"Dynamic recog failed!")
            logging.info("Dynamic recog failed!")
        else:
            logging.info("Dynamic recog successed!")
            logging.info(dynamic_generate)
        full_generate = test_recog_one_file(recog_prompt_full, exs_url, mc)
        if full_generate == None:
            print(f"Full recog failed!")
            logging.info("Full recog failed.")
        else:
            logging.info(f"Full recog successed!")
            logging.info(full_generate)
        print("Finish analogy part!")
        logging.info("Analogy finished.")
        
        # Slippage part
        print("Start slippage part!")
        logging.info("Slippage start.")
        recog_com_prompt = recog_com_head + "1. The analogy mainly considering color is: " + color_generate + "2. The analogy mainly considering shape is: " + shape_generate + "3. The analogy mainly considering dynamic process is: " + dynamic_generate + "4. The analogy mainly considering full image is: " + full_generate 
        com_generate = test_recog_one_file(recog_com_prompt, exs_url, mc)
        if com_generate == None:
            print(f"Composite recog failed!")
            logging.info("Composite recog failed!")
            return None
        else:
            logging.info("Composite recog successed!")
            logging.info(com_generate)
        com_dict = parse_answer(com_generate, is_format="recog")
        targets = com_dict['Analogy_list']
        print("Finish Slippage Part!")
        logging.info("Slippage finished.")


        # Programming part
        print("Start programming part!")
        logging.info("Programming start.")
        programs_dict = {}
        example_result_dict = {}
        for sig in range(3):
            print(f"-------------Start programming code{sig}--------------")
            logging.info(f"Proggramming code{sig}.")
            target_dict = targets[sig]
            answer_dict = {}
            if 'Analogy' in target_dict:
                target = target_dict['Analogy']
                answer_dict['Analogy'] = target
            else:
                print(f"Target is a dict but is lack of the key 'Analogy'.")
                return None
            if 'Reason' in target_dict:
                reason = target_dict['Reason']
                answer_dict['Reason'] = reason
            else:
                print(f"Target is a dict but is lack of the key 'Reason'.")
            # coding function
            print("Coding.............")
            logging.info(f"Coding code{sig}")
            code_dict = coding_target(answer_dict, is_reflect = 0, mc = mc, exs=code_prompt_dict, exs_url = exs_url)
            if code_dict == None:
                print(f"Coding failed!")
                logging.info(f"Coding code{sig} failed!")
                return None
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
                stdout, stderr = process.communicate(input=input_json)
                if process.returncode != 0:
                    error_signal = True
                    error_message = stderr
                    break
                else:
                    error_signal = False
                    error_message = ""

                output_json = json.loads(stdout)
                if output_json == None:
                    error_signal = True
                    error_message = "The output grid is None, which is not valid!"
                    break
                if len(output_json) == 1:
                    output_json = output_json[0]
                output_grid_list.append(output_json)
            
            write_code_dict = {}
            for key, value in code_dict.items():
                write_code_dict[key] = value
            write_code_dict['error_signal'] = error_signal
            write_code_dict['error_message'] = error_message
            write_code_dict['former correct rate'] = 0
            write_code_dict['small mutation rate'] = 0
            write_code_dict['mutation rate'] = 0
            programs_dict[code_file_name] = write_code_dict
            example_result_dict[code_file_name] = output_grid_list
            former_correct_rate_dict[code_file_name] = 0
            mutation_rate_dict[code_file_name] = 0
            small_mutation_rate_dict[code_file_name] = 0

        print("Finish Programming Part!")
        programs_dict['circulate times'] = 0
        programs_dict_file = programs_dir + f'/programs_{ex_name}.json'
        program_write_dict = {}
        program_write_dict[ex_name] = programs_dict
        with open(programs_dict_file, "w") as f:
            json.dump(program_write_dict, f)
            print(f"Programs already saved to {programs_dict_file}")
            logging.info(f"Programs already saved to {programs_dict_file}")
    
    all_solved_code_filename = []
    break_sig = False
    output_grid_temp_dict = {}
    for circ_sig in range(circ_times, max_circ_times):
        new_mutate_programs_dict = {}
        all_solved_code_filename_temp = []
        print(f"Start circulate {circ_sig+1}!")
        logging.info(f"Start circulate {circ_sig+1}!")
        # Judge examples output
        print("Start judging code outputs!")
        for judge_code_file_name, judge_code_result_dict in programs_dict.items():
            if judge_code_file_name == 'circulate times':
                continue
            if judge_code_result_dict == None:
                continue
            if judge_code_result_dict['error_signal']:
                continue
            judge_code_result_grid = example_result_dict[judge_code_file_name]
            all_right = True
            for ex_num_sig in range(len(exs)):
                if judge_code_result_grid[ex_num_sig] != exs[ex_num_sig][1]:
                    all_right = False
            if all_right:
                print(f"All examples are right! Code is {judge_code_file_name}")
                logging.info(f"All examples are right! Code is {judge_code_file_name}")
                all_solved_code_filename_temp.append(judge_code_file_name)
                break_sig = True

        # compute current output of questions
        for code_file_name, code_result_dict in programs_dict.items():
            if code_file_name == 'circulate times':
                continue
            if code_result_dict == None:
                continue
            # execute code
            print(f"-------Start computing current output of {code_file_name}--------")
            output_grid_list_temp = []
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
                stdout, stderr = process.communicate(input=input_json)
                if process.returncode != 0:
                    error_signal = True
                    error_message = stderr
                    break
                else:
                    error_signal = False
                    error_message = ""

                output_json = json.loads(stdout)
                if output_json == None:
                    error_signal = True
                    error_message = "The output grid is None, which is not valid!"
                    break
                if len(output_json) == 1:
                    output_json = output_json[0]
                output_grid_list_temp.append(output_json)
            code_result_dict['error_signal'] = error_signal
            code_result_dict['error_message'] = error_message
            output_grid_temp_dict[code_file_name] = output_grid_list_temp


            if not error_signal:
                try:
                    save_vis_data_temp(exs, example_result_dict[code_file_name], ques, output_grid_list_temp, circ_sig, code_file_name)
                except Exception as e:
                    print(e)

        if break_sig:
            break_sig_sig = False
            print(f"Start break judging! Some codes are leaving!")
            logging.info(f"Start break judging! Some codes are leaving!")
            for judge_code_file_name in all_solved_code_filename_temp:
                code_file_dict = programs_dict[judge_code_file_name]
                breaking_prompt_content = [
                        {
                            "type": "text",
                            "text": breaking_code_prompt
                            },
                        {
                            "type": "text", 
                            "text": "The analogy of the question:" + code_file_dict['analogy'] + "\nThe reason of the analogy:" + code_file_dict['reason']
                            },
                        {
                            "type": "text",
                            "text": "The visualization of examples are shown below:"
                            },
                        {
                            "type": "image_url",
                            "image_url": {"url": exs_url}
                            }
                        ]
                final_rectify_prompt_content = [
                        {
                            "type": "text",
                            "text": final_rectify_code_prompt
                            },
                        {
                            "type": "text", 
                            "text": "The analogy of the question:" + code_file_dict['analogy'] + "\nThe reason of the analogy:" + code_file_dict['reason']
                            },
                        {
                            "type": "text",
                            "text": "The visualization of examples are shown below:"
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
                            "text":str(code_prompt_dict)
                            },
                        {
                            "type": "text",
                            "text": "The code is shown below:"
                            },
                        {
                            "type": "text",
                            "text": programs_dict[judge_code_file_name]['code']
                            }
                        ]
                logging.info(f"Juding {judge_code_file_name}")
                output_result_one_program = output_grid_temp_dict[judge_code_file_name]
                for ques_sig_num in range(len(ques)):
                    result_ques_url, result_ques_b64 = vis_result_grid_for_LLM(ques[ques_sig_num], output_result_one_program[ques_sig_num])
                    breaking_prompt_content.append({
                        "type": "text",
                        "text": f"The visualization of the question {ques_sig_num+1} input and the corresponding output from the code is shown below:"
                        })
                    breaking_prompt_content.append({
                        "type": "image_url", 
                        "image_url": {"url": result_ques_url}
                        })
                    final_rectify_prompt_content.append({
                        "type": "text",
                        "text": f"The visualization of the question {ques_sig_num+1} input and the corresponding output from the code is shown below:"
                        })
                    final_rectify_prompt_content.append({
                        "type": "image_url", 
                        "image_url": {"url": result_ques_url}
                        })
                    final_rectify_prompt_content.append({
                        "type": "text",
                        "text": "The matrix of the question input is: " + str(ques[ques_sig_num])
                        })
                    final_rectify_prompt_content.append({
                        "type": "text",
                        "text": "The matrix of the code output is: " + str(output_result_one_program[ques_sig_num])
                        })
                break_sig_t, break_inst = get_breaking_instruction(breaking_prompt_content, mc)
                if break_sig_t:
                    all_solved_code_filename.append(judge_code_file_name)
                    break_sig_sig = True
                else:
                    print(f"--------Start all examples correct but abnormal code {judge_code_file_name}--------")
                    logging.info(f"Start rectify.")
                    full_response = final_rectify(final_rectify_prompt_content, mc)
                    if full_response == None:
                        print(f"Final rectify failed on {judge_code_file_name}!")
                    else:
                        logging.info(full_response)
                        reasoning = extract_section(full_response, "REASONING:")
                        code = extract_section(full_response, "CODE:")
                        explanation = extract_section(full_response, "EXPLANATION:")
                        # Update dict
                        code_file_dict['code'] = code
                        code_file_dict['code reasoning'] = reasoning
                        code_file_dict['explanation'] = explanation
                        modified_code = modified_code_head + code_file_dict['code'] + modified_code_main
                        with open(judge_code_file_name, "w", encoding='utf-8') as f:
                            f.write(modified_code)
                            print(f"Modified code saved to {judge_code_file_name}")
                            logging.info(f"Modified code saved to {judge_code_file_name}")
            if break_sig_sig:
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
                        "text": "The analogy of the better code:" + best_analogy + "\nThe reason of the analogy:" + best_reason
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
        for code_file_name, code_file_dict in programs_dict.items():
            if code_file_name == 'circulate times':
                continue
            if code_file_dict == None:
                continue
            if code_file_name in all_solved_code_filename_temp:
                print(f"Skip {code_file_name}.")
            else:
                print(f"-------------Start modifying {code_file_name}--------------")
                if code_file_dict['error_signal']:
                    logging.info(f"Start rectifying {code_file_name}.")
                    print(f"Start rectifying {code_file_name}.")
                    rectified_code = rectify_code_file(code_file_dict, mc)
                    if rectified_code != None:
                        code_file_dict['code'] = rectified_code
                        modified_code = modified_code_head + rectified_code + modified_code_main
                        with open(code_file_name, "w", encoding='utf-8') as f:
                            f.write(modified_code)
                        code_file_dict['error_signal'] = False
                        code_file_dict['error_message'] = ""
                        print("Start executing code!")
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
                            stdout, stderr = process.communicate(input=input_json)
                            if process.returncode != 0:
                                error_signal = True
                                error_message = stderr
                                break
                            else:
                                error_signal = False
                                error_message = ""

                            output_json = json.loads(stdout)
                            if output_json == None:
                                error_signal = True
                                error_message = "The output grid is None, which is not valid!"
                                break
                            if len(output_json) == 1:
                                output_json = output_json[0]
                            output_grid_list.append(output_json)
                            code_file_dict['error_signal'] = error_signal
                            code_file_dict['error_message'] = error_message
                        example_result_dict[code_file_name] = output_grid_list
                        continue
                    else:
                        print(f"Rectify code failed! Code filename: {code_file_name}")
                        logging.info(f"Rectify code failed! Code filename: {code_file_name}")
                        continue

                # preparing prompts
                question_prompt_content = [
                        {
                            "type": "text", 
                            "text": question_code_prompt
                            },
                        {
                            "type": "text", 
                            "text": "The analogy of the question:" + code_file_dict['analogy'] + "\nThe reason of the analogy:" + code_file_dict['reason']
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
                            "text": "The analogy of the question:" + code_file_dict['analogy'] + "\nThe reason of the analogy:" + code_file_dict['reason']
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
                            "text": "The analogy of the question:" + code_file_dict['analogy'] + "\nThe reason of the analogy:" + code_file_dict['reason']
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
                            "text": "The analogy of the question:" + code_file_dict['analogy'] + "\nThe reason of the analogy:" + code_file_dict['reason']
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
                            "text": "The analogy of the question:" + code_file_dict['analogy'] + "\nThe reason of the analogy:" + code_file_dict['reason']
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

                # small mutation: add sub-concepts to the existing analogy
                # also known as concepts augmentation
                if random.uniform(0, 1) < small_mutation_rate_dict[code_file_name]:
                    small_mutation_rate_dict[code_file_name] = small_mutation_rate_dict[code_file_name] - 4*delta_small_mutation_rate if small_mutation_rate_dict[code_file_name] - 4*delta_small_mutation_rate > 0 else 0
                    code_file_dict['small mutation rate'] = small_mutation_rate_dict[code_file_name]

                    print(f"-----!!!Attention, small mutation happens on {code_file_name}!!!-----")
                    logging.info(f"-----!!!Attention, small mutation happens on {code_file_name}!!!-----")
                    full_response_small_mutation = augmentation_analogy(small_mutation_prompt_content, mc)
                    if full_response_small_mutation == None:
                        print("-----Small mutation (concept augmentation) Failed!-----")
                        logging.info("-----Small mutation (concept augmentation) Failed.-----")
                    else:
                        logging.info(full_response_small_mutation)
                        small_mutation_reasoning = extract_section(full_response_small_mutation, "REASONING:")
                        small_mutation_analogy = extract_section(full_response_small_mutation, "ANALOGY:")
                        small_mutation_proposals = extract_section(full_response_small_mutation, "PROPOSALS:")
                        augment_analogy_target_dict = parse_answer(small_mutation_analogy, is_format="mutate")
                        if augment_analogy_target_dict == None:
                            print("Parsing small mutation dict failed!")
                            logging.info("Parsing small mutation dict failed.")
                        else:
                            code_file_dict['analogy'] = augment_analogy_target_dict['analogy']
                            code_file_dict['reason'] = augment_analogy_target_dict['reason']
                            question_prompt_content.append({
                                "type": "text",
                                "text": "Attention, the analogy concept might be augmented in this execution. The augmentation details and the modification proposals are shown below: " + small_mutation_proposals 
                                })



                # get instructions
                print("Start getting instructions!")
                logging.info(f"Start getting instructions on {code_file_name}!")
                instruction_reason, instruction_one_program = question_one_program(question_prompt_content, mc)
                instruction_programs_dict[code_file_name] = instruction_one_program
                code_prompt_content.append({
                    "type": "text", 
                    "text": "The modify instructions are below:" + instruction_one_program
                    })

                # crossover codes
                if code_file_name != best_file_name and best_file_name:
                    if random.uniform(0, 1) < crossover_rate:
                        print(f"!!!Attention, crossover happens on {code_file_name}!!!")
                        logging.info(f"!!!Attention, crossover happens on {code_file_name}!!!")
                        for best_code_content_dict in best_code_prompt_content:
                            crossover_prompt_content.append(best_code_content_dict)
                        full_response_crossover_instructions = crossover_two_programs(crossover_prompt_content, mc)
                        if full_response_crossover_instructions != None:
                            logging.info(full_response_crossover_instructions)
                            crossover_reasoning = extract_section(full_response_crossover_instructions, "REASONING:")
                            crossover_instructions = extract_section(full_response_crossover_instructions, "INSTRUCTIONS:")
                            code_prompt_content.append({
                                "type": "text", 
                                "text": "The modify instructions from analyzing the better code are below:" + crossover_instructions
                                })
                        else:
                            print("Crossover failed!")
                            logging.info("Crossover failed.")

                # finding abnormal part of the results
                logging.info(f"Finding abnormal part of the results on {code_file_name}.")
                full_response_abnormal_instructions = finding_abnormal_from_result(abnormal_prompt_content, mc)
                if full_response_abnormal_instructions !=None:
                    logging.info(full_response_abnormal_instructions)
                    abnormal_reasoning = extract_section(full_response_abnormal_instructions, "REASONING:")
                    abnormal_instructions = extract_section(full_response_abnormal_instructions, "INSTRUCTIONS:")
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
                full_response_modifying = modify_one_program(code_prompt_content, mc)
                logging.info(full_response_modifying)
                reasoning = extract_section(full_response_modifying, "REASONING:")
                code = extract_section(full_response_modifying, "CODE:")
                explanation = extract_section(full_response_modifying, "EXPLANATION:")

                # mutation codes: change the analogy target and reasons, then modifying the code
                if random.uniform(0, 1) < mutation_rate_dict[code_file_name]:
                    mutation_rate_dict[code_file_name] = mutation_rate_dict[code_file_name] - 4*delta_mutation_rate if mutation_rate_dict[code_file_name] - 4*delta_mutation_rate > 0 else 0
                    code_file_dict['mutation rate'] = mutation_rate_dict[code_file_name]

                    print(f"!!!Attention, mutation happens on {code_file_name}!!!")
                    logging.info(f"!!!Attention, mutation happens on {code_file_name}!!!")

                    code_file_num = len(programs_dict) - 1
                    other_analogy_and_reason = "Other analogies you can consider and their reasons:"
                    others_analogy_sig = 1
                    for join_code_file_name, join_code_file_dict in programs_dict.items():
                        if join_code_file_name == 'circulate times':
                            continue
                        if join_code_file_dict == None:
                            continue
                        if join_code_file_name != code_file_name:
                            other_analogy_and_reason = other_analogy_and_reason + f"{others_analogy_sig}. The analogy is: {join_code_file_dict['analogy']}  The reason is: {join_code_file_dict['reason']}\n"
                            others_analogy_sig += 1

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
                                "text": "The main analogy you should consider is:" + code_file_dict['analogy'] + "\nThe reason of the analogy:" + code_file_dict['reason']
                                },
                            {
                                "type": "text",
                                "text": other_analogy_and_reason
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
                                "text": "The former analogy:" + code_file_dict['analogy'] + "\nThe reason of the analogy:" + code_file_dict['reason']
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

                    new_code_file_dict = mutate_code_file(mutate_analogy_content, mutate_code_content, mc)
                    if new_code_file_dict == None:
                        print(f"Mutation Failed!")
                        logging.info(f"Mutation Failed!")
                    else:
                        # save file
                        new_code_file_name = programs_dir + "/code"+ str(len(programs_dict) - 1) + "_" + ex_name + ".py"
                        new_modified_code = modified_code_head + new_code_file_dict['code'] + modified_code_main
                        with open(new_code_file_name, "w", encoding='utf-8') as f:
                            f.write(new_modified_code)
                            print(f"Mutation code saved to {new_code_file_name}")
                            logging.info(f"Mutation code saved to {new_code_file_name}")
                        new_code_file_dict['code_file_name'] = new_code_file_name

                        # execute code
                        print(f"-------------Start executing mutation code--------------")
                        output_grid_list = []
                        # compute all of the examples
                        for exs_input_sig in range(len(exs)):
                            input_json = json.dumps(exs[exs_input_sig][0])

                            process = subprocess.Popen(
                                    ['python3', new_code_file_name],
                                    stdin = subprocess.PIPE,
                                    stdout = subprocess.PIPE,
                                    stderr = subprocess.PIPE,
                                    text = True
                                )
                            stdout, stderr = process.communicate(input=input_json)
                            if process.returncode != 0:
                                error_signal = True
                                error_message = stderr
                                break
                            else:
                                error_signal = False
                                error_message = ""

                            output_json = json.loads(stdout)
                            if output_json == None:
                                error_signal = True
                                error_message = "The output grid is None, which is not valid!"
                                break
                            if len(output_json) == 1:
                                output_json = output_json[0]
                            output_grid_list.append(output_json)
                        
                        write_code_dict = {}
                        for key, value in new_code_file_dict.items():
                            write_code_dict[key] = value
                        write_code_dict['error_signal'] = error_signal
                        write_code_dict['error_message'] = error_message
                        write_code_dict['former correct rate'] = 0
                        write_code_dict['mutation rate'] = 0
                        former_correct_rate_dict[new_code_file_name] = 0
                        new_mutate_programs_dict[new_code_file_name] = write_code_dict
                        example_result_dict[new_code_file_name] = output_grid_list
                        mutation_rate_dict[new_code_file_name] = 0
                        small_mutation_rate_dict[new_code_file_name] = 0


                # Update dict
                code_file_dict['code'] = code
                code_file_dict['code reasoning'] = reasoning
                code_file_dict['explanation'] = explanation
                modified_code = modified_code_head + code_file_dict['code'] + modified_code_main
                with open(code_file_name, "w", encoding='utf-8') as f:
                    f.write(modified_code)
                    print(f"Modified code saved to {code_file_name}")
                    logging.info(f"Modified code saved to {code_file_name}")

            # execute code
            print("Start executing code!")
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
                stdout, stderr = process.communicate(input=input_json)
                if process.returncode != 0:
                    error_signal = True
                    error_message = stderr
                    break
                else:
                    error_signal = False
                    error_message = ""

                output_json = json.loads(stdout)
                if output_json == None:
                    error_signal = True
                    error_message = "The output grid is None, which is not valid!"
                    break
                if len(output_json) == 1:
                    output_json = output_json[0]
                output_grid_list.append(output_json)
                code_file_dict['error_signal'] = error_signal
                code_file_dict['error_message'] = error_message
            example_result_dict[code_file_name] = output_grid_list

        programs_dict['circulate times'] = circ_sig + 1
        for mutate_code_file_name, mutate_code_file_dict in new_mutate_programs_dict.items():
            programs_dict[mutate_code_file_name] = mutate_code_file_dict
        with open(programs_dict_file, "w") as f:
            json.dump(program_write_dict, f)
            print(f"Programs already saved to {programs_dict_file}")
            logging.info(f"Programs already saved to {programs_dict_file}")
        programs_dict_file_circ = programs_dir + f'/programs_{ex_name}_circ_{circ_sig+1}.json'
        with open(programs_dict_file_circ, "w") as f:
            json.dump(program_write_dict, f)
            print(f"Programs already saved to {programs_dict_file_circ}")
            logging.info(f"Programs already saved to {programs_dict_file_circ}")


    result_programs_dict = {}
    all_exs_num = len(ques)
    if break_sig:
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
                stdout, stderr = process.communicate(input=input_json)
                if process.returncode != 0:
                    error_signal = True
                    error_message = stderr
                    break
                else:
                    error_signal = False
                    error_message = ""

                output_json = json.loads(stdout)
                if output_json == None:
                    error_signal = True
                    error_message = "The output grid is None, which is not valid!"
                    break
                if len(output_json) == 1:
                    output_json = output_json[0]
                output_grid_list.append(output_json)

            for answer_grid_sig in range(len(output_grid_list)):
                if output_grid_list[answer_grid_sig] == ans[answer_grid_sig]:
                    right_exs_num += 1
            if right_exs_num == all_exs_num:
                print(f"All questions are solved on {ex_name}, by {right_code_file_name}!")
            result_programs_dict[right_code_file_name]['result'] = output_grid_list
            result_programs_dict[right_code_file_name]['all_num'] = all_exs_num
            result_programs_dict[right_code_file_name]['correct_num'] = right_exs_num
            save_vis_data_temp(exs, example_result_dict[right_code_file_name], ques, output_grid_list, 0, right_code_file_name, False)

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
                stdout, stderr = process.communicate(input=input_json)
                if process.returncode != 0:
                    error_signal = True
                    error_message = stderr
                    break
                else:
                    error_signal = False
                    error_message = ""

                output_json = json.loads(stdout)
                if output_json == None:
                    error_signal = True
                    error_message = "The output grid is None, which is not valid!"
                    break
                if len(output_json) == 1:
                    output_json = output_json[0]
                output_grid_list.append(output_json)

            for answer_grid_sig in range(len(output_grid_list)):
                if output_grid_list[answer_grid_sig] == ans[answer_grid_sig]:
                    right_exs_num += 1
            if right_exs_num == all_exs_num:
                print(f"All questions are solved on {ex_name}, by {right_code_file_name}!")
            result_programs_dict[code_file_name]['result'] = output_grid_list
            result_programs_dict[code_file_name]['all_num'] = all_exs_num
            result_programs_dict[code_file_name]['correct_num'] = right_exs_num
            result_programs_dict[code_file_name]['analogy'] = programs_dict[code_file_name]['analogy']
            result_programs_dict[code_file_name]['reason'] = programs_dict[code_file_name]['reason']
            save_vis_data_temp(exs, example_result_dict[code_file_name], ques, output_grid_list, 0, code_file_name, False)

    result_file_name = results_dir + f"/result_{ex_name}.json"
    with open(result_file_name, "w") as f:
        json.dump(result_programs_dict, f)
        print(f"Results already saved to {result_file_name}!")
        logging.info(f"Results already saved to {result_file_name}!")


def test_recog_one_file(recog_prompt, exs_url, mc):
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
    target = answer_dict['Analogy']
    reason = answer_dict['Reason']
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
                        "text": "The deductive rule and reason is provided as below:"
                        },
                    {
                        "type": "text", 
                        "text": "Target rule: " + target
                        },
                    {
                        "type": "text", 
                        "text": "Reason: " + reason
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
            'code reasoning': reasoning,
            'explanation': explanation,
            'code': code
        }


def extract_section(text, section_name):
    """Extract certain part of the text"""
    sections = ["REASONING:", "CODE:", "EXPLANATION:", "INSTRUCTIONS:", "ANALOGY:", "PROPOSALS:"]

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

def vis_difference_grid_for_LLM(example, code_output, diff_mode = False):
    if not diff_mode:
        cmap = ListedColormap(["#FFFFFF","#4A90E2","#50E3C2","#F5A623","#7ED321","#BD10E0","#D0021B","#F8E71C","#8B572A","#000000"])
        fig, axes = plt.subplots(1, 3, figsize=(12, 4))
        plt.suptitle("Visualization", fontsize=20)
        axes[0].pcolormesh(example[0], cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth=0.005)
        axes[0].invert_yaxis()
        axes[0].set_title('example input')
        axes[1].pcolormesh(example[1], cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth=0.005)
        axes[1].invert_yaxis()
        axes[1].set_title('example output, ground truth')
        axes[2].pcolormesh(code_output, cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth=0.005)
        axes[2].invert_yaxis()
        axes[2].set_title('example output, code generate')
    else:
        cmap = ListedColormap(["#FFFFFF","#4A90E2","#50E3C2","#F5A623","#7ED321","#BD10E0","#D0021B","#F8E71C","#8B572A","#000000", "#9E9E9E"])
        fig, axes = plt.subplots(1, 2, figsize=(8, 4))
        plt.suptitle("Visualization difference grid", fontsize=20)
        axes[0].pcolormesh(example, cmap = cmap, vmin = 0, vmax = 10, edgecolors='grey', linewidth=0.005)
        axes[0].invert_yaxis()
        axes[0].set_title('Difference in code generate grid')
        axes[1].pcolormesh(code_output, cmap = cmap, vmin = 0, vmax = 10, edgecolors='grey', linewidth=0.005)
        axes[1].invert_yaxis()
        axes[1].set_title('Difference in ground truth grid')

            
    buf = io.BytesIO()
    fig.savefig(buf, format = 'png', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)

    img_b64 = base64.b64encode(buf.read()).decode('ascii')
    data_url = f"data:image/png;base64,{img_b64}"
    return data_url, img_b64

def vis_result_grid_for_LLM(example, code_output):
    cmap = ListedColormap(["#FFFFFF","#4A90E2","#50E3C2","#F5A623","#7ED321","#BD10E0","#D0021B","#F8E71C","#8B572A","#000000"])
    fig, axes = plt.subplots(1, 2, figsize=(8, 4))
    plt.suptitle("Visualization", fontsize=20)
    axes[0].pcolormesh(example, cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth=0.005)
    axes[0].invert_yaxis()
    axes[0].set_title('example input')
    axes[1].pcolormesh(code_output, cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth=0.005)
    axes[1].invert_yaxis()
    axes[1].set_title('example output, ground truth')

            
    buf = io.BytesIO()
    fig.savefig(buf, format = 'png', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)

    img_b64 = base64.b64encode(buf.read()).decode('ascii')
    data_url = f"data:image/png;base64,{img_b64}"
    return data_url, img_b64

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
        except Exception as e:
            print(e)
            temp_sig += 1
            finished = False
        if finished:
            break
        if temp_sig > 2:
            return None
    full_response = response.choices[0].message.content
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

def mutate_code_file(mutate_analogy_content: list, mutate_code_content: list, mc: str) -> dict:
    com_generate = mutate_analogy(mutate_analogy_content, mc)
    if com_generate == None:
        print(f"Mutate analogy failed!")
        logging.info("Mutate analogy failed!")
        return None
    else:
        logging.info("Mutate analogy successed!")
        logging.info(com_generate)
    analogy_target_dict = parse_answer(com_generate, is_format="mutate")
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
    target = analogy_target_dict['analogy']
    reason = analogy_target_dict['reason']
    mutate_code_content.append({
            "type": "text",
            "text": "The deductive analogy is below:" + target
        })
    mutate_code_content.append({
            "type": "text",
            "text": "The reason of the analogy is below:" + reason
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
            'code reasoning': reasoning,
            'explanation': explanation,
            'code': code
        }

def save_vis_data_temp(exs, exs_ans, ques, ans, circ_sig, code_file_name, temp = True, cot = True):
    abbre_code_file_name = code_file_name.replace("./programs/", "").replace(".py", "")
    cmap = ListedColormap(["#FFFFFF","#4A90E2","#50E3C2","#F5A623","#7ED321","#BD10E0","#D0021B","#F8E71C","#8B572A","#000000"])
    tar_n = len(exs) + len(ques)
    fig, axes = plt.subplots(2, tar_n, figsize=(4 * tar_n, 8))
    plt.suptitle("Visualization", fontsize=20)
    for idx in range(len(exs)):
        axes[0, idx].pcolormesh(exs[idx][0], cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth=0.005)
        axes[0, idx].invert_yaxis()
        axes[0, idx].set_title("example " + f' {idx+1}')
        axes[1, idx].pcolormesh(exs_ans[idx], cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth=0.005)
        axes[1, idx].invert_yaxis()
    for idx in range(len(ques)):
        axes[0, idx+len(exs)].pcolormesh(ques[idx], cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth=0.005)
        axes[0, idx+len(exs)].invert_yaxis()
        axes[0, idx+len(exs)].set_title("test " + f' {idx+1}')
        axes[1, idx+len(exs)].pcolormesh(ans[idx], cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth=0.005)
        axes[1, idx+len(exs)].invert_yaxis()
    if temp:
        plt.savefig(f'./programs/{abbre_code_file_name}_results_circ{circ_sig+1}.png')
        plt.close()
    else:
        if cot:
            code_result_file_name = code_file_name.replace(".json", "")
            plt.savefig(f'{code_result_file_name}.png')
        else:
            plt.savefig(f'./results/{abbre_code_file_name}.png')
        plt.close()

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
            return False, None
    full_response = response.choices[0].message.content
    logging.info(full_response)
    reasoning = extract_section(full_response, "REASONING:")
    prop = extract_section(full_response, "PROPOSALS:")
    prop_dict = parse_answer(prop, is_format = "final")
    if prop_dict['judge'] == "True":
        return True, prop_dict['instruct']
    else:
        return False, prop_dict['instruct']

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

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mc', type=str, default='GPT5', help='model chosen')
    parser.add_argument('--p', type=str, default='t', help='analogy prompted, t or f')
    parser.add_argument('--v', type=str, default='t', help='VL or only Language, t or f')
    parser.add_argument('--of', type=str, default='f', help='one file, t or f')
    parser.add_argument('--file', type=str, default='None', help='file name')
    parser.add_argument('--upc', type=str, default='f', help='whether use prior code, t or f')
    parser.add_argument('--debug', type=str, default='f', help='debugging mode, t or f')
    parser.add_argument('--cot', type=str, default='t', help='debugging mode, t or f')
    args = parser.parse_args()
    data_dir = "./data/"
    if not os.path.exists(data_dir):
        raise ValueError("There is no data directory! All execution will be stopped!")
    if args.of == 'f':
        test_json_grids(data_dir, args.mc, args.p, args.v, args.cot)
    elif args.of == 't':
        for file in ["dye4.json", "wind_and_flag_and_windmill1.json", "cup1.json", "cut_sushi1.json", "fireworks1.json", "hat1.json"]:
           print(f"----------------------------Start execute {file}------------------------------")
           try:
               test_one_file(data_dir, file, args.mc, args.p, args.v, args.upc, args.debug)
           except Exception as e:
               print(e)
               print(f"File name {file}.")
        #test_one_file(data_dir, args.file, args.mc, args.p, args.v, args.upc, args.debug)
