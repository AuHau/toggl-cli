import re

from click.testing import Result


class ParsingResult:

    def __init__(self, result):  # type: (Result) -> None
        if result is None:
            raise TypeError('Result must not be None!')

        self.obj = result

    def parse_list(self):
        output = self.obj.output.strip()
        parsed = []

        for line in output.split('\n'):
            parsed.append(line.split('\t'))

        return parsed

    def parse_detail(self):
        output = self.obj.output.strip().split('\n')
        parsed = {}

        regex = re.match(r'([\w ]+) #(\d+)$', output[0])

        if not regex:
            raise RuntimeError('Unknown structure of detail string!')

        parsed['name'] = regex.group(1)
        parsed['id'] = regex.group(2)

        for line in output[1:]:
            key, value = line.split(':')

            key = key.trim().replace(' ', '_')
            parsed[key.lower()] = value.trim()

        return parsed


