"""
Vera AI Challenge — Resumable Submission Generator
===================================================
Generates the required 30-line `submission.jsonl` from `test_pairs.json`
using the 4-Context Composer. Saves line-by-line with real-time flushing.
"""

import json
import time
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from my_work.composer import compose

DATASET_DIR = Path("task/dataset/expanded")
TEST_PAIRS_FILE = DATASET_DIR / "test_pairs.json"
OUTPUT_FILE = Path("submission.jsonl")


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    if not TEST_PAIRS_FILE.exists():
        print(f"Error: {TEST_PAIRS_FILE} not found.", flush=True)
        sys.exit(1)

    pairs_data = load_json(TEST_PAIRS_FILE)
    pairs = pairs_data.get("pairs", [])
    print(f"Found {len(pairs)} canonical test pairs to compose.", flush=True)

    # Check already completed test_ids
    completed_ids = set()
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        completed_ids.add(record.get("test_id"))
                    except Exception:
                        pass
    print(f"Already completed: {len(completed_ids)}/{len(pairs)}", flush=True)

    # Cache categories
    categories = {}
    cat_dir = DATASET_DIR / "categories"
    for cat_file in cat_dir.glob("*.json"):
        cat_data = load_json(cat_file)
        categories[cat_data.get("slug", cat_file.stem)] = cat_data

    with open(OUTPUT_FILE, "a", encoding="utf-8") as out_f:
        for idx, pair in enumerate(pairs, 1):
            test_id = pair["test_id"]
            if test_id in completed_ids:
                continue

            merch_id = pair["merchant_id"]
            trg_id = pair["trigger_id"]
            cust_id = pair.get("customer_id")

            print(f"[{idx}/{len(pairs)}] Composing {test_id} ({merch_id})...", flush=True)

            merch_file = DATASET_DIR / "merchants" / f"{merch_id}.json"
            merchant = load_json(merch_file) if merch_file.exists() else {}

            cat_slug = merchant.get("category_slug", "dentists")
            category = categories.get(cat_slug, {})

            trg_file = DATASET_DIR / "triggers" / f"{trg_id}.json"
            trigger = load_json(trg_file) if trg_file.exists() else {}

            customer = None
            if cust_id:
                cust_file = DATASET_DIR / "customers" / f"{cust_id}.json"
                if cust_file.exists():
                    customer = load_json(cust_file)

            result = compose(category, merchant, trigger, customer)

            record = {
                "test_id": test_id,
                "body": result["body"],
                "cta": result["cta"],
                "send_as": result["send_as"],
                "suppression_key": result["suppression_key"],
                "rationale": result["rationale"],
            }
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_f.flush()

            time.sleep(2.0)

    print(f"\n[DONE] Finished writing submission.jsonl", flush=True)


if __name__ == "__main__":
    main()
