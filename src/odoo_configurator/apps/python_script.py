# Copyright (C) 2024 - Scalizer (<https://www.scalizer.fr>).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

import importlib.util as ilu
from . import imports
from ..utils import Utils as utils


class PythonScript(imports.OdooImports):
    _name = "PythonScript"
    _key = "python_script"
    auto_apply = False

    def get_func(self, data):
            file_path = data.get('file', False)
            method_name = data.get('method', False)
            self.logger.info("Python Script %s %s" % (file_path, method_name))
            path = utils.get_file_full_path(data.get('file'))
            spec = ilu.spec_from_file_location('import_specific', path)
            specific_lib = ilu.module_from_spec(spec)
            spec.loader.exec_module(specific_lib)
            return getattr(self._import_manager, method_name)

    def apply(self):
        self.prepare_extra_odoo_connections()
        self.prepare_sql_connections()
        datas = self._datas.get(self._key, {})
        for script_section in datas:
            if not self.install_mode() and datas[script_section].get('on_install_only', False):
                return
            script_data = datas[script_section]
            func = self.get_func(script_data)
            params = script_data.get('params', {})
            params['configurator'] = self._configurator
            params['config'] = self._configurator.config
            func(params=params)
