"""
ARC Visualization Script
Generates visualization images for ARC (Abstraction and Reasoning Corpus) tasks.
"""

import json
import matplotlib
matplotlib.use('Agg')  # Use non-GUI backend for faster rendering
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
from pathlib import Path

# Color palette for ARC grids
PALETTE = {
    0: "#FFFFFF",  # white
    1: "#4A90E2",  # blue
    2: "#50E3C2",  # teal
    3: "#F5A623",  # orange
    4: "#7ED321",  # green
    5: "#BD10E0",  # purple
    6: "#D0021B",  # red
    7: "#F8E71C",  # yellow
    8: "#8B572A",  # brown
    9: "#000000",  # black
}

# Convert hex to RGB
def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))

# Create RGB palette
RGB_PALETTE = {k: hex_to_rgb(v) for k, v in PALETTE.items()}


def load_json(filepath):
    """Load JSON file and return data."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_test_output(test_item):
    """Return a test answer from either supported ARCANA schema."""
    output = test_item.get('answer')
    if output is None:
        output = test_item.get('output')
    if output is None:
        raise ValueError("Test item has neither an 'answer' nor an 'output' field")
    return output


def parse_data(data, show_question_mark=True):
    """
    Parse the JSON data and return examples and tests.
    
    Returns:
        examples: list of (input, output) tuples
        tests: list of (input, None) tuples (output is question mark)
    """
    examples = []
    tests = []
    
    # Parse examples
    train_examples = data.get('train')
    if train_examples is None:
        train_examples = data.get('examples', [])
    for ex in train_examples:
        if isinstance(ex, dict):
            inp = np.array(ex['input'])
            out = np.array(ex['output'])
            examples.append((inp, out))
    
    # Parse tests
    if 'test' in data:
        test_data = data['test']
        # Could be a single dict or a list of dicts
        if isinstance(test_data, dict):
            # Single test
            inp = np.array(test_data['input'])
            if show_question_mark:
                tests.append((inp, None))
            else:
                out = np.array(get_test_output(test_data))
                tests.append((inp, out))
        elif isinstance(test_data, list):
            # Multiple tests
            for t in test_data:
                inp = np.array(t['input'])
                if show_question_mark:
                    tests.append((inp, None))
                else:
                    out = np.array(get_test_output(t))
                    tests.append((inp, out))
    
    return examples, tests


def draw_grid(ax, grid, cell_size=1.0):
    """
    Draw a single grid on the given axes using imshow for efficiency.
    
    Args:
        ax: matplotlib axes
        grid: 2D numpy array
        cell_size: size of each cell (used for aspect ratio)
    """
    rows, cols = grid.shape
    
    # Create RGB image
    rgb_image = np.zeros((rows, cols, 3))
    for i in range(rows):
        for j in range(cols):
            rgb_image[i, j] = RGB_PALETTE.get(grid[i, j], RGB_PALETTE[0])
    
    # Display image
    ax.imshow(rgb_image, aspect='equal', interpolation='nearest')
    
    # Draw grid lines with grey color
    for i in range(rows + 1):
        ax.axhline(y=i - 0.5, color='grey', linewidth=0.5)
    for j in range(cols + 1):
        ax.axvline(x=j - 0.5, color='grey', linewidth=0.5)
    
    # Set axis properties
    ax.set_xlim(-0.5, cols - 0.5)
    ax.set_ylim(rows - 0.5, -0.5)
    ax.set_aspect('equal')
    ax.set_xticks([])
    ax.set_yticks([])
    ax.axis('off')


def draw_question_mark(ax, rows, cols):
    """
    Draw a question mark placeholder for test output.
    
    Args:
        ax: matplotlib axes
        rows: number of rows in the corresponding input grid
        cols: number of columns in the corresponding input grid
    """
    # Create black background
    black_image = np.zeros((rows, cols, 3))
    ax.imshow(black_image, aspect='equal', interpolation='nearest')
    
    # Draw grid lines with grey color (slightly lighter for visibility on black)
    for i in range(rows + 1):
        ax.axhline(y=i - 0.5, color='#555555', linewidth=0.5)
    for j in range(cols + 1):
        ax.axvline(x=j - 0.5, color='#555555', linewidth=0.5)
    
    # Draw question mark
    ax.text(cols / 2 - 0.5, rows / 2 - 0.5, '?', 
            fontsize=min(rows, cols) * 3,
            color='white',
            ha='center', va='center',
            fontweight='bold')
    
    ax.set_xlim(-0.5, cols - 0.5)
    ax.set_ylim(rows - 0.5, -0.5)
    ax.set_aspect('equal')
    ax.set_xticks([])
    ax.set_yticks([])
    ax.axis('off')


def visualize_arc_task(
        data,
        title,
        output_path,
        items_per_row,
        show_question_mark=True,
        item_max_grid_heights=None,
        ):
    """
    Create visualization for an ARC task.
    
    Args:
        data: parsed JSON data
        title: title for the figure (filename without extension)
        output_path: path to save the output image
        item_max_grid_heights: optional mapping such as {"Ex.4": 3.0}; values
            cap that item's grid height in inches while preserving square cells
    """
    examples, tests = parse_data(data, show_question_mark)
    
    # Calculate layout
    n_examples = len(examples)
    n_tests = len(tests)
    
    # Combine examples and tests into a unified list for sequential placement
    # Each item: (input, output, label_prefix, item_number, is_test)
    all_items = []
    for i, (inp, out) in enumerate(examples):
        all_items.append((inp, out, "Ex.", i + 1, False))
    for i, (inp, out) in enumerate(tests):
        if show_question_mark:
            all_items.append((inp, None, "Test", i + 1 if n_tests > 1 else None, True))
        else:
            all_items.append((inp, out, "Test", i + 1 if n_tests > 1 else None, True))
    
    n_items = len(all_items)
    item_max_grid_heights = item_max_grid_heights or {}
    
    # Lay out up to items_per_row example/test pairs per row.
    total_rows = (n_items + items_per_row - 1) // items_per_row
    
    if total_rows == 0:
        print(f"No data to visualize for {title}")
        return
    
    # Find the maximum grid dimensions to normalize display width
    max_cols = 0
    for item in all_items:
        inp = item[0]
        max_cols = max(max_cols, inp.shape[1])
        if item[1] is not None:
            max_cols = max(max_cols, item[1].shape[1])
    
    # Calculate figure size
    # Each pair takes: input_width + arrow_space + output_width + pair_gap
    # We want all grids to have the same display width
    fixed_grid_display_width = 3.0  # inches for grid display width
    arrow_width = 0.8  # inches for arrow
    pair_internal_gap = 0.3  # gap between input and output within a pair
    pair_gap = 1.2  # gap between pairs in same row
    margin = 0.5  # margin on sides
    label_height = 0.4  # height for labels above grids
    row_gap = 0.6  # gap between rows
    title_height = 0.6  # height for title
    title_margin = 0.3  # margin between title and first row
    
    # Width calculation
    single_pair_width = fixed_grid_display_width * 2 + arrow_width + pair_internal_gap
    fig_width = margin * items_per_row + single_pair_width * items_per_row + pair_gap * (items_per_row - 1)
    
    # Height calculation - need to account for varying grid heights
    def get_item_key(label_prefix, item_num, is_test):
        if is_test:
            return "Test" if item_num is None else f"Test{item_num}"
        return f"{label_prefix}{item_num}"

    def get_display_width(grid, item_key):
        display_width = fixed_grid_display_width
        max_height = item_max_grid_heights.get(item_key)
        if max_height is not None:
            rows, cols = grid.shape
            natural_height = rows * display_width / cols
            if natural_height > max_height:
                display_width *= max_height / natural_height
        return display_width

    def get_display_height(grid, display_width):
        rows, cols = grid.shape
        cell_size = display_width / cols
        return rows * cell_size
    
    # Calculate max height for each row (unified for examples and tests)
    row_heights = []
    
    for row_idx in range(total_rows):
        max_height = 0
        for col_idx in range(items_per_row):
            item_idx = row_idx * items_per_row + col_idx
            if item_idx < n_items:
                inp, out, label_prefix, item_num, is_test = all_items[item_idx]
                item_key = get_item_key(label_prefix, item_num, is_test)
                inp_width = get_display_width(inp, item_key)
                h1 = get_display_height(inp, inp_width)
                if out is not None:
                    out_width = get_display_width(out, item_key)
                    h2 = get_display_height(out, out_width)
                else:
                    h2 = h1
                max_height = max(max_height, h1, h2)
        row_heights.append(max_height)
    
    # Add bottom margin
    bottom_margin = 0.3
    fig_height = title_height + title_margin + sum(row_heights) + len(row_heights) * (label_height + row_gap) + bottom_margin
    
    # Create figure
    fig = plt.figure(figsize=(fig_width, fig_height), facecolor='white')
    
    # Add title at top (closer to content)
    title_y = (fig_height - title_height / 2 - 0.1) / fig_height
    fig.text(0.5, title_y, title, fontsize=16, fontweight='bold', ha='center', va='center')
    
    # Helper function to draw a pair (input -> output) with gray background
    def draw_pair(fig, inp, out, label_prefix, pair_num, x_start, y_top, row_height, is_test=False):
        """Draw a pair of input/output grids with arrow.
        
        y_top: the y position (in inches from bottom of figure) of the TOP of this row area
        """
        
        # Calculate grid dimensions
        item_key = get_item_key(label_prefix, pair_num, is_test)
        inp_rows, inp_cols = inp.shape
        inp_display_width = get_display_width(inp, item_key)
        inp_cell_size = inp_display_width / inp_cols
        inp_height = inp_rows * inp_cell_size
        
        if out is not None:
            out_rows, out_cols = out.shape
            out_display_width = get_display_width(out, item_key)
            out_cell_size = out_display_width / out_cols
            out_height = out_rows * out_cell_size
        else:
            # For question mark, use same dimensions as input
            out_display_width = inp_display_width
            out_height = inp_height
        
        # y_top is top of label area, grid area is below labels
        grid_area_top = y_top - label_height
        grid_area_bottom = grid_area_top - row_height
        
        # Background dimensions (in figure fraction)
        bg_width = single_pair_width + 0.2
        bg_height_inches = row_height + label_height + 0.2
        
        # Normalize to figure coordinates (0 to 1)
        bg_x = (x_start - 0.1) / fig_width
        bg_y = (grid_area_bottom - 0.1) / fig_height  # bottom of background
        bg_w = bg_width / fig_width
        bg_h = bg_height_inches / fig_height
        
        # Draw gray background
        bg_rect = patches.FancyBboxPatch(
            (bg_x, bg_y), bg_w, bg_h,
            boxstyle="round,pad=0.01,rounding_size=0.02",
            facecolor='#E8E8E8',
            edgecolor='none',
            transform=fig.transFigure,
            zorder=0
        )
        fig.patches.append(bg_rect)
        
        # Center grids vertically within the row_height area
        inp_y_offset = (row_height - inp_height) / 2
        out_y_offset = (row_height - out_height) / 2
        
        # Input grid position (in figure fraction)
        inp_x_start = x_start + (fixed_grid_display_width - inp_display_width) / 2
        inp_x = inp_x_start / fig_width
        inp_bottom = grid_area_bottom + inp_y_offset
        inp_y = inp_bottom / fig_height
        inp_w = inp_display_width / fig_width
        inp_h = inp_height / fig_height
        
        ax_inp = fig.add_axes([inp_x, inp_y, inp_w, inp_h])
        ax_inp.set_zorder(10)  # Ensure grid is above background
        draw_grid(ax_inp, inp)
        
        # Input label (above the grid area)
        if is_test:
            # If pair_num is None, there's only one test; otherwise show number
            inp_label = "Test Input" if pair_num is None else f"Test{pair_num} Input"
        else:
            inp_label = f"Ex.{pair_num} Input"
        
        label_y = (grid_area_top + label_height * 0.4) / fig_height
        inp_label_x = (x_start + fixed_grid_display_width / 2) / fig_width
        fig.text(inp_label_x, label_y, inp_label,
                ha='center', va='center', fontsize=10, fontweight='bold')
        
        # Arrow position (in the middle of the row)
        arrow_x_pos = x_start + fixed_grid_display_width + pair_internal_gap / 2 + arrow_width / 2
        arrow_y_pos = grid_area_bottom + row_height / 2
        
        fig.text(arrow_x_pos / fig_width, arrow_y_pos / fig_height, '→',
                ha='center', va='center', fontsize=24, fontweight='bold')
        
        # Output grid position
        out_slot_start = x_start + fixed_grid_display_width + pair_internal_gap + arrow_width
        out_x_start = out_slot_start + (fixed_grid_display_width - out_display_width) / 2
        out_x = out_x_start / fig_width
        out_bottom = grid_area_bottom + out_y_offset
        out_y = out_bottom / fig_height
        out_w = out_display_width / fig_width
        out_h = out_height / fig_height
        
        ax_out = fig.add_axes([out_x, out_y, out_w, out_h])
        ax_out.set_zorder(10)  # Ensure grid is above background
        
        if out is not None:
            draw_grid(ax_out, out)
        else:
            # Use input dimensions for question mark
            draw_question_mark(ax_out, inp_rows, inp_cols)
        
        # Output label
        if is_test:
            out_label = "Test Output" if pair_num is None else f"Test{pair_num} Output"
        else:
            out_label = f"Ex.{pair_num} Output"
        
        out_label_x = (out_slot_start + fixed_grid_display_width / 2) / fig_width
        fig.text(out_label_x, label_y, out_label,
                ha='center', va='bottom', fontsize=10, fontweight='bold')
    
    # Draw all examples and tests from top to bottom (unified placement)
    current_y_top = fig_height - title_height - title_margin  # Start below title
    
    for row_idx in range(total_rows):
        row_h = row_heights[row_idx]
        
        for col_idx in range(items_per_row):
            item_idx = row_idx * items_per_row + col_idx
            if item_idx < n_items:
                x_start = margin + col_idx * (single_pair_width + pair_gap)
                inp, out, label_prefix, item_num, is_test = all_items[item_idx]
                # item_num is None for single test, otherwise it's the test number
                draw_pair(fig, inp, out, label_prefix, item_num, x_start, current_y_top, row_h, is_test=is_test)
        
        current_y_top -= (row_h + label_height + row_gap)
    
    # Save figure
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close(fig)
    print(f"Saved: {output_path}")


def main():
    """Main function to process all JSON files."""
    # Define paths
    project_root = Path(__file__).resolve().parent.parent
    input_dir = project_root / "data"
    output_dir = project_root / "data_visualization_full"
    
    # Create output directory if it doesn't exist
    output_dir.mkdir(exist_ok=True)
    
    # Find all JSON files
    json_files = list(input_dir.glob("*.json"))
    print(f"Found {len(json_files)} JSON files to process")
    
    # Define hyperparameter
    items_per_row = 2
    show_question_mark = False

    # Process each file
    for json_path in json_files:
        try:
            # Get filename without extension
            title = json_path.stem
            
            # Load data
            data = load_json(json_path)
            
            # Output path
            output_path = output_dir / f"{title}.png"
            
            # Visualize
            visualize_arc_task(data, title, output_path, items_per_row, show_question_mark)
            
        except Exception as e:
            print(f"Error processing {json_path}: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\nDone! All visualizations saved to {output_dir}")


if __name__ == "__main__":
    main()
