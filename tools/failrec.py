"""pytest plugin (validation only): record which tests fail/error, plus files that fail to import.
Output: $FAIL_OUT (json) = {"failed": [nodeid...], "collect_errors": [file...]}"""
import json, os

failed, collect = set(), set()


def pytest_runtest_logreport(report):
    if report.failed:
        failed.add(report.nodeid.split(" ")[0].split("[")[0])


def pytest_collectreport(report):
    if report.failed:
        collect.add(report.nodeid)


def pytest_sessionfinish(session, exitstatus):
    if hasattr(session.config, "workerinput"):
        return
    with open(os.environ["FAIL_OUT"], "w") as f:
        json.dump({"failed": sorted(failed), "collect_errors": sorted(collect),
                   "exitstatus": int(exitstatus)}, f)
