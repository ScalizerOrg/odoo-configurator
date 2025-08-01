# Copyright (C) 2023 - Teclib'ERP (<https://www.teclib-erp.com>).
# Copyright (C) 2025 - Scalizer (<https://www.scalizer.fr>).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from .configurator import Configurator
import argparse

import importlib.metadata
import pathlib
import toml

source_location = pathlib.Path(__file__).parent.parent
if (source_location.parent / "pyproject.toml").exists():
    with open(source_location.parent / "pyproject.toml", "rt") as f:
        __version__ = toml.load(f)['project']['version']
else:
    __version__ = importlib.metadata.version("odoo-configurator")


def main():
    parser = argparse.ArgumentParser(description='Odoo Configurator')
    parser.add_argument('paths', metavar='files', type=open, nargs='+', help='Config Files To load')
    parser.add_argument('--update', action='store_true', help='Update Mode')
    parser.add_argument('--install', action='store_true', help='Install Mode')
    parser.add_argument('--debug', action='store_true', help='Debug log')
    parser.add_argument('--debug_xmlrpc', action='store_true', help='Debug log xmlrpc')
    parser.add_argument('--keepass', type=str, help='Keepass password')
    parser.add_argument('--lang', type=str, help='Language code (e.g. fr_FR) to be used in context for all API calls')
    parser.add_argument('--slack-token', type=str, help='Slack token')
    args = parser.parse_args()
    c = Configurator(**dict(args._get_kwargs()), version=__version__)
    c.show()
    log = c.start()


if __name__ == '__main__':
    main()
