import sys

from . import cli

TOGGL_URL = "https://www.toggl.com/api/v8"
WEB_CLIENT_ADDRESS = "https://www.toggl.com/app/"


def main(args=None):
    """Main entry point for Toggl CLI application"""
    cli.entrypoint(args or sys.argv[1:])
