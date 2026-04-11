"""
Run the full pipeline (extract → predict → generate points) for all cities,
one city at a time in separate subprocesses to avoid memory accumulation.

Usage:
    python run_full_pipeline.py [data_dir]
"""

import sys
import os
import glob
import time
import subprocess

DATA_DIR = r"d:\OneDrive - Technion\Research\Shade Maps\Israel trees"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run_step(script, shp_path):
    """Run a pipeline step as a subprocess. Returns True on success."""
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, script), shp_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        print(f"    FAILED (exit {result.returncode})")
        if result.stderr:
            print(f"    {result.stderr[-500:]}")
        return False
    # Print last few lines of output
    lines = result.stdout.strip().split('\n')
    for line in lines[-3:]:
        print(f"    {line}")
    return True


def main():
    data_dir = sys.argv[1] if len(sys.argv) > 1 else DATA_DIR

    # Find all input canopy files (exclude _processed and _predicted)
    pattern = os.path.join(data_dir, '*_tree_canopies_*.shp')
    all_files = sorted(glob.glob(pattern))
    input_files = [f for f in all_files
                   if not f.endswith('_processed.shp') and not f.endswith('_predicted.shp')]

    if not input_files:
        print(f"No *_tree_canopies_*.shp files found in {data_dir}")
        sys.exit(1)

    print(f"Full pipeline for {len(input_files)} cities")
    print(f"Steps: extract_features -> predict_trees -> generate_points")
    print(f"{'='*60}")

    t_total = time.time()
    success = []
    failed = []

    for i, shp in enumerate(input_files):
        city = os.path.basename(shp).split('_tree_canopies_')[0]
        year = os.path.basename(shp).split('_tree_canopies_')[1].replace('.shp', '')
        processed = shp.replace('.shp', '_processed.shp')
        predicted = shp.replace('.shp', '_predicted.shp')

        print(f"\n[{i+1}/{len(input_files)}] {city} ({year})")
        t0 = time.time()

        # Step 1: Extract features
        print(f"  Step 1: Feature extraction...")
        if not run_step('batch_extract_features.py', shp):
            failed.append(city)
            continue

        # Step 2: Predict
        print(f"  Step 2: Tree count prediction...")
        if not run_step('batch_predict_trees.py', processed):
            failed.append(city)
            continue

        # Step 3: Generate points
        print(f"  Step 3: Tree point generation...")
        if not run_step('batch_generate_points.py', predicted):
            failed.append(city)
            continue

        elapsed = time.time() - t0
        success.append(city)
        print(f"  Done ({elapsed:.0f}s)")

    elapsed_total = time.time() - t_total
    print(f"\n{'='*60}")
    print(f"Pipeline complete: {len(success)}/{len(input_files)} cities in {elapsed_total:.0f}s")
    if failed:
        print(f"Failed: {', '.join(failed)}")


if __name__ == '__main__':
    main()
