"""How often the incident rest centre watch repeats inside one GitHub Actions job.

GitHub's scheduler starts only a fraction of a */10 cron (this repo saw 28 runs in a day).
The watch job loops until near the 6-hour job limit, then the workflow requests the next
run itself. These helpers are the timing for that loop.
"""
import sys

INTERVAL_S = 600
# GitHub-hosted jobs are killed at 6 hours. Stop the loop early so this job can wait
# out the last gap and request the next run before that kill.
JOB_TIMEOUT_S = 360 * 60
HANDOFF_BUFFER_S = 20 * 60
# Checkout and Python setup for the next run. The handoff waits this much less than
# 10 minutes so the next check still lands about 10 minutes after the previous one.
STARTUP_ALLOWANCE_S = 90
MIN_WAIT_S = 30


def loop_budget_s(job_timeout_s=None, buffer_s=None):
    job_timeout_s = JOB_TIMEOUT_S if job_timeout_s is None else int(job_timeout_s)
    buffer_s = HANDOFF_BUFFER_S if buffer_s is None else int(buffer_s)
    return job_timeout_s - buffer_s


def should_continue(elapsed_s, budget_s, interval_s=None):
    """True when another 10-minute gap still fits before the handoff buffer."""
    interval_s = INTERVAL_S if interval_s is None else int(interval_s)
    interval_s = max(1, interval_s)
    return max(0, int(elapsed_s)) + interval_s <= int(budget_s)


def wait_seconds(elapsed_s, interval_s=None, allowance_s=None, min_wait_s=None):
    """Seconds to wait after a check before the next run should be requested."""
    interval_s = INTERVAL_S if interval_s is None else int(interval_s)
    allowance_s = STARTUP_ALLOWANCE_S if allowance_s is None else int(allowance_s)
    min_wait_s = MIN_WAIT_S if min_wait_s is None else int(min_wait_s)
    elapsed_s = max(0, int(elapsed_s))
    wait = int(interval_s) - elapsed_s - int(allowance_s)
    if wait < int(min_wait_s):
        return int(min_wait_s)
    return wait


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else ""
    if cmd == "interval":
        print(INTERVAL_S)
    elif cmd == "budget":
        print(loop_budget_s())
    elif cmd == "continue":
        elapsed = int(argv[1])
        budget = int(argv[2]) if len(argv) > 2 else loop_budget_s()
        interval = int(argv[3]) if len(argv) > 3 else INTERVAL_S
        print("yes" if should_continue(elapsed, budget, interval) else "no")
    elif cmd == "wait":
        elapsed = int(argv[1]) if len(argv) > 1 else 0
        interval = int(argv[2]) if len(argv) > 2 else INTERVAL_S
        print(wait_seconds(elapsed, interval))
    else:
        print("usage: incident_rest_centre_schedule.py interval|budget|continue ELAPSED [BUDGET] [INTERVAL]|wait ELAPSED [INTERVAL]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
