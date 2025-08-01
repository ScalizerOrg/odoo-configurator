odoo-configurator
=================

Odoo Configurator simplifies and automates the configuration of Odoo using YAML files. 
It allows you to update the database, install/update/uninstall modules, configure settings, 
manage users, and perform various data manipulation operations. 
It is an essential tool for Odoo administrators looking to streamline their configuration workflow.

## Installation

    pip install odoo-configurator

## Usage

    odoo-configurator ./work_dir/project_name.local.yml

To run a configuration from the source code:

    /odoo-configurator/start_config.py ./work_dir/project_name.local.yml

Provided file must contain the auth/odoo section to set connexion parameters.

#### project_name.local.yml

```yml
    name: project_name local
    version: 16.0

    inherits:
        - ../work_dir/project_name/project_name.yml

    auth:
        odoo:
            url: http://project_name.localhost
            dbname: project_name
            username: admin
            password: admin123
```

The`version` parameter is required for odoo versions >= 15.0

It's also possible to provide auth for other odoo servers, these connections can be used in python script files and specific imports.
```yml
    auth:
      odoo:
        url: http://project_name.localhost
        dbname: project_name
        username: admin
        password: admin
        version: 16.0
      odoo_base_v8:
        url: http://old.odoo.localhost
        dbname: project_name_v8
        username: admin
        password: admin
        version: 8.0
      odoo_base_v17:
        url: http://next.odoo.localhost
        dbname: project_name_v17
        username: admin
        password: admin
        version: 17.0
```
### Extra parameters
When running odoo-configurator, you can provide the following optional arguments:
- --lang: Set the language for the Odoo connection (default value: 'fr_FR')

## Inherits

Inherits param provide a list of configuration files witch content is merged before execution.

```yml
    inherits:
        - ../work_dir/project_name/sales.yml
        - ../work_dir/project_name/account.yml
 ```

## Script Files

Script Files param provide a list of configuration files witch content will be executed sequentially.

```yml
    script_files:
        - ../work_dir/project_name/script1.yml
        - ../work_dir/project_name/script2.yml
```

## Parameters

**Install Mode**: To import datas with the value **on_install_only: True** add the "--install" parameter in command
line:

    ./start_config.py ./clients/name/name.local.yml --install

## Environment variables

Some parameters can be provided by environment variable.

Use ODOO_URL, ODOO_DB, ODOO_USER and ODOO_PASSWORD instead of using auth/odoo params in config file

Use KEEPASS_PASSWORD instead of --keepass command line parameter

## Pre Update

To prepare a configuration or add a fix use "pre_update" from a top-level configuration, the given scripts will be executed before the normal configuration.

```yml
    pre_update:
        - ../exemple/exemple.pre_update_script.yml
```

## Modules

To install modules use "modules"
```yml
    base:
      modules:
        - example_module
```

To update modules use "updates"
```yml
    base:
      updates:
        - example_module
```

To uninstall modules use "uninstall_modules"
```yml
    base:
      uninstall_modules:
        - example_module
```

## Set config parameters (Settings)

to set the value of a setting (res.config.settings)
```yml
    settings:
      config:
        group_use_lead: True
```

For a specific company configuration use the `company_id` parameter:
```yml
    settings main_company:
      config:
        company_id: get_ref("base.main_company")
        chart_template_id: get_ref("l10n_fr.l10n_fr_pcg_chart_template")
        context: { 'lang': 'fr_FR' }
```

A context can be passed to the config command.

## Set system parameters

to set the value of a system parameter (ir.config_parameter)
```yml
Company System Parameters:
  system_parameter:
    Mail Default From Filter:
      key: mail.default.from_filter
      value: my-company.com
  ```


## Create or update records
    
If the record with the xml id provided with force_id don't exist, the record will be created.    

```yml
    Records to create:
        datas:
            My record 1:
                model: res.partner
                force_id: external_config.partner_1
                values:
                    name: Partner 1
                    ref: PARTNER1
            My record 2:
                model: res.user
                force_id: base.user_admin
                values:
                    name: Admin User
```

