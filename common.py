import os
import sys


def get_program_dir() -> str:
    try:
        # noinspection PyUnresolvedReferences
        return os.path.abspath(__compiled__.containing_dir)
    except NameError:
        return os.path.abspath(os.path.dirname(sys.argv[0]))
