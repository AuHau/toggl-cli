import re

import sys

from . import cli

TOGGL_URL = "https://www.toggl.com/api/v8"
VISIT_WWW_COMMAND = "open http://www.toggl.com/app/timer"


def main():
    """toggle.toggle.main: Main entry point for Toggle CLI application"""
    input('Waiting')
    cli.cli(sys.argv[1:], obj={})