## Load records

Using load parameter will speed up creation and update of record compared to single record update.

```yml
    Records to load:
        load: True
        model: res.partner
        datas:
            My record 1:
                force_id: external_config.record1
                values:
                    name: Record 1
                    ref: REC1
            My record 2:
                force_id: external_config.record2
                values:
                    name: Record 2
                    ref: REC2
```

## Update records with a domain

To update values of multiple records, set a domain with "update_domain" :
```yml
    Update Example:
      model: res.partner
      update_domain: "[('email','=','example@test.com')]"
      values:
        name: Example
```

## Available functions

All functions in OdooConnection starting by `get_` are callable from yml files.
 - get_ref
 - get_image_url
 - get_image_local
 - get_local_file
 - get_country
 - get_menu
 - get_search_id
 - get_xml_id_from_id
 - get_record

These functions can be nested by using the o object:

```yml
Ir model Data Config:
  datas:
    Add employee document xmlid:
      model: ir.model.data
      force_id: template_01_employee_01
      values:
        model: paper.paper
        module: external_config
        name: template_01_employee_01
        res_id: get_search_id('paper.paper', [
                ('template_id', '=', o.get_ref('external_config.template_01')),
                ('res_id', '=', o.get_ref('external_config.employee_01'))
                ], 'desc')
```

## Special field name

field_name_id/id : to provide a xmlid to many2one fields instead of a value, without using get_ref.
field_name_ids/id : to provide a list of xmlid to many2many fields.
field_name_ids.ids : to provide a string that will be evaluated to compute the raw values for a many2many field.
field_name/json : to provide a list or dict to convert into json string.

```yml
    res_partner:
        datas:
            My record 1:
                model: res.partner
                force_id: external_config.partner_1
                values:
                    name: Partner 1
                    ref: PARTNER1
                    field_name_id/id: external_config.partner_1
                    field_name_ids/id: [external_config.partner_2, external_config.partner_3]
                    field_name2_ids/id:
                        - external_config.partner_2
                        - external_config.partner_3
                    field_name3_ids.ids: "[[6, 0, [o.get_ref('external_config.partner_2')]]]"
                    field_name/json: {"key1": "value1", "key2": "value2"}
```

## Server Actions and Functions

To call a model function:
```yml
    001 Call Function:
      datas:
        Call Function:
          function: example_function
          model: res.parnter
          res_id: get_ref("base.partner_demo")
          params: ['param1', param2]
          kw: {'extra_param1': get_ref('external_config.extra_param1')}  
```

To call an action server (`ir.actions.server`):
```yml
    002 Call Action Server:
      datas:
        Call Action Server:
          action_server_id: get_ref("custom_module.action_exemple")
          model: res.parnter
          res_id: get_ref("base.partner_demo")
```

## Users

To set groups on a user you can remove previous groups with "unlink all".
```yml
    users:
        Portal Users:
            User Example 1:
                force_id: base.user_example
                login: example@test.com
                groups_id:
                    - unlink all
                    - base.group_portal
                values:
                    name: Portal User Example 1
```
                    
## Other data tools

- delete_all
- delete_domain
- delete_id
- deactivate
- activate
- update_domain
  - search_value_xml_id
      - this option allows to pass an id from xml_id to a domain
      - Can be used with update_domain, activate, deactivate:
  
        ```yml        
                      Deactivate Partner Title doctor:
                          model: res.partner.title
                          search_value_xml_id: base.res_partner_title_doctor
                          deactivate: "[('id', '=', 'search_value_xml_id')]"
        ```

## Translations

To set the translation of a translatable field, use the **languages** option.
Example:
```yml
    Mail Templates:
        datas:
            Notification:
                model: mail.template
                force_id: mail.notification_template
                languages:
                    - fr_FR
                    - en_US
                values:
                    body_html: |
                        <table>
                            <tbody>
                            Text for french and english
                            </tbody>
                        </table>
```

## Notifications

To avoid notifications, add in main yaml file:
```yml
    no_notification: True
```

## Mattermost Notification

