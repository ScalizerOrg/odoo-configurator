# Copyright (C) 2023 - Teclib'ERP (<https://www.teclib-erp.com>).
# Copyright (C) 2024 - Scalizer (<https://www.scalizer.fr>).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from collections import OrderedDict

from . import base


class OdooDefaults(base.OdooModule):
    _name = "Defaults"

    def apply(self):
        super(OdooDefaults, self).apply()

        for key in self._datas:
            if isinstance(self._datas.get(key), dict) or isinstance(self._datas.get(key), OrderedDict):
                defaults = self._datas.get(key).get('defaults', {})
                if defaults:
                    self.logger.info("\t- %s" % key)
                    self.pre_config(defaults)
                    self.odoo_defaults(defaults)

    def odoo_defaults(self, defaults):
        if not defaults:
            return
        for default in defaults:
            self.logger.info("\t\t* %s" % default)
            d = defaults[default]
            default_value = d['value']
            if type(default_value) is str and default_value.startswith('get_'):
                default_value = self.safe_eval(default_value)
            condition = d.get('condition', False)
            if self._connection._use_json2:
                # v19 json2 binds args via inspect.signature.bind(**kwargs) — must
                # pass named kwargs matching ir.default.set's signature.
                self.odoo._json2_call(
                    'ir.default', 'set',
                    model_name=d['model'],
                    field_name=d['field'],
                    value=default_value,
                    user_id=False,
                    company_id=False,
                    condition=condition,
                )
            else:
                self.execute_odoo('ir.default', 'set',
                                  [d['model'], d['field'], default_value, False, False, condition],
                                  {'context': self._context})
