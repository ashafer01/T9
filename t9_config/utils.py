def parse_time_interval(time_arg):
    """Parse a simple string representing a time interval and return an integer number of seconds"""
    try:
        return int(time_arg)
    except ValueError:
        pass
    if time_arg.endswith('s'):
        seconds = int(time_arg[:-1])
    elif time_arg.endswith('m'):
        seconds = int(time_arg[:-1]) * 60
    elif time_arg.endswith('h'):
        seconds = int(time_arg[:-1]) * 3600
    else:
        raise ValueError('Unknown time units')
    return seconds
