import string


class EchoFormatter(string.Formatter):
    def __init__(self, line, func_input='', stack=None, regex_match=None):
        if stack and len(stack) >= 1:
            stack = [i[1] for i in stack]
        else:
            stack = []

        if regex_match:
            matches = {0: regex_match.group(0)}
            for i, group_str in enumerate(regex_match.groups(default='')):
                matches[i + 1] = group_str
            for name, group_str in regex_match.groupdict(default='').items():
                matches[name] = group_str
        else:
            matches = {}

        self._format_values = {
            'nick': line.handle.nick,
            'channel': line.args[0],
            'input': func_input,
            'stack': stack,
            'match': matches,
        }

    def parse(self, format_string):
        for tpl in string.Formatter.parse(self, format_string):
            literal_text, field_name, format_spec, conversion = tpl
            if field_name:
                try:
                    field, default = field_name.split('=', 1)
                except ValueError:
                    field = field_name
                    default = ''

                try:
                    try:
                        field, item = field.split('.', 1)
                        try:
                            item = int(item)
                        except ValueError:
                            pass
                        collection = self._format_values[field]
                        try:
                            value = collection[item]
                        except (KeyError, IndexError):
                            value = default
                    except ValueError:
                        value = self._format_values[field]
                except KeyError:
                    value = '{UNKNOWN FIELD}'

                if not value:
                    value = default

                value = format(value, format_spec)

                yield literal_text + value, None, None, None
            else:
                yield tpl
