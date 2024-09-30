# Copyright (C) 2023 - Teclib'ERP (<https://www.teclib-erp.com>).
# Copyright (C) 2024 - Scalizer (<https://www.scalizer.fr>).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from s6r_odoo import OdooConnection as Orm
from collections import OrderedDict
import importlib.util as ilu
from . import base
from ..odoo_connection import get_file_full_path
from ..sql import SqlConnection


class OdooImports(base.OdooModule):
    _name = "Imports"

    def get_func(self, data):
        if data.get('specific_import', False):
            if data.get('file_path', ''):
                self.logger.info("Specific import %s %s : %s" % (data.get('specific_import', False),
                                                                 data.get('specific_method', False),
                                                                 data.get('file_path', '')))
            else:
                self.logger.info("Specific import %s %s" % (data.get('specific_import', False),
                                                            data.get('specific_method', False)))
            path = get_file_full_path(data.get('specific_import'))
            spec = ilu.spec_from_file_location('import_specific', path)
            specific_lib = ilu.module_from_spec(spec)
            spec.loader.exec_module(specific_lib)
            func = getattr(self._import_manager, data.get('specific_method', False))
        else:
            func = getattr(self._import_manager, 'import_csv')
        return func

    def apply(self):
        super(OdooImports, self).apply()
        self.prepare_extra_odoo_connections()
        self.prepare_sql_connections()
        if self._import_manager and not hasattr(self._import_manager, '_datas'):
            self._import_manager._datas = self._datas

        datas = self._datas.get('import_data', {})
        if datas:
            self.logger.info("\t- %s" % "Global")
        for import_name in datas:
            if not self.install_mode() and datas[import_name].get('on_install_only', False):
                return
            import_data = datas[import_name]
            func = self.get_func(import_data)
            func(get_file_full_path(import_data.get('file_path', '')),
                 import_data.get('model', ''), params=import_data)
        for key in self._datas:
            if isinstance(self._datas.get(key), dict) or isinstance(self._datas.get(key), OrderedDict):
                for key_import, import_data in self._datas.get(key, {}).get('import_data', {}).items():
                    self.logger.info("\t- %s" % key_import)
                    if not self.install_mode() and import_data.get('on_install_only', False):
                        self.logger.info("\t\t* skipped not install mode")
                        return
                    func = self.get_func(import_data)
                    func(get_file_full_path(import_data.get('file_path', '')),
                         import_data.get('model', ''), params=import_data)

    def prepare_extra_odoo_connections(self):
        auth = self._datas.get('auth', {})
        if auth:
            for key in auth:
                if key != 'odoo' and not hasattr(self._import_manager, key):
                    auth_values = auth.get(key, {})
                    try:
                        setattr(self._import_manager, key, Orm(auth_values['url'],
                                               auth_values['dbname'],
                                               auth_values['username'],
                                               auth_values['password'],
                                               version=auth_values.get('version', False),
                                               ))
                    except ConnectionError:
                        exit(1)


    def prepare_sql_connections(self):
        sql_auth = self._datas.get('sql_auth', {})
        if sql_auth:
            for key in sql_auth:
                if not hasattr(self._import_manager, key):
                    auth_values = sql_auth.get(key, {})
                    try:
                        setattr(self._import_manager, key, SqlConnection(**auth_values))
                    except Exception as err:
                        self.logger.error(err)
                        exit(1)