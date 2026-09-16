import json
import sys

from sqlagent.index.build import build


def main() -> int:
    manifest = build()
    print(json.dumps({k: v for k, v in manifest.items() if k != "values"}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
