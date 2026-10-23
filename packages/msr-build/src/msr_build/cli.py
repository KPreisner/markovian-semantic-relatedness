"""The `msr` command line. Subcommands (fetch, build-model, corpus-prep, concepts, search) land
with their phases."""

import argparse
from collections.abc import Sequence

import msr


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="msr", description="Markovian Semantic Relatedness")
    parser.add_argument("--version", action="version", version=f"%(prog)s {msr.__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0
