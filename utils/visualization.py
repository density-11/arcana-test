"""Runtime visualization helpers used by the pipeline and baselines."""

import base64
import io

import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap


ARC_COLORS = [
    "#FFFFFF", "#4A90E2", "#50E3C2", "#F5A623", "#7ED321",
    "#BD10E0", "#D0021B", "#F8E71C", "#8B572A", "#000000",
]


def vis_data_for_VLM(tar, in_out=True):
    cmap = ListedColormap(ARC_COLORS)
    tar_n = len(tar)
    i_o_n = 1
    subtitle = "test question"
    if in_out:
        i_o_n = 2
        subtitle = "train example"
    fig, axes = plt.subplots(i_o_n, tar_n, figsize=(4 * tar_n, 4 * i_o_n))
    plt.suptitle("Visualization", fontsize=20)
    for idx, train_ex in enumerate(tar):
        if in_out:
            axes[0, idx].pcolormesh(
                train_ex[0], cmap=cmap, vmin=0, vmax=9,
                edgecolors="grey", linewidth=0.005,
            )
            axes[0, idx].invert_yaxis()
            axes[0, idx].set_title(f"{subtitle} {idx + 1}")
            axes[1, idx].pcolormesh(
                train_ex[1], cmap=cmap, vmin=0, vmax=9,
                edgecolors="grey", linewidth=0.005,
            )
            axes[1, idx].invert_yaxis()
        elif len(tar) > 1:
            axes[idx].pcolormesh(
                train_ex, cmap=cmap, vmin=0, vmax=9,
                edgecolors="grey", linewidth=0.005,
            )
            axes[idx].invert_yaxis()
            axes[idx].set_title(f"{subtitle} {idx + 1}")
        else:
            axes.pcolormesh(
                train_ex, cmap=cmap, vmin=0, vmax=9,
                edgecolors="grey", linewidth=0.005,
            )
            axes.invert_yaxis()
            axes.set_title(f"{subtitle} {idx + 1}")

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    image_b64 = base64.b64encode(buffer.read()).decode("ascii")
    return f"data:image/png;base64,{image_b64}", image_b64


def vis_difference_grid_for_LLM(example, code_output, diff_mode=False):
    if not diff_mode:
        cmap = ListedColormap(ARC_COLORS)
        fig, axes = plt.subplots(1, 3, figsize=(12, 4))
        plt.suptitle("Visualization", fontsize=20)
        axes[0].pcolormesh(
            example[0], cmap=cmap, vmin=0, vmax=9,
            edgecolors="grey", linewidth=0.005,
        )
        axes[0].invert_yaxis()
        axes[0].set_title("example input")
        axes[1].pcolormesh(
            example[1], cmap=cmap, vmin=0, vmax=9,
            edgecolors="grey", linewidth=0.005,
        )
        axes[1].invert_yaxis()
        axes[1].set_title("example output, ground truth")
        axes[2].pcolormesh(
            code_output, cmap=cmap, vmin=0, vmax=9,
            edgecolors="grey", linewidth=0.005,
        )
        axes[2].invert_yaxis()
        axes[2].set_title("example output, code generate")
    else:
        cmap = ListedColormap(ARC_COLORS + ["#9E9E9E"])
        fig, axes = plt.subplots(1, 2, figsize=(8, 4))
        plt.suptitle("Visualization difference grid", fontsize=20)
        axes[0].pcolormesh(
            example, cmap=cmap, vmin=0, vmax=10,
            edgecolors="grey", linewidth=0.005,
        )
        axes[0].invert_yaxis()
        axes[0].set_title("Difference in code generate grid")
        axes[1].pcolormesh(
            code_output, cmap=cmap, vmin=0, vmax=10,
            edgecolors="grey", linewidth=0.005,
        )
        axes[1].invert_yaxis()
        axes[1].set_title("Difference in ground truth grid")

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    image_b64 = base64.b64encode(buffer.read()).decode("ascii")
    return f"data:image/png;base64,{image_b64}", image_b64


def vis_result_grid_for_LLM(example, code_output):
    cmap = ListedColormap(ARC_COLORS)
    fig, axes = plt.subplots(1, 2, figsize=(8, 4))
    plt.suptitle("Visualization", fontsize=20)
    axes[0].pcolormesh(
        example, cmap=cmap, vmin=0, vmax=9,
        edgecolors="grey", linewidth=0.005,
    )
    axes[0].invert_yaxis()
    axes[0].set_title("example input")
    axes[1].pcolormesh(
        code_output, cmap=cmap, vmin=0, vmax=9,
        edgecolors="grey", linewidth=0.005,
    )
    axes[1].invert_yaxis()
    axes[1].set_title("example output")

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    image_b64 = base64.b64encode(buffer.read()).decode("ascii")
    return f"data:image/png;base64,{image_b64}", image_b64


def save_vis_data_temp(
        exs,
        exs_ans,
        ques,
        ans,
        circ_sig,
        code_file_name,
        temp=True,
        cot=True,
        path=None,
        ):
    abbre_code_file_name = code_file_name.replace("./programs/", "").replace(".py", "")
    cmap = ListedColormap(ARC_COLORS)
    tar_n = len(exs) + len(ques)
    fig, axes = plt.subplots(2, tar_n, figsize=(4 * tar_n, 8))
    plt.suptitle("Visualization", fontsize=20)
    for idx in range(len(exs)):
        axes[0, idx].pcolormesh(
            exs[idx][0], cmap=cmap, vmin=0, vmax=9,
            edgecolors="grey", linewidth=0.005,
        )
        axes[0, idx].invert_yaxis()
        axes[0, idx].set_title(f"example  {idx + 1}")
        axes[1, idx].pcolormesh(
            exs_ans[idx], cmap=cmap, vmin=0, vmax=9,
            edgecolors="grey", linewidth=0.005,
        )
        axes[1, idx].invert_yaxis()
    for idx in range(len(ques)):
        column = idx + len(exs)
        axes[0, column].pcolormesh(
            ques[idx], cmap=cmap, vmin=0, vmax=9,
            edgecolors="grey", linewidth=0.005,
        )
        axes[0, column].invert_yaxis()
        axes[0, column].set_title(f"test  {idx + 1}")
        axes[1, column].pcolormesh(
            ans[idx], cmap=cmap, vmin=0, vmax=9,
            edgecolors="grey", linewidth=0.005,
        )
        axes[1, column].invert_yaxis()
    if path:
        plt.savefig(path)
        plt.close(fig)
        return
    if temp:
        plt.savefig(f"./programs/{abbre_code_file_name}_results_circ{circ_sig + 1}.png")
    elif cot:
        code_result_file_name = code_file_name.replace(".json", "")
        plt.savefig(f"{code_result_file_name}.png")
    else:
        plt.savefig(f"./results/{abbre_code_file_name}.png")
    plt.close(fig)
