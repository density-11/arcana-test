import json
import os
import glob
from tqdm import tqdm

def process_single_data(data, data_name):
    if not isinstance(data, dict):
        print(f"The file {data_name} is not a dict!")
        return None
    examples = data.get("train")
    if examples is None:
        examples = data.get("examples")
    if examples is None:
        print(f"The file {data_name} has neither train nor examples!")
        return None
    test = data["test"]
    proc_test = []
    if isinstance(test, dict):
        test = [test]
    for test_ex in test:
        if not isinstance(test_ex, dict):
            print(f"The test of the file {data_name} is not a dict")
        t_proc_ex = {}
        t_input = test_ex["input"]
        t_ans = test_ex["answer"]
        t_proc_ex["input"] = t_input
        t_proc_ex["output"] = t_ans
        proc_test.append(t_proc_ex)

    proc_data = {}
    proc_data["train"] = examples
    proc_data["test"] = proc_test

    return proc_data


def process_all_data(from_dir, to_dir):
    if os.path.exists(from_dir):
        json_files = glob.glob(os.path.join(from_dir, "*.json"))
        for from_file_path in tqdm(json_files):
            try:
                with open(from_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                proc_data = process_single_data(data, from_file_path)
                if proc_data is None:
                    continue
                file_name = from_file_path.replace(from_dir, "").replace("/", "")
                to_file_path = os.path.join(to_dir, file_name)
                with open(to_file_path, "w", encoding='utf-8') as tf:
                    json.dump(proc_data, tf)

            except Exception as e:
                print(f"Error loading {from_file_path}: {e}")

    else:
        print("Process directory not found!")



if __name__ == "__main__":
    from_dir = "data"
    to_dir = "processed_data"
    process_all_data(from_dir, to_dir)
