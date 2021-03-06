"""
Evaluators to produce dummy data from parsed models.
"""

import re
from collections import OrderedDict

from . import functions
from .exceptions import DDEvaluatorException


TAG_PATTERN = re.compile(r"""
    \{% \s*                             # open tag
    (?P<function> \b \w+ \b)            # function name
    (?P<args>                           # function arguments
    (?: \s*                             # separated by white-space
    [^\s]+ )*? )?                       # non-white-space, allowed characters
    \s* %\}                             # close tag
""", re.VERBOSE)


ARG_PATTERN = re.compile(r"""
    (?<!\S)                             # do not allow non-white-space
    (?<![:/\d])                         # do not match date or time
    -?                                  # negative sign
    (?= [1-9]|0(?!\d) )                 # digits or zero before decimal
    \d+                                 # pre-decimal digits
    (?: \.                              # decimal
    \d+ )?                              # post-decimal digits
    (?:[eE] [+-]? \d+)?                 # scientific notation
    (?![:/\d])                          # do not match date or time
    (?!\S)                              # do not allow non-white-space
    |
    (?<!\S)                             # do not allow non-white-space
    "                                   # begin quote
    (?:[^"\\]                           # non-control characters
    | \\ ["\\bfnrt/]                    # escaped characters
    | \\ u [0-9a-f]{4}                  # Unicode characters
    | \\\\ \\\" )*?                     # double-escaped quotation mark
    "                                   # end quote
    (?!\S)                              # do not allow non-white-space
    |
    (?<!\S)                             # do not allow non-white-space
    (?:[^"\\\s])+?                      # unenclosed string without white-space
    (?!\S)                              # do not allow non-white-space
""", re.VERBOSE)


def evaluate_parsed(parsed, allow_callable=False, iteration=None):
    """
    Traverse parsed data and evaluate tags.
    """

    def call_function(match):
        """
        Call matched function.
        """
        args = ARG_PATTERN.findall(match.group('args'))
        args = [x[1:-1] if x[0] == '"' and x[-1] == '"' else x for x in args]
        try:
            value = getattr(
                functions,
                match.group('function')
            )(*args, iteration=iteration)
        except AttributeError:
            raise DDEvaluatorException(
                'attempted call to non-existent function {0}'.format(
                    match.group('function')
                )
            )
        if hasattr(parsed, '__call__') and not allow_callable:
            raise DDEvaluatorException(
                'function {0} called from illegal location'.format(
                    match.group('function')
                )
            )
        if match.start() != 0 or match.end() != len(match.string):
            value = str(value)
        return value

    def evaluate_object(parsed_object):
        """
        Evaluate tags in parsed object.
        """
        evaluated = OrderedDict()
        for k in parsed_object:
            evaluated[
                evaluate_parsed(k, iteration=iteration)
            ] = evaluate_parsed(parsed_object[k], iteration=iteration)
        return evaluated

    def evaluate_array(parsed_array):
        """
        Evaluate tags in parsed array.
        """
        evaluated = []
        index = 0
        while index < len(parsed_array):
            item = evaluate_parsed(
                parsed_array[index],
                allow_callable=True,
                iteration=index
            )
            if hasattr(item, '__call__'):
                if index + 1 >= len(parsed_array):
                    raise DDEvaluatorException(
                        'invalid use of {0} function at end of array'.format(
                            item.parent_function
                        )
                    )
                if 'repeat' == item.parent_function:
                    evaluated.extend(item(parsed_array[index + 1], evaluate_parsed))
                    index += 1
                elif 'random' == item.parent_function:
                    return item(parsed_array[index + 1:], evaluate_parsed)
            else:
                evaluated.append(item)
            index += 1
        return evaluated

    if isinstance(parsed, dict):
        return evaluate_object(parsed)
    elif isinstance(parsed, list):
        return evaluate_array(parsed)
    elif isinstance(parsed, str):
        try:
            return re.sub(TAG_PATTERN, call_function, parsed)
        except TypeError:
            # function returned a type other than string
            return call_function(TAG_PATTERN.search(parsed))
    return parsed