To set a Mattermost url and channel where to send notifications:
```yml
    mattermost_channel: my-channel
    mattermost_url: https://mattermost.xxx.com/hooks/dfh654fgh
```

## Slack Notification

To send notifications with Slack:
```yml
    slack_channel: my-channel
    slack_token: xxxxx
```

The Slack token can also be set by passing it as an argument with the `--slack-token` option.

To send notifications from a python script:
```python
from odoo_configurator.import_manager import ImportManager
def import_stuff(self, params=dict):
    self.set_params(params)
    self.configurator.slack.send_message('Starting Stuff Import')
```

Note: To use Slack notification, the `Odoo Configurator` Slack app must be added in the channel.

## Keepass

Keepass is a tool to store and protect passwords.

Available functions to use stored values in Keepass:
```yml
    password: get_keepass_password('path/passwords.kdbx', 'Folder Name', 'Key Name')
    user: get_keepass_user('path/passwords.kdbx', 'Folder Name', 'Key Name')
    url: get_keepass_url('path/passwords.kdbx', 'Folder Name', 'Key Name')
```

To avoid to repeat path and group in Keepass functions, you can set `keepass_path` and `keepass_group`
```yml
keepass_path: path/passwords.kdbx
keepass_group: Folder Name

my_secret: get_keepass_password('Key Name')
```

3 ways to pass the Keepass password to odoo-configurator :
 - Provide Keepass password with the keepass parameter in command line: `--keepass='mdp***'`
 - Set the `KEEPASS_PASSWORD` environment variable
 - Manually. If it's required odoo-configurator will ask to type the password with the prompt `Keepass Password:`

 In PyCharm, to type the Keepass password, please check the `Emulate terminal in output console` option in your run/debug configuration.

## Bitwarden

Bitwarden is a tool to store and protect passwords. Make sure Bitwarden CLI is installed.

