import argparse
import asyncio
import os
from pathlib import Path

from baseline_runner import batch_test_baseline
from pipeline_runner import generate_pipeline_flow_html_only, test_one_file


def normalize_task_file_argument(file_name):
    if file_name is None:
        return None
    normalized = str(file_name).strip()
    if not normalized or normalized.lower() == "none":
        return normalized
    if normalized.lower().endswith(".json"):
        return normalized[:-5] + ".json"
    return normalized + ".json"


def main():
    script_dir = Path(__file__).resolve().parent
    os.chdir(script_dir)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--mc',
        type=str,
        default=None,
        help=(
            'ARC model key or ID for pipeline and baseline; defaults to GPT5 for '
            'the default API and Qwen (qwen3.5 vision) for uni'
        ),
    )
    parser.add_argument('--of', type=str, default='f', help='one file, t or f, t is pipeline, f is baseline')
    parser.add_argument(
        '--file',
        type=str,
        default='None',
        help='task filename under data/; the .json suffix is optional',
    )
    parser.add_argument('--upc', type=str, default='t', help='whether use prior code, t or f')
    parser.add_argument('--code', type=str, default='f', help='baseline code mode, t or f')
    parser.add_argument('--rerun_code', type=str, default='f', help='rerun saved baseline code locally without API, t or f')
    parser.add_argument('--baseline_output_dir', type=str, default='None', help='baseline output run folder; None creates a new run folder')
    parser.add_argument(
        '--baseline_method',
        choices=('all', 'base', 'cot', 'ana', 'anacot'),
        default='all',
        help='baseline prompt method to run; all preserves the existing four-method behavior',
    )
    parser.add_argument(
        '--pipeline_output_dir',
        type=str,
        default='./pipeline',
        help='pipeline output root containing results, programs, logs, and visualizations',
    )
    parser.add_argument('--html_only', type=str, default='f', help='only regenerate pipeline flow html from saved json, t or f')
    parser.add_argument(
        '--ablation',
        type=str,
        default='none',
        help='pipeline ablation preset: none, direct_targets, or task_name',
    )
    parser.add_argument('--direct_grid', type=str, default='f', help='use direct grid prediction challenger during pipeline break judge, t or f')
    parser.add_argument(
        '--api',
        choices=('default', 'uni'),
        default='default',
        help='API route: default keeps the existing provider; uni uses UNI_BASE_URL and UNI_API_KEY',
    )
    args = parser.parse_args()
    args.file = normalize_task_file_argument(args.file)
    model_chosen = args.mc or ('Qwen' if args.api == 'uni' else 'GPT5')

    if args.html_only == 't':
        generate_pipeline_flow_html_only(
            args.file,
            model_chosen,
            pipeline_dir=args.pipeline_output_dir,
            ablation=args.ablation,
            api_route=args.api,
        )
        return

    if os.path.exists('./data/'):
        data_dir = './data/'
    elif os.path.exists('../data/'):
        data_dir = '../data/'
    else:
        raise ValueError('There is no data directory! All execution will be stopped!')

    if args.of == 'f':
        asyncio.run(batch_test_baseline(
            data_dir,
            code_sig=args.code,
            rerun_code=args.rerun_code,
            use_prior_code=args.upc,
            target_file=args.file,
            output_dir=args.baseline_output_dir,
            api_route=args.api,
            model_chosen=model_chosen,
            baseline_method=args.baseline_method,
        ))
    elif args.of == 't':
        test_one_file(
            data_dir,
            args.file,
            model_chosen,
            args.upc,
            ablation=args.ablation,
            direct_grid=args.direct_grid,
            api_route=args.api,
            pipeline_dir=args.pipeline_output_dir,
        )


if __name__ == '__main__':
    main()
