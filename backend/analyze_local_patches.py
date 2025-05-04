import json
import re

PATCHES_PATH = 'all_patches.txt'
METADATA_PATH = 'pr_metadata.json'

# Load PR metadata as a dict keyed by pr_number
with open(METADATA_PATH, 'r', encoding='utf-8') as f:
    metadata_list = json.load(f)
metadata_lookup = {str(item['pr_number']): item for item in metadata_list}

def parse_patches(patches_path):
    """Yield (pr_number, diff) for each PR in the patches file."""
    pr_number = None
    diff_lines = []
    in_pr = False
    pr_start_re = re.compile(r'^===== PR #(\d+) =====$')
    pr_end_re = re.compile(r'^===== END PR #(\d+) =====$')
    with open(patches_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            start_match = pr_start_re.match(line.strip())
            end_match = pr_end_re.match(line.strip())
            if start_match:
                pr_number = start_match.group(1)
                diff_lines = []
                in_pr = True
            elif end_match and in_pr and end_match.group(1) == pr_number:
                # Yield the PR
                yield pr_number, ''.join(diff_lines)
                pr_number = None
                diff_lines = []
                in_pr = False
            elif in_pr:
                diff_lines.append(line)

if __name__ == "__main__":
    for pr_number, diff in parse_patches(PATCHES_PATH):
        meta = metadata_lookup.get(pr_number)
        if not meta:
            print(f"[WARN] No metadata for PR #{pr_number}")
            continue
        print(f"\n=== PR #{pr_number} ===")
        print(f"Title: {meta.get('title')}")
        print(f"Author: {meta.get('author')}")
        print(f"Merged at: {meta.get('merged_at')}")
        print(f"Diff (first 10 lines):\n{''.join(diff.splitlines(True)[:10])}")
        print(f"--- End PR #{pr_number} ---\n") 