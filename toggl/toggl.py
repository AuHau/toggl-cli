import re

import sys

from . import cli

TOGGL_URL = "https://www.toggl.com/api/v8"
VERBOSE = False  # verbose output?
Parser = None  # OptionParser initialized by main()
VISIT_WWW_COMMAND = "open http://www.toggl.com/app/timer"


# TODO: Edits

def run(cmd):
    """Special function for running CLI like commands inside REPL

    Example of usages:
    >>>from toggl.toggl import run
    >>>run("add 'Some task'")
    >>>run("-h")
    """

    # Simulates quoting of strings with spaces ("some important task")
    parsed = re.findall(r"([\"]([^\"]+)\")|([']([^']+)')|(\S+)", cmd)
    cli.CLI([i[1] or i[3] or i[4] for i in parsed]).act()


def main():
    """toggle.toggle.main: Main entry point for Toggle CLI application"""
    cli.cli(sys.argv[1:], obj={})