Credentials to connect to Bitwarden Vault can be set by environment variables, please report to the [s6r-bitwarden-cli documentation](https://pypi.org/project/s6r-bitwarden-cli)

An over option is to set the value of `bitwarden_username` and  `bitwarden_password` in yml file. Obviously, do not save password directly in your yml file, use Keepass functions for example.

```yml
bitwarden_username: get_keepass_user('Bitwarden')
bitwarden_password: get_keepass_password('Bitwarden')
```

## Standard CSV Import

Columns in the CSV file must be the technical name of the field.
A column "id" is required to allow update of datas. 

In yml file, use the **import_csv** entry in the **import_data** section:

```yml
    import_data:
        import_csv Product Template:
            on_install_only: True
            model: product.template
            name_create_enabled_fields: uom_id,uom_po_id,subscription_template_id
            file_path: ../datas/todoo/product.template.csv
            specific_import: base/import_specific.py
            specific_method: import_partner
            batch_size: 200
            skip_line: 1420
            limit: 100
            context: {'install_mode': True}
```

### Required fields:

  - model
  - file_path

### Optional fields:

  - **name_create_enabled_fields** : List of the fields which are allowed to "Create the record if it doesn't exist"
  - **on_install_only** : Do the csv export only in **Install Mode**
  - **context** : Provide a specific context for imports
  - **specific_import** : Path to a specific Python file
  - **specific_method** : Import method to use form the file **specific_import**
  - **batch_size** : Number of records by load batch
  - **limit** : Maximum number of record to import
  - **skip_line** : index of the record to start with

## Specific Import with Python script

Use the **import_data** section:

```yml
Import Scripts:
  import_data:
    Task Import 001:
      model: project.product
      file_path: scripts/products.csv
      specific_import: scripts/import_products.py
      specific_method: import_products
```

scripts/import_products.py :

```python
from odoo_configurator.import_manager import ImportManager

def import_products(self, file_path, model, params):
    self.set_params(params)
    fields = self.get_model_fields(model)
    raw_datas = self.parse_csv_file_dictreader(file_path, fields)
    m_order = self.odoo.model('sale.order')
    orders = m_order.search([], context=self._context)
    self.logger.info('Orders : %s' % ','.join([o['name'] for o in orders]))
    company_ids_cache = self.odoo.get_id_ref_dict('res.company')
    company_xmlid_cache = self.odoo.get_xmlid_dict('res.company')
    products = self.odoo.search('product.template', [], context=self._context)
    ...

ImportManager.import_products = import_products
```


## Run Python script

Use the **python_script** section:

```yml
python_script:
  Data Transfer:
    file: scripts/transfer_script.py
    method: data_transfer
    params:
      param1: TEST
```

It's possible to add connection to other odoo database by adding, for exemple, _odoo_base_v16_ in the **auth** section.
_odoo_base_v16_ can be used easily in python scripts by referring to self.odoo_base_v16:

```yml
auth:
  odoo:
    url: http://odoo_my_customer17.localhost
    dbname: my_customer17
    username: admin
    password: admin
    version: 17.0
  odoo_base_v16:
    url: http://odoo_my_customer16.localhost
    dbname: my_customer16
    username: admin
    password: admin
    version: 16.0
```

scripts/transfer_script.py :

```python
from src.odoo_configurator.import_manager import ImportManager

def data_transfer(self, params=dict):
    # Search analytic lines on my_customer17 (the main database)
    analytic_lines = self.odoo.search("account.analytic.line", [], fields=['name', 'partner_id'])
    for analytic_line in analytic_lines:
        if analytic_line['partner_id']:
            partner_id = analytic_line['partner_id'][0]
            # Read partner on my_customer16 (the extra database)
            partner = self.odoo_base_v16.read('res.partner', [partner_id], fields=['name', 'email'])
            if partner:
                self.logger.info('analytic_line %s partner %s' % (analytic_line['id'], partner[0]['name']))

ImportManager.data_transfer = data_transfer
```

## Connection to SQL database

Use the **sql_auth** section:

```yml
sql_auth:
  sql_my_shop:
    db_type: postgresql
    url: localhost
    dbname: my_shop_prod
    username: admin
    password: get_keepass_password('My Shop Admin')
```

### Available database types
 * Postgresql (postgresql)
 * MS SQL Server (mssql)
 * MySQL (mysql)

scripts/sql_transfer_script.py :

```python
from src.odoo_configurator.import_manager import ImportManager

def sql_transfer(self, params=dict):
    query = 'select name, email from res_partner'
    cr = self.sql_my_shop.execute(query)
    for partner_values in cr.fetchall():
            self.logger.info('Partner %s' % partner_values['name'])

ImportManager.sql_transfer = sql_transfer
```


## Generate YML data file from a Odoo database

'import_configurator_model_file' configuration will generate a res_partner.yml file in the **config** directory
```yml
Actions:
    import_configurator_model_file:
        Portal Form:
            model: res.partner
            domain: [['is_company', '=', True]]  # Don't use parenthesis in the domain
            order_by: name, ref
            force_export_fields: ["email_formatted", "country_code"]
            excluded_fields: ["email", "country_id"]
            context: {'active_test': False}
```

'import_configurator_module' configuration will generate a 'studio_customization' directory in the **config** directory, with a file for each model containing the records of the module.
```yml
 Actions:           
    import_configurator_module:
        module: 'studio_customization'
```

## Release Configuration

Some configurations need to be executed on every platform until the production release. After that we need to archive these configuration files.
We will store the files in the directory *release_config* for example.
To run all these files, add the **release_directory** parameter in your main configuration file:

```yml
    release_directory: ./release_config
```

To back up the release files after the execution of the production configuration, add the **clear_release_directory** parameter in you production configuration file.

```yml
  clear_release_directory: True
```

## Contributors

* David Halgand
* Michel Perrocheau - [Github](https://github.com/myrrkel)


## Maintainer

This software was created by [Hodei](https://www.hodei.net) formerly Teclib' ERP, 
maintenance is now being handled by [Scalizer](https://www.scalizer.fr).


<div style="text-align: center;">

[![Scaliser](./logo_scalizer.png)](https://www.scalizer.fr)

[![Hooei](./logo_hodei.jpg)](https://www.hodei.net)

</div>
