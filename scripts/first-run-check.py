#!/usr/bin/env python3
# scripts/first-run-check.py
"""First-Run Storage Check.

Exit-Code 1 wenn weniger als MIN_FREE_GB frei sind.
Die Advisory-Budget-Tabelle ist rein informativ.
"""
import shutil
import sys

MIN_FREE_GB = 30.0


def main() -> None:
    usage = shutil.disk_usage(".")
    free_gb = usage.free / (1024 ** 3)
    total_gb = usage.total / (1024 ** 3)
    used_pct = (usage.used / usage.total) * 100

    print("=== First-Run Storage Check ===")
    print(f"  Total:  {total_gb:.1f} GB")
    print(f"  Free:   {free_gb:.1f} GB")
    print(f"  Used:   {used_pct:.1f}%")
    print()
    print("--- Advisory Budget ---")
    budgets = {
        "qdrant_data": 10,
        "embedding_cache": 5,
        "vault_content": 20,
        "model_cache": 30,
        "buffer": 5,
    }
    for name, gb in budgets.items():
        print(f"  {name:20s}: ~{gb} GB (advisory only)")
    print(f"  {'total advisory':20s}: ~{sum(budgets.values())} GB")
    print()

    if free_gb < MIN_FREE_GB:
        print(
            f"❌ FEHLER: Weniger als {MIN_FREE_GB} GB frei "
            f"({free_gb:.1f} GB). Bitte Speicher freigeben."
        )
        sys.exit(1)
    print(f"✅ First-Run Check PASSED ({free_gb:.1f} GB frei)")


if __name__ == "__main__":
    main()
