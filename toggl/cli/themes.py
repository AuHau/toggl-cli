"""
The values of the themes are derived from click.style
https://click.palletsprojects.com/en/7.x/api/#click.style

"""


class PlainTheme:
    code = 'plain'
    name = 'Plain theme'

    title = {}
    title_id = {}
    header = {}
    success = {}

    error_color = 'red'


class LightTheme:
    code = 'light'
    name = 'Light theme'

    title = {'fg': 'green'}
    title_id = {'fg': 'green', 'dim': 1}
    header = {'fg': 'bright_black', 'dim': 1}
    success = {'fg': 'green'}

    error_color = 'red'


class DarkTheme:
    code = 'dark'
    name = 'Dark theme'

    title = {'fg': 'green'}
    title_id = {'fg': 'green', 'dim': 1}
    header = {'fg': 'white', 'dim': 1}
    success = {'fg': 'green'}

    error_color = 'red'


themes = {
    'dark': DarkTheme,
    'light': LightTheme,
    'plain': PlainTheme
}
