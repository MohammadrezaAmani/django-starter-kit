#!/usr/bin/env python
"""
Test runner script for the course app.
Runs comprehensive tests including API, security, and performance tests.
"""
import os
import sys

import django
from django.conf import settings
from django.test.utils import get_runner


def setup_django():
    """Setup Django for testing"""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()


def run_course_tests():
    """Run all course-related tests"""
    setup_django()

    TestRunner = get_runner(settings)
    test_runner = TestRunner()

    # Define test modules to run
    test_modules = [
        "tests.test_course_api",
        "tests.test_course_security",
    ]

    print("Running Course App Tests...")
    print("=" * 50)

    failures = 0

    for module in test_modules:
        print(f"\nRunning tests in {module}...")
        try:
            result = test_runner.run_tests([module])
            failures += result
        except Exception as e:
            print(f"Error running {module}: {e}")
            failures += 1

    print("\n" + "=" * 50)
    if failures:
        print(f"Tests completed with {failures} failures.")
        return 1
    else:
        print("All tests passed successfully!")
        return 0


def run_security_tests_only():
    """Run only security tests"""
    setup_django()

    TestRunner = get_runner(settings)
    test_runner = TestRunner()

    print("Running Security Tests Only...")
    print("=" * 50)

    try:
        failures = test_runner.run_tests(["tests.test_course_security"])
        if failures:
            print(f"Security tests completed with {failures} failures.")
            return 1
        else:
            print("All security tests passed!")
            return 0
    except Exception as e:
        print(f"Error running security tests: {e}")
        return 1


def run_api_tests_only():
    """Run only API tests"""
    setup_django()

    TestRunner = get_runner(settings)
    test_runner = TestRunner()

    print("Running API Tests Only...")
    print("=" * 50)

    try:
        failures = test_runner.run_tests(["tests.test_course_api"])
        if failures:
            print(f"API tests completed with {failures} failures.")
            return 1
        else:
            print("All API tests passed!")
            return 0
    except Exception as e:
        print(f"Error running API tests: {e}")
        return 1


def run_with_coverage():
    """Run tests with coverage reporting"""
    try:
        import coverage
    except ImportError:
        print("Coverage.py not installed. Install with: pip install coverage")
        return 1

    cov = coverage.Coverage()
    cov.start()

    setup_django()

    # Run tests
    result = run_course_tests()

    cov.stop()
    cov.save()

    print("\nCoverage Report:")
    print("=" * 50)
    cov.report()

    # Generate HTML report
    cov.html_report(directory="htmlcov")
    print("HTML coverage report generated in 'htmlcov' directory")

    return result


def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "security":
            return run_security_tests_only()
        elif command == "api":
            return run_api_tests_only()
        elif command == "coverage":
            return run_with_coverage()
        elif command in ["help", "--help", "-h"]:
            print_help()
            return 0
        else:
            print(f"Unknown command: {command}")
            print_help()
            return 1

    return run_course_tests()


def print_help():
    """Print help information"""
    print("Course App Test Runner")
    print("=" * 30)
    print("Usage:")
    print("  python run_course_tests.py           # Run all tests")
    print("  python run_course_tests.py security  # Run security tests only")
    print("  python run_course_tests.py api       # Run API tests only")
    print("  python run_course_tests.py coverage  # Run with coverage report")
    print("  python run_course_tests.py help      # Show this help")


if __name__ == "__main__":
    sys.exit(main())
