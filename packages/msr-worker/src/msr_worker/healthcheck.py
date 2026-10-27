"""The container healthcheck (`python -m msr_worker.healthcheck`): ping this container's worker
over the broker, with a 1 s timeout. A busy worker still answers, so a long job doesn't make the
container unhealthy."""

import sys
from socket import gethostname

from msr_worker.app import celery_app


def main() -> int:
    replies = celery_app.control.ping(destination=[f"celery@{gethostname()}"], timeout=1.0)
    if not replies:
        print("no worker answered the ping", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
