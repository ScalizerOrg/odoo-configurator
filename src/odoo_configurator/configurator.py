# Copyright (C) 2023 - Teclib'ERP (<https://www.teclib-erp.com>).
# Copyright 2024 Scalizer (<https://www.scalizer.fr>)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from datetime import date, datetime
import glob
import logging
from packaging.version import Version
import os.path
import sys

import hiyapyco

from .apps import connection
from .apps import account
from .apps import config
from .apps import system_parameter
from .apps import datas
from .apps import defaults
from .apps import imports
from .apps import python_script
from .apps import modules
from .apps import roles
from .apps import translations
from .apps import users
from .apps import website
from .apps import mattermost
from .apps import slack
from .apps import call
from .apps import import_configurator

from .import_manager import ImportManager
from .logging import get_logger
from .odoo_connection import OdooConnection
from .keepass import KeepassCli
from .bitwarden import Bitwarden
from .utils import Utils

logger = get_logger(__name__)


def get_config_from_files(files):
    return hiyapyco.load(files, method=hiyapyco.METHOD_MERGE, interpolate=True,
                         failonmissingfiles=True, loglevel='INFO')


class Configurator:
    mode = ["config"]
    debug = False
    connection = None
    import_manager = None
    keepass_cli = None
    bitwarden_cli = None
    config = dict()
    pre_update_config = dict()
    xmlid_cache = dict()
    release_directory = ''
    clear_release_directory = False
    paths = list()
    slack_token = ''
    start_time = datetime.now()
    version = ''

    def __init__(self, paths=None, install=False, update=False, debug=False, debug_xmlrpc=False, **kwargs):
        """
        paths (list): List of file paths to load configuration from.
        install (bool): Whether to install mode is enabled.
        update (bool): Whether to update mode is enabled.
        debug (bool): Whether to enable debug logging.
        debug_xmlrpc (bool): Whether to enable debug logging for XML-RPC.
        **kwargs: Additional keyword arguments:
            - keepass (str): Keepass password.
            - slack_token (str): Slack token.
            - config_dict (dict): Dictionary containing configuration data.
        """
        if paths is None:
            paths = []
        self.configurator_dir = os.path.dirname(sys.argv[0])
        paths = [i.name if hasattr(i, 'name') else i for i in paths]
        if install:
            self.mode.append('install')
        if update:
            self.mode.append('update')

        self.version = kwargs.get('version', '')

        self.slack_token = os.environ.get('SLACK_TOKEN') or kwargs.get('slack_token', '')
        self.lang = kwargs.get('lang', 'fr_FR')
        self.debug = debug
        self.debug_xmlrpc = debug_xmlrpc
        if paths:
            self.paths = paths
            self.config, self.pre_update_config = self.parse_config()
        else:
            self.config = kwargs.get('config_dict', {})
        self.log_history = []
        logger.setLevel(logging.DEBUG if debug else logging.INFO)

        self.utils = Utils(self)
        self.keepass_cli = KeepassCli(self, keepass_password=kwargs.get('keepass', ''))
        self.bitwarden_cli = Bitwarden(self)
        self.prepare_odoo_connection()
        self.import_manager = ImportManager(self)

    def prepare_odoo_connection(self):
        odoo_params = self.get_odoo_auth_params()
        connection.OdooConnection(self).pre_config(odoo_params)
        self.connection = OdooConnection(
            odoo_params['url'],
            odoo_params['dbname'],
            odoo_params['username'],
            odoo_params['password'],
            version=self.config.get('version', False),
            http_user=odoo_params.get('http_user'),
            http_password=odoo_params.get('http_password'),
            createdb=odoo_params.get('create_db'),
            debug_xmlrpc=self.debug_xmlrpc,
            lang=self.lang,
            configurator=self,
        )

    def get_odoo_auth_params(self):
        if self.config.get('auth') and self.config.get('auth').get('odoo'):
            return self.config['auth']['odoo']
        else:
            return {
                'url': os.environ.get('ODOO_URL'),
                'dbname': os.environ.get('ODOO_DB'),
                'username': os.environ.get('ODOO_USER'),
                'password': os.environ.get('ODOO_PASSWORD'),
            }

    def parse_config(self):
        count_inherit = 0
        count_pre_update = 0
        config_files = []
        pre_update_config = None
        parsed_config = get_config_from_files(self.paths)

        while len(parsed_config.get("pre_update", [])) != count_pre_update:
            count_pre_update = len(parsed_config.get("pre_update", []))
            config_files = self.get_files_path(parsed_config['pre_update'])
            logger.info("Pre Update Loading %s" % (",".join(config_files)))
            pre_update_config = get_config_from_files(config_files)
            pre_update_config['auth'] = parsed_config['auth']

        while len(parsed_config.get("inherits", [])) != count_inherit:
            count_inherit = len(parsed_config.get("inherits", []))
            inherit_files = self.get_files_path(parsed_config['inherits'])
            config_files = self.paths + inherit_files
            parsed_config = get_config_from_files(config_files)
        logger.info("Configuration Loading %s" % (",".join(config_files)))

        if parsed_config.get('release_directory'):
            self.release_directory = parsed_config['release_directory']
            release_files = self.get_release_files()
            config_files += release_files
            logger.info("Release Configuration Loading %s" % (",".join(release_files)))
            parsed_config = get_config_from_files(config_files)
        if parsed_config.get('clear_release_directory'):
            self.clear_release_directory = parsed_config.get('clear_release_directory')

        if parsed_config.get('configurator_version'):
            version = parsed_config['configurator_version']
            version = str(version) if not isinstance(version, str) else version
            if Version(version) > Version(self.version):
                msg = "The yml configuration requires Odoo Configurator version >= %s (Current version==%s)"
                logger.error(msg % (version, self.version))
                exit(1)

        self.parse_scripts(parsed_config)

        return parsed_config, pre_update_config

    def parse_scripts(self, parsed_config):
        parsed_config['scripts'] = []
        count_script = 0
        while len(parsed_config.get("script_files", [])) != count_script:
            count_script = len(parsed_config.get("script_files", []))
            script_files = self.get_files_path(parsed_config['script_files'])

            for script_file in script_files:
                parsed_script = get_config_from_files([script_file])
                if parsed_script.get('title'):
                    parsed_script['title'] = '%s : %s' % (os.path.basename(script_file),
                                                          parsed_script.get('title'))
                else:
                    parsed_script['title'] = os.path.basename(script_file)
                if 'script_files' in parsed_script:
                    self.parse_scripts(parsed_script)
                parsed_config['scripts'].append(parsed_script)

    def get_release_files(self):
        files = []
        release_dir = self.release_directory
        if not os.path.isdir(release_dir):
            release_dir = os.path.join(os.path.dirname(sys.argv[1]), release_dir)
        if os.path.isdir(release_dir):
            files = glob.glob(os.path.join(release_dir, '*.yml'))
        return files

    def backup_release_directory(self):
        release_directory = self.utils.get_dir_full_path(self.release_directory)
        if self.clear_release_directory and os.path.isdir(release_directory):
            bak_dir = os.path.join(release_directory, 'bak')
            if not os.path.isdir(bak_dir):
                os.mkdir(bak_dir)
            release_bak_dir = os.path.join(bak_dir, str(date.today()))
            if not os.path.isdir(release_bak_dir):
                os.mkdir(release_bak_dir)
            for file in self.get_release_files():
                bak_file = os.path.join(release_bak_dir, os.path.basename(file))
                os.rename(file, bak_file)

    def get_files_path(self, files):
        res = []
        template_dirs = [
            os.path.join(self.configurator_dir, 'templates'),
            os.path.join(self.configurator_dir, 'src/templates'),
            os.path.join(os.path.dirname(__file__), '../templates'),
        ]
        for file in files:
            if os.path.isfile(file):
                res.append(file)
            else:
                file_found = ''
                for template_dir in template_dirs:
                    file_path = os.path.join(template_dir, file)
                    if os.path.isfile(file_path):
                        file_found = file_path
                        res.append(file_path)
                        continue
                if file_found:
                    continue

                for path in self.paths:
                    file_path = os.path.join(os.path.dirname(path), file)
                    if os.path.isfile(file_path):
                        file_found = file_path
                        continue

                if file_found:
                    res.append(file_found)
                else:
                    logger.info("File not found: %s" % file)
        return res

    def get_log(self):
        return "\n".join(self.log_history)

    def get_external_config_xmlid_cache(self):
        domain = [['module', '=', 'external_config']]
        xmlid_datas = self.connection.execute_odoo('ir.model.data', 'search_read', [domain, ['name', 'res_id']], {'context': {}})
        for xmlid_data in xmlid_datas:
            self.xmlid_cache['external_config.%s' % xmlid_data['name']] = xmlid_data['res_id']

    def show(self):
        pass
        # logger.info('show')
        # logger.info(pformat(self.config))

    def start(self):
        self.start_time = datetime.now()
        self.slack = slack.Slack(self)
        self.slack.init_slack_client()
        translations.OdooTranslations(self)
        modules_manager = modules.OdooModules(self)
        modules_manager.pre_update_config_modules()
        datas_manager = datas.OdooDatas(self)
        datas_manager.execute_pre_update_config_datas()
        modules_manager.install_config_modules()
        datas_manager.execute_update_config_datas()
        config.OdooConfig(self)
        system_parameter.OdooSystemParameter(self)
        roles.OdooRoles(self)
        defaults.OdooDefaults(self)
        users.OdooUsers(self)
        account.OdooAccount(self)
        website.OdooWebsite(self)
        imports.OdooImports(self)
        python_script.PythonScript(self)
        import_configurator.ImportConfigurator(self)
        mattermost.Mattermost(self)
        call.OdooCalls(self)
        self.backup_release_directory()

        duration = datetime.now() - self.start_time
        minutes = round(duration.total_seconds() / 60, 2) if duration else 0
        message = '%s updated in %s minutes' % (self.config.get('name'), minutes)
        if self.slack.slack_client:
            self.slack.send_message(message, message_type='valid', title='Odoo Configurator Done')
        logger.info(message)

        return self.get_log()
