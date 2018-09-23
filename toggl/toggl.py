import sys

from . import cli

TOGGL_URL = "https://www.toggl.com/api/v8"
WEB_CLIENT_ADDRESS = "https://www.toggl.com/app/"


def main():
    """toggle.toggle.main: Main entry point for Toggle CLI application"""
    cli.cli(sys.argv[1:], obj={})
