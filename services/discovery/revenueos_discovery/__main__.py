from revenueos_common.service import run

from . import DEFAULT_PORT
from .app import app, start


def main() -> None:  # pragma: no cover - process entrypoint
    start()
    run(app, DEFAULT_PORT)


if __name__ == "__main__":  # pragma: no cover
    main()
