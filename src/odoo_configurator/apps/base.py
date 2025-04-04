# Copyright (C) 2023 - Teclib'ERP (<https://www.teclib-erp.com>).
# Copyright (C) 2024 - Scalizer (<https://www.scalizer.fr>).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

import logging
from collections import OrderedDict
from ..odoo_connection import OdooConnection
from ..keepass import KeepassCli
from ..bitwarden import Bitwarden
from ..utils import Utils

from ..logging import get_logger


class OdooModule:
    # pylint: disable=too-many-instance-attributes
    auto_apply = True

    def __init__(self, configurator):
        self._configurator = configurator
        self.config = self._configurator.config
        self._connection = configurator.connection
        self._utils = configurator.utils
        self._keepass_cli = configurator.keepass_cli
        self._bitwarden_cli = configurator.bitwarden_cli
        self._import_manager = configurator.import_manager
        self._datas = configurator.config
        self._pre_datas = configurator.pre_update_config
        self._mode = configurator.mode
        self._debug = configurator.debug
        self.xmlid_cache = configurator.xmlid_cache
        if self._connection:
            self.odoo = self._connection.odoo
            self._context = self._connection.context.copy()
            self.execute_odoo = self._connection.execute_odoo
            self.search = self._connection.search
            self.search_read = self._connection.search_read
            self.get_xml_id_from_id = self._connection.get_xml_id_from_id
            self.get_id_from_xml_id = self._connection.get_id_from_xml_id
            self.get_ref = self._connection.get_ref
            self.get_record = self._connection.get_record
            self.default_get = self._connection.default_get
            self.create_xml_id = self._connection.create_xml_id
        self.logger = get_logger(self._name.ljust(20))
        if self._debug:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)
        if self.auto_apply:
            self.apply()

    @property
    def _name(self):
        raise NotImplementedError

    def _published_objects(self):
        return self._connection, self._keepass_cli, self._bitwarden_cli, self._utils

    def _published_class(self):
        return OdooConnection, KeepassCli, Bitwarden, Utils

    def install_mode(self):
        if 'install' in self._mode:
            return True
        return False

    def get_mapping_method(self):
        res = {}
        for o in self._published_class():
            res[o.__name__] = [method for method in dir(o) if method.startswith('_') is False]
        return res

    def deep_convert_dict(self, layer):
        to_ret = layer
        if isinstance(layer, OrderedDict):
            to_ret = dict(layer)
        try:
            for key, value in to_ret.items():
                to_ret[key] = self.deep_convert_dict(value)
        except AttributeError:
            pass
        return to_ret

    def safe_eval(self, name, force=False):
        for object_class, methods in self.get_mapping_method().items():
            if name.split('(')[0] in methods:
                for o in self._published_objects():
                    if o.__class__.__name__ == object_class:
                        self.logger.debug("o.%s", name)
                        try:
                            return eval("o.%s" % name)
                        except Exception as err:
                            raise err
            elif name.split('(')[0].split('.')[-1] in methods and force:
                for o in self._published_objects():
                    if o.__class__.__name__ == object_class:
                        return eval(name)

        raise Exception("Cannot eval %s" % name)

    def pre_config(self, config, rec=0):
        if config and isinstance(config, dict) or isinstance(config, OrderedDict):
            for key in config:
                if isinstance(config[key], list):
                    tmp = []
                    for i in config[key]:
                        if type(i) is str and i.startswith('get_'):
                            i = self.safe_eval(i)
                        tmp.append(i)
                    config[key] = tmp
                elif isinstance(config[key], str) and config[key].startswith('get_'):
                    config[key] = self.safe_eval(config[key])
                elif isinstance(config[key], (dict, OrderedDict)) and config[key].get(
                        'values', '') and not config[key].get('force_id', ''):
                    model = config[key].get('model')
                    if config[key].get('values'):
                        self.pre_config(config[key]['values'], rec + 1)
                    values = config[key].get('values')
                    search_key = config[key].get('key', 'name')
                    domain = []
                    for i in search_key.split(','):
                        if values.get(i, False):
                            domain.append((i, '=', values[i]))
                    if config[key].get('update_domain', False) or not model:
                        continue

                    object_ids = self.search(model, domain, order='id', context=self._context)
                    self.logger.debug("%s %s %s", model, domain, object_ids)
                    if object_ids:
                        config[key]['force_id'] = object_ids[0]
                    else:
                        config[key] = self.execute_odoo(model, 'create', [dict(values)], {'context': self._context})
                elif isinstance(config[key], (dict, OrderedDict, list)):
                    if not self.install_mode() and config[key].get('on_install_only', False):
                        continue
                    for i in config[key]:
                        key_value = config[key][i]
                        if isinstance(key_value, str) and key_value.startswith('get_'):
                            config[key][i] = self.safe_eval(key_value)
                        self.pre_config(config[key][i], rec + 1)

    def apply(self):
        self.logger.info("Apply %s", self._name)
