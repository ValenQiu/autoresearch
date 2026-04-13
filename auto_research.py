"""
Automate research experiments from a task JSON file.

This script mutates top-level hyperparameters in train.py, runs experiments,
parses metrics from logs, and writes a machine-readable result table.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import itertools
import json
import random
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_COMMAND = "uv run train.py"
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_SEED = 42

METRIC_KEYS = (
    "val_bpb",
    "training_seconds",
    "total_seconds",
    "peak_vram_mb",
    "mfu_percent",
    "total_tokens_M",
    "num_steps",
    "num_params_M",
    "depth",
)

ASSIGNMENT_RE = re.compile(
    r"^(?P<indent>\s*)(?P<name>[A-Z][A-Z0-9_]*)\s*=\s*(?P<value>.*?)(?P<comment>\s+#.*)?$",
    re.MULTILINE,
)
METRIC_RE = re.compile(r"^(?P<key>[a-zA-Z0-9_]+):\s+(?P<value>.+?)\s*$", re.MULTILINE)


@dataclass
class RunResult:
    run_id: str
    status: str
    return_code: int
    duration_seconds: float
    metrics: dict[str, float | int | str]
    config: dict[str, Any]
    log_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automatic research runner")
    parser.add_argument("--task", required=True, help="Path to a task JSON file")
    parser.add_argument(
        "--output-dir",
        default="research_runs",
        help="Directory for logs and results",
    )
    parser.add_argument(
        "--train-file",
        default="train.py",
        help="Training file to mutate (default: train.py)",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=None,
        help="Optional hard cap overriding task max_runs",
    )
    parser.add_argument(
        "--apply-best",
        action="store_true",
        help="Apply the best config to train.py when done",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print planned runs, do not execute",
    )
    return parser.parse_args()


def load_task(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        task = json.load(f)

    if "search" not in task or "parameters" not in task["search"]:
        raise ValueError("task.search.parameters is required")
    if not isinstance(task["search"]["parameters"], dict) or not task["search"]["parameters"]:
        raise ValueError("task.search.parameters must be a non-empty object")
    if task.get("objective", {}).get("metric", "val_bpb") != "val_bpb":
        raise ValueError("only objective.metric=val_bpb is currently supported")
    return task


def format_value_for_python(value: Any) -> str:
    if isinstance(value, dict) and "python" in value:
        return value["python"]
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "True" if value else "False"
    if value is None:
        return "None"
    return repr(value)


def normalize_value(value: Any) -> Any:
    if isinstance(value, dict) and "python" in value:
        return {"python": value["python"]}
    return value


def candidate_id(config: dict[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]


def build_candidates(task: dict[str, Any], hard_cap: int | None) -> list[dict[str, Any]]:
    search = task["search"]
    params: dict[str, list[Any]] = search["parameters"]
    method = search.get("method", "grid")
    seed = int(search.get("seed", DEFAULT_SEED))

    names = list(params.keys())
    values = [params[name] for name in names]
    if not all(isinstance(v, list) and v for v in values):
        raise ValueError("every parameter must have a non-empty list of candidate values")

    combos: list[dict[str, Any]] = [
        {name: normalize_value(value) for name, value in zip(names, combo)}
        for combo in itertools.product(*values)
    ]

    max_runs = hard_cap if hard_cap is not None else search.get("max_runs")
    if method == "random":
        rng = random.Random(seed)
        rng.shuffle(combos)
    elif method != "grid":
        raise ValueError("search.method must be either 'grid' or 'random'")

    if max_runs is not None:
        combos = combos[: int(max_runs)]
    return combos


def patch_train_file(content: str, overrides: dict[str, Any]) -> str:
    found: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        if name not in overrides:
            return match.group(0)
        found.add(name)
        indent = match.group("indent") or ""
        comment = match.group("comment") or ""
        new_value = format_value_for_python(overrides[name])
        return f"{indent}{name} = {new_value}{comment}"

    updated = ASSIGNMENT_RE.sub(replace, content)
    missing = sorted(set(overrides) - found)
    if missing:
        raise ValueError(f"parameter(s) not found in train.py: {', '.join(missing)}")
    return updated


def parse_metrics(log_text: str) -> dict[str, float | int | str]:
    metrics: dict[str, float | int | str] = {}
    for match in METRIC_RE.finditer(log_text):
        key = match.group("key")
        if key not in METRIC_KEYS:
            continue
        raw = match.group("value")
        try:
            if "." in raw:
                metrics[key] = float(raw)
            else:
                metrics[key] = int(raw)
        except ValueError:
            metrics[key] = raw
    return metrics


def append_tsv(path: Path, row: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8") as f:
        if not exists:
            f.write(
                "run_id\ttimestamp\tstatus\tval_bpb\tpeak_vram_mb\treturn_code\tduration_s\tconfig_json\tlog_file\n"
            )
        f.write("\t".join(row) + "\n")


def load_completed_run_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    if len(lines) <= 1:
        return set()
    return {ln.split("\t", 1)[0] for ln in lines[1:]}


def run_once(
    run_id: str,
    config: dict[str, Any],
    train_path: Path,
    train_base: str,
    run_dir: Path,
    command: str,
    timeout_seconds: int,
) -> RunResult:
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / f"{run_id}.log"

    patched = patch_train_file(train_base, config)
    train_path.write_text(patched, encoding="utf-8")

    started = time.time()
    status = "crash"
    return_code = -999
    try:
        with log_path.open("w", encoding="utf-8") as log_f:
            completed = subprocess.run(
                command,
                shell=True,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                check=False,
            )
        return_code = completed.returncode
        status = "ok" if completed.returncode == 0 else "crash"
    except subprocess.TimeoutExpired:
        with log_path.open("a", encoding="utf-8") as log_f:
            log_f.write(f"\n[TIMEOUT] command exceeded {timeout_seconds} seconds\n")
        status = "timeout"
        return_code = 124

    duration = time.time() - started
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    metrics = parse_metrics(log_text)
    if "val_bpb" not in metrics:
        status = "crash" if status == "ok" else status
    return RunResult(
        run_id=run_id,
        status=status,
        return_code=return_code,
        duration_seconds=duration,
        metrics=metrics,
        config=config,
        log_path=log_path,
    )


def pick_best(results: list[RunResult]) -> RunResult | None:
    ok = [r for r in results if r.status == "ok" and isinstance(r.metrics.get("val_bpb"), float)]
    if not ok:
        return None
    return min(ok, key=lambda r: float(r.metrics["val_bpb"]))


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parent
    task_path = (root / args.task).resolve() if not Path(args.task).is_absolute() else Path(args.task)
    train_path = (root / args.train_file).resolve() if not Path(args.train_file).is_absolute() else Path(args.train_file)
    output_root = (root / args.output_dir).resolve() if not Path(args.output_dir).is_absolute() else Path(args.output_dir)

    task = load_task(task_path)
    task_name = task.get("task_name") or task_path.stem
    safe_task_name = re.sub(r"[^a-zA-Z0-9_.-]+", "-", task_name.strip()) or "task"
    run_dir = output_root / safe_task_name
    results_tsv = run_dir / "results.tsv"
    summary_json = run_dir / "summary.json"

    command = task.get("command", DEFAULT_COMMAND)
    timeout_seconds = int(task.get("constraints", {}).get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    candidates = build_candidates(task, args.max_runs)
    done_ids = load_completed_run_ids(results_tsv)
    train_base = train_path.read_text(encoding="utf-8")

    print(f"Task: {task_name}")
    print(f"Candidates planned: {len(candidates)}")
    if args.dry_run:
        for idx, cfg in enumerate(candidates, start=1):
            print(f"  {idx:03d}. {candidate_id(cfg)} {cfg}")
        return

    results: list[RunResult] = []
    try:
        for idx, config in enumerate(candidates, start=1):
            run_id = candidate_id(config)
            if run_id in done_ids:
                print(f"[{idx:03d}/{len(candidates):03d}] skip {run_id} (already recorded)")
                continue
            print(f"[{idx:03d}/{len(candidates):03d}] run  {run_id} {config}")
            result = run_once(
                run_id=run_id,
                config=config,
                train_path=train_path,
                train_base=train_base,
                run_dir=run_dir,
                command=command,
                timeout_seconds=timeout_seconds,
            )
            results.append(result)
            val_bpb = result.metrics.get("val_bpb", "NA")
            peak_vram_mb = result.metrics.get("peak_vram_mb", "NA")
            append_tsv(
                results_tsv,
                [
                    result.run_id,
                    dt.datetime.now().isoformat(timespec="seconds"),
                    result.status,
                    str(val_bpb),
                    str(peak_vram_mb),
                    str(result.return_code),
                    f"{result.duration_seconds:.1f}",
                    json.dumps(result.config, ensure_ascii=True, separators=(",", ":")),
                    result.log_path.name,
                ],
            )
            print(
                f"      -> status={result.status} val_bpb={val_bpb} peak_vram_mb={peak_vram_mb} "
                f"duration={result.duration_seconds:.1f}s"
            )
    finally:
        train_path.write_text(train_base, encoding="utf-8")

    best = pick_best(results)
    summary = {
        "task_name": task_name,
        "new_runs": len(results),
        "best": None,
        "results_tsv": str(results_tsv),
    }
    if best is not None:
        summary["best"] = {
            "run_id": best.run_id,
            "val_bpb": best.metrics["val_bpb"],
            "peak_vram_mb": best.metrics.get("peak_vram_mb"),
            "config": best.config,
            "log_file": str(best.log_path),
        }
        print(f"Best run: {best.run_id} val_bpb={best.metrics['val_bpb']}")
        if args.apply_best:
            applied = patch_train_file(train_base, best.config)
            train_path.write_text(applied, encoding="utf-8")
            print(f"Applied best config to {train_path}")
    else:
        print("No successful runs produced val_bpb.")

    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Wrote summary: {summary_json}")


if __name__ == "__main__":
    main()
