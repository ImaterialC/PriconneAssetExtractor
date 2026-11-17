#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_all_tests.py - Test runner across all Priconne ADV & Data Miner test suites
"""
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    print("======================================================================")
    print("  PRINCESS CONNECT! RE:DIVE - FULL TEST SUITE VERIFICATION")
    print("======================================================================\n")

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Discover and add test suites
    tests_dir = Path(__file__).resolve().parent
    suite.addTests(loader.discover(start_dir=str(tests_dir), pattern="test_*.py", top_level_dir=str(tests_dir)))

    misora_tests = PROJECT_ROOT / "misora" / "tests"
    if misora_tests.exists():
        suite.addTests(loader.discover(start_dir=str(misora_tests), pattern="test_*.py", top_level_dir=str(PROJECT_ROOT)))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n======================================================================")
    if result.wasSuccessful():
        print("  ALL TESTS PASSED SUCCESSFULLY! (100% Pass Rate)")
    else:
        print(f"  TEST FAILURES DETECTED: {len(result.failures)} failure(s), {len(result.errors)} error(s)")
    print("======================================================================")

    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
