# Copyright (C) 2023 - Teclib'ERP (<https://www.teclib-erp.com>).
# Copyright (C) 2024 - Scalizer (<https://www.scalizer.fr>).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from collections import OrderedDict
from . import base


class OdooSystemParameter(base.OdooModule):
    _name = "System Parameter"

    def __init__(self, configurator, auto_apply=True):
        self.auto_apply = auto_apply
        super(OdooSystemParameter, self).__init__(configurator)

    def apply(self, datas=None):
        super(OdooSystemParameter, self).apply()
        for key in datas or self._datas:
            if isinstance(self._datas.get(key), dict) or isinstance(self._datas.get(key), OrderedDict):
                system_parameters = self._datas.get(key).get('system_parameter', {})
                if system_parameters:
                    self.logger.info("\t- %s" % key)
                    self.execute(system_parameters)

    def execute_script_config(self, datas=False):
        datas = datas if datas else self._datas
        for key in datas:
            if isinstance(datas.get(key), dict) or isinstance(datas.get(key), OrderedDict):
                values = datas.get(key).get('system_parameter', {})
                if values:
                    self.logger.info("\tSystem Parameter - %s" % key)
                    self.execute(values)

    def execute(self, datas):
        for key in datas:
            if isinstance(datas.get(key), dict) or isinstance(datas.get(key), OrderedDict):
                self.logger.info("\t\t* %s" % key)
                self.odoo_system_parameter(datas.get(key))

    def odoo_system_parameter(self, system_parameter):
        for key in system_parameter:
            if isinstance(system_parameter[key], str) and system_parameter[key].startswith('get_'):
                system_parameter[key] = self.safe_eval(system_parameter[key])
        domain = [['key', '=', system_parameter['key']]]
        parameter_id = self.search_read('ir.config_parameter', domain, fields=['id', 'key', 'value'],
                                   context=self._context, limit=1)
        if parameter_id:
            parameter_id = parameter_id[0]
            self.execute_odoo('ir.config_parameter', 'write',
                              [parameter_id['id'],
                               {'value': system_parameter['value']}
                               ], {'context': self._context})
        else:
            parameter_id = self.execute_odoo('ir.config_parameter', 'create',
                                             [{'key': system_parameter['key'],
                                               'value': system_parameter['value']}],
                                             {'context': self._context})
