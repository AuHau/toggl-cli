import sys

from toggl import cli

TOGGL_URL = "https://www.toggl.com/api/v8"
REPORTS_URL = "https://toggl.com/reports/api/v2"
WEB_CLIENT_ADDRESS = "https://www.toggl.com/app/"


def main(args=None):
    """Main entry point for Toggl CLI application"""
    cli.entrypoint(args or sys.argv[1:])
