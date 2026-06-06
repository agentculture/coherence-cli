"""Entry point for ``python -m coherence``."""

from __future__ import annotations

import sys

from coherence.cli import main

if __name__ == "__main__":
    sys.exit(main())
