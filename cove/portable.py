import os
import sys

PORTABLE_ENV = "COVE_PORTABLE"


def _exe_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def is_portable():
    if os.environ.get(PORTABLE_ENV) == "1":
        return True
    base = _exe_dir()
    return (os.path.isdir(os.path.join(base, 'cove-app-data'))
            or os.path.isfile(os.path.join(base, 'portable.marker')))


def portable_data_dir(app_name):
    d = os.path.join(_exe_dir(), 'cove-app-data', app_name)
    os.makedirs(d, exist_ok=True)
    return d
