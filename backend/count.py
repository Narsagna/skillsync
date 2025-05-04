import re

def extract_pr_numbers(filepath):
    pr_numbers = []
    pattern = re.compile(r"===== PR #(\d+) =====")
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            match = pattern.match(line.strip())
            if match:
                pr_numbers.append(match.group(1))
    return pr_numbers

if __name__ == "__main__":
    import sys
    # Default path is all_patches.txt in the same directory as the script
    path = sys.argv[1] if len(sys.argv) > 1 else "all_patches.txt"
    pr_numbers = extract_pr_numbers(path)
    print("\n".join(pr_numbers)) 