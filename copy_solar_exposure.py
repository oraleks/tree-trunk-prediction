"""
Copy solar exposure rasters (XXX_all_kdown_1999_218.tif) from each
city folder to a central folder.

For each city in Israel_shade_maps/:
- Find the file named XXX_all_kdown_1999_218.tif (case-insensitive) inside the city folder
- If multiple matches, copy the most recent one (by mtime)
- If none found, record it in the missing report

Output:
    d:/OneDrive - Technion/Research/Shade Maps/Israel solar exposure/<file>.tif
    d:/OneDrive - Technion/Research/Shade Maps/Israel solar exposure/missing_files_report.txt
"""

import os
import re
import glob
import shutil
from datetime import datetime

SOURCE_DIR = r"d:\OneDrive - Technion\Research\Shade Maps\Israel_shade_maps"
DEST_DIR = r"d:\OneDrive - Technion\Research\Shade Maps\Israel solar exposure"
REPORT_FILE = os.path.join(DEST_DIR, "missing_files_report.txt")

# Filename patterns (case-insensitive):
#   Primary:  XXX_all_kdown_1999_218.tif (exact)
#   Fallback: XXX_all_kdown_1999_218_SUM.tif (cumulative sum of hourly rasters)
FNAME_PATTERN = re.compile(r'^([A-Za-z0-9]{2,4})_all_kdown_1999_218\.tif$', re.IGNORECASE)
FNAME_SUM_PATTERN = re.compile(r'^([A-Za-z0-9]{2,4})_all_kdown_1999_218_SUM\.tif$', re.IGNORECASE)

# Exclude paths containing these folder names (variants, not the primary kdown folder)
EXCLUDE_FOLDERS = ['kdown_no_trees']


def find_city_folders(source_dir):
    """Return list of city folders (top-level directories only)."""
    return sorted([
        os.path.join(source_dir, d) for d in os.listdir(source_dir)
        if os.path.isdir(os.path.join(source_dir, d))
    ])


def find_kdown_files(city_folder, pattern):
    """Find all files matching the given pattern in a city folder.
    Excludes paths containing folders in EXCLUDE_FOLDERS (e.g. kdown_no_trees)."""
    matches = []
    for root, dirs, files in os.walk(city_folder):
        # Skip excluded subfolders
        dirs[:] = [d for d in dirs if d not in EXCLUDE_FOLDERS]
        for f in files:
            if pattern.match(f):
                matches.append(os.path.join(root, f))
    return matches


def main():
    os.makedirs(DEST_DIR, exist_ok=True)

    city_folders = find_city_folders(SOURCE_DIR)
    print(f"Scanning {len(city_folders)} folders in {SOURCE_DIR}")
    print(f"Destination: {DEST_DIR}")
    print("=" * 60)

    copied = []
    copied_sum = []
    missing = []
    multiple = []

    for folder in city_folders:
        city_name = os.path.basename(folder)

        # Try primary pattern first
        matches = find_kdown_files(folder, FNAME_PATTERN)
        source_type = "primary"

        # Fallback to _SUM.tif if no primary file found
        if not matches:
            matches = find_kdown_files(folder, FNAME_SUM_PATTERN)
            source_type = "SUM"

        if not matches:
            missing.append(city_name)
            print(f"  [MISSING] {city_name}")
            continue

        if len(matches) > 1:
            matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            multiple.append((city_name, matches))
            selected = matches[0]
            tag = f"MULTIPLE:{len(matches)},{source_type}"
            print(f"  [{tag}] {city_name} -> most recent:")
            for i, m in enumerate(matches):
                marker = '*' if i == 0 else ' '
                mtime = datetime.fromtimestamp(os.path.getmtime(m)).strftime('%Y-%m-%d %H:%M')
                print(f"      {marker} {mtime}  {m}")
        else:
            selected = matches[0]
            tag = "OK" if source_type == "primary" else "OK-SUM"
            print(f"  [{tag}] {city_name}: {os.path.basename(selected)}")

        dest_name = os.path.basename(selected)
        dest_path = os.path.join(DEST_DIR, dest_name)
        shutil.copy2(selected, dest_path)
        copied.append((city_name, dest_name, selected, source_type))
        if source_type == "SUM":
            copied_sum.append(city_name)

    # Write missing report
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(f"Solar Exposure File Collection Report\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Source: {SOURCE_DIR}\n")
        f.write(f"Destination: {DEST_DIR}\n")
        f.write(f"{'='*70}\n\n")

        f.write(f"SUMMARY\n")
        f.write(f"  Total city folders scanned: {len(city_folders)}\n")
        f.write(f"  Files copied (total): {len(copied)}\n")
        f.write(f"    - Primary file (XXX_all_kdown_1999_218.tif): {len(copied) - len(copied_sum)}\n")
        f.write(f"    - SUM fallback (XXX_all_kdown_1999_218_SUM.tif): {len(copied_sum)}\n")
        f.write(f"  Missing: {len(missing)}\n")
        f.write(f"  Cities with multiple candidates (most recent copied): {len(multiple)}\n\n")

        f.write(f"MISSING FILES\n")
        f.write(f"-" * 70 + "\n")
        if missing:
            f.write(f"The following {len(missing)} city folders do not contain "
                    f"XXX_all_kdown_1999_218.tif:\n\n")
            for city in missing:
                f.write(f"  - {city}\n")
        else:
            f.write("None - all city folders contained the expected file.\n")
        f.write("\n")

        f.write(f"COPIED FILES\n")
        f.write(f"-" * 70 + "\n")
        for city, fname, src, src_type in copied:
            tag = "[SUM]" if src_type == "SUM" else "     "
            f.write(f"  {tag} {city:<25s} -> {fname}\n")
            f.write(f"          from: {src}\n")
        f.write("\n")

        if multiple:
            f.write(f"MULTIPLE MATCHES (most recent was copied)\n")
            f.write(f"-" * 70 + "\n")
            for city, matches in multiple:
                f.write(f"\n  {city}:\n")
                for i, m in enumerate(matches):
                    mtime = datetime.fromtimestamp(os.path.getmtime(m)).strftime('%Y-%m-%d %H:%M')
                    marker = '[COPIED]' if i == 0 else '[SKIPPED]'
                    f.write(f"    {marker} {mtime}  {m}\n")

    print(f"\n{'='*60}")
    print(f"Done.")
    print(f"  Copied:   {len(copied)}")
    print(f"  Missing:  {len(missing)}")
    print(f"  Multiple: {len(multiple)}")
    print(f"  Report:   {REPORT_FILE}")


if __name__ == '__main__':
    main()
