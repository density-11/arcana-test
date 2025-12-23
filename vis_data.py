import numpy as np
import os
import json
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.ticker import MaxNLocator
from matplotlib.colors import ListedColormap
from tqdm import tqdm
import ipdb

def vis_data(file, f_name):
    values = np.linspace(0,1,10)
    cmap = ListedColormap(["#FFFFFF", "#4A90E2", "#50E3C2", "#F5A623", "#7ED321", "#BD10E0", "#D0021B", "#F8E71C", "#8B572A", "#000000"])
    with open(file, 'r') as f:
        load_dict = json.load(f)
    train_lst = load_dict['examples']
    test_lst = load_dict['test']
    if not isinstance(test_lst, list):
        test_lst = [test_lst]
    train_n = len(train_lst)
    test_n = len(test_lst)
    all_x = 0
    avg_y = len(train_lst[0]["input"])
    for example in train_lst:
        all_x += len(example["input"][0])
    for test in test_lst:
        all_x += len(test["input"][0])
    avg_x = all_x / (train_n + test_n)
    len_y = 4
    len_x = avg_x / avg_y * len_y

    fig, axes = plt.subplots(2, train_n + test_n, figsize=(len_x * (train_n + test_n), 2 * len_y))
    plt.suptitle(f_name, fontsize=20)

    for idx, train_dict in enumerate(train_lst):
        axes[0, idx]. pcolormesh(train_dict['input'], cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth = 0.005)
        axes[0, idx].invert_yaxis()
        axes[0, idx].set_title(f'train example {idx+1}')
        axes[1, idx]. pcolormesh(train_dict['output'], cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth = 0.005)
        axes[1, idx].invert_yaxis()
        axes[0, idx].xaxis.set_major_locator(MaxNLocator(steps=[2,3,5,10]))
        axes[0, idx].yaxis.set_major_locator(MaxNLocator(steps=[2,3,5,10]))
        axes[1, idx].xaxis.set_major_locator(MaxNLocator(steps=[2,3,5,10]))
        axes[1, idx].yaxis.set_major_locator(MaxNLocator(steps=[2,3,5,10]))
    for idx, test_dict in enumerate(test_lst):
        axes[0, idx+train_n].pcolormesh(test_dict['input'], cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth = 0.005)
        axes[0, idx+train_n].invert_yaxis()
        axes[0, idx+train_n].set_title(f'test example {idx+1}')
        axes[1, idx+train_n].pcolormesh(test_dict['answer'], cmap = cmap, vmin = 0, vmax = 9, edgecolors='grey', linewidth = 0.005)
        axes[1, idx+train_n].invert_yaxis()
        axes[0, idx+train_n].xaxis.set_major_locator(MaxNLocator(steps=[2,3,5,10]))
        axes[0, idx+train_n].yaxis.set_major_locator(MaxNLocator(steps=[2,3,5,10]))
        axes[1, idx+train_n].xaxis.set_major_locator(MaxNLocator(steps=[2,3,5,10]))
        axes[1, idx+train_n].yaxis.set_major_locator(MaxNLocator(steps=[2,3,5,10]))
    plt.savefig(f'./arcana_pic/{f_name}.png')
    plt.close()


path = './data'
if not os.path.exists("./arcana_pic"):
    os.makedirs("./arcana_pic")
for file in tqdm(os.listdir(path)):
    f_name = file.replace('.json', '')
    file = path + '/' + file
    vis_data(file, f_name)
