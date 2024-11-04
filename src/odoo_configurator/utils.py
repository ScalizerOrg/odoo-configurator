# Copyright (C) 2024 - Scalizer (<https://www.scalizer.fr>).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from .logging import get_logger
import os


class Utils:
    """This class is intended to provide utility functions which are not related to a specific configurator app.
    Methods starting with 'get_' will automatically be callable from within yaml files,
    as per similar methods in OdooConnection Class (get_ref, get_record, etc.) """

    def __init__(self, configurator):
        self.configurator = configurator
        self.logger = get_logger("Utils".ljust(20))

    def get_env_var(self, var_name):
        var = os.environ.get(var_name)
        if not var:
            self.logger.warning(f"{var} Environment Variable not found or empty")
        return var