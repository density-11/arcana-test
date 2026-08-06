"""Visualize saved model answers alongside ARCANA task inputs."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap


PROJECT_ROOT = Path(__file__).resolve().parent.parent

def vis_data(file, answer, output_dir=None):
    ans = answer["answer"]
    if "target" in answer:
        tar = answer["target"]
    if len(ans) > 2:
        ans = [ans]
    cmap = ListedColormap(["#FFFFFF","#4A90E2","#50E3C2","#F5A623","#7ED321","#BD10E0","#D0021B","#F8E71C","#8B572A","#000000"])
    task_path = Path(file)
    if not task_path.is_absolute():
        task_path = PROJECT_ROOT / task_path
    with open(task_path, 'r') as f:
        load_dict = json.load(f)
    train_lst = load_dict.get('train')
    if train_lst is None:
        train_lst = load_dict.get('examples', [])
    test_lst = load_dict['test']
    if isinstance(test_lst, dict):
        test_lst = [test_lst]
    train_n = len(train_lst)
    test_n = len(test_lst)
    fig, axes = plt.subplots(2, train_n + test_n, figsize=(4* (train_n + test_n), 8))
    file_name = task_path.stem
    if "target" in answer:
        plt.suptitle(f"GPT5 answer for {file_name}, target:{tar}", fontsize=20)
    else:
        plt.suptitle(f"GPT5 answer visualization for {file_name}", fontsize=20)
    for idx, train_dict in enumerate(train_lst):
        axes[0, idx].pcolormesh(train_dict['input'], cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth=0.005)
        axes[0, idx].invert_yaxis()
        axes[0, idx].set_title(f'train example {idx+1}')
        axes[1, idx].pcolormesh(train_dict['output'], cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth=0.005)
        axes[1, idx].invert_yaxis()
    for idx, test_dict in enumerate(test_lst):
        i = test_dict['input']
        o = ans[idx]
        axes[0, idx+train_n].pcolormesh(i, cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth=0.005)
        axes[0, idx+train_n].invert_yaxis()
        axes[0, idx+train_n].set_title(f'test example {idx+1}')
        axes[1, idx+train_n].pcolormesh(o, cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth=0.005)
        axes[1, idx+train_n].invert_yaxis()
    output_dir = Path(output_dir) if output_dir else PROJECT_ROOT / 'gpt5_one_chance'
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_dir / f'{file_name}.png')
    plt.close()
    
    
if __name__ == "__main__":
    with open(PROJECT_ROOT / 'one_chance_answers.json', 'r') as f:
        ans = json.load(f)
    for file, answer in ans.items():
        try:
            vis_data(file, answer)
        except Exception as e:
            print(e)
            print(file)
