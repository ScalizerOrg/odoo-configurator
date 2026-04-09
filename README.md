# odoo-configurator

Configure and update Odoo databases from YAML files. Install modules, write settings, create or update records, run CSV imports, execute Python scripts — all driven by a single readable config file.

## Installation

```bash
pip install odoo-configurator
```

Optional extras for SQL connections and Slack notifications:

```bash
pip install "odoo-configurator[postgresql]"   # PostgreSQL
pip install "odoo-configurator[mysql]"         # MySQL
pip install "odoo-configurator[mssql]"         # MS SQL Server
pip install "odoo-configurator[slack]"         # Slack notifications
pip install "odoo-configurator[all-db,slack]"  # everything
```

---

## Quick start

```yaml
# myproject.local.yml
name: myproject local
version: 17.0

auth:
  url: http://myproject.localhost
  db: myproject
  user: admin
  password: admin

Base modules:
  modules:
    - sale_management
    - purchase

Settings:
  config:
    group_use_lead: true
    company_id: get_ref('base.main_company')
```

```bash
odoo-configurator myproject.local.yml
```

---

## CLI

```
odoo-configurator [OPTIONS] FILE [FILE ...]
```

| Option | Description |
|---|---|
| `FILE [FILE ...]` | One or more YAML config files (merged in order, later files win) |
| `--target NAME` | Load auth from a `targets.yml` file instead of the config |
| `--targets-file FILE` | Path to targets file (default: `targets.yml`) |
| `--install` | Install mode — enables `on_install_only` operations |
| `--lang CODE` | Language code for the Odoo context (default: `fr_FR`) |
| `--debug` | Enable DEBUG logging |
| `--debug-xmlrpc` | Log every XML-RPC call |
| `--version` | Print version and exit |

---

## Config file structure

A config file has metadata keys at the top level and **sections** below. A section is a user-named group of directives (`modules:`, `config:`, `datas:`, etc.) — the name is arbitrary and used only for logging. Every key that maps to a dict and is not a metadata key is treated as a section.

```yaml
name: My Config          # optional label
version: 17.0            # Odoo version (required for >= 15.0)
configurator_version: 4.0  # minimum odoo-configurator version required

auth:                    # connection credentials (or use --target)
  url: http://odoo.localhost
  db: mydb
  user: admin
  password: admin

includes:                # merge other files before executing
  - base/modules.yml
  - base/settings.yml

My Section:              # user-named group of directives
  modules:
    - sale_management
  config:
    group_use_lead: true
```

### Merging files (`includes:`)

Included files are merged recursively before execution. Later files override earlier ones — dicts are deep-merged, lists are replaced.

```yaml
# prod.yml
name: Production
includes:
  - base/common.yml
  - base/prod_settings.yml

auth:
  url: https://prod.example.com
  db: prod-db
  password: env://ODOO_PROD_PASSWORD
```

### Ordered execution (`sequence:`)

Use `sequence:` when execution order matters — each file's operations are appended after the previous one's. This is the standard way to structure a multi-file project.

```yaml
# main.yml — entry point
sequence:
  - config/modules.yml
  - config/settings.yml
  - datas/partners.yml
  - datas/products.yml
```

```bash
odoo-configurator main.yml
```

Each file in `sequence:` can itself use `includes:` to merge sub-files. Sequences are expanded recursively before execution — the executor always receives a single flat list of operations.

---

## Authentication

### Inline auth (quick start)

Convenient for local development or a single-environment setup. For projects with multiple environments (local / staging / prod), use a targets file instead.

```yaml
auth:
  url: http://odoo.localhost
  db: mydb
  user: admin
  password: admin
  version: 17.0          # optional, defaults to 17.0
  http_user: proxy_user  # optional, for reverse-proxy HTTP Basic Auth
  http_password: secret
```

### Targets file (recommended for multi-environment projects)

A targets file decouples credentials from config files — a single `config/main.yml` works for every environment; only the `--target` flag changes.

```yaml
# targets.yml  (gitignored)
targets:
  local:
    url: http://odoo.localhost
    db: mydb
    user: admin
    password: admin

  staging:
    url: https://staging.example.com
    db: staging-db
    password: env://ODOO_STAGING_PASSWORD

  prod:
    url: https://prod.example.com
    db: prod-db
    password: env://ODOO_PROD_PASSWORD
```

```bash
odoo-configurator --target staging config/main.yml
odoo-configurator --target prod config/main.yml
```

---

## Secrets

Use the `env://` URI scheme to read a value from an environment variable at runtime:

```yaml
password: env://ODOO_PROD_PASSWORD
slack_token: env://SLACK_BOT_TOKEN
```

Create a `.env` file at the project root (gitignored) — it is loaded automatically:

```bash
# .env
ODOO_PROD_PASSWORD=my_secret_password
SLACK_BOT_TOKEN=xoxb-...
```

Plain string values pass through unchanged.

---

## YAML expressions

Any field value starting with `get_` is evaluated as a Python expression at execution time.

| Expression | Returns |
|---|---|
| `get_ref('base.EUR')` | `int` — database id for an xml_id |
| `get_record('res.partner', 7)` | `dict` — full record by id |
| `get_search_id('res.partner', [('name','=','ACME')])` | `int` or `None` — first match |
| `get_country('FR')` | `int` — id of `res.country` |
| `get_menu(1, '/shop')` | `int` — id of `website.menu` |
| `get_image_url('https://example.com/logo.png')` | base64 string (cached to disk) |
| `get_image_local('assets/logo.png')` | base64 string |
| `get_local_file('templates/footer.html')` | file contents as string |
| `get_xml_id_from_id('res.partner', 42)` | xml_id string |
| `get_default('res.partner', 'country_id')` | field default value |
| `get_env_var('MY_VAR')` | env var value (legacy — prefer `env://`) |

Expressions are evaluated per-record at execution time, so a record created earlier in the same run is immediately referenceable:

```yaml
Partners:
  datas:
    ACME:
      model: res.partner
      force_id: external_config.partner_acme
      name: ACME Corp
      country_id: get_search_id('res.country', [('code','=','FR')])
      image_1920: get_image_url('https://logo.example.com/acme.png')

    ACME Paris:
      model: res.partner
      force_id: external_config.partner_acme_paris
      name: ACME Paris
      parent_id: get_ref('external_config.partner_acme')  # created above
```

The legacy nested syntax `o.get_ref(...)` is also supported.

---

## Modules

```yaml
Base:
  modules:
    - sale_management
    - purchase

  updates:
    - stock

  uninstall_modules:
    - website_sale
```

---

## Settings

### Odoo settings (`res.config.settings`)

```yaml
Settings:
  config:
    group_use_lead: true
    group_use_quotation_validity_days: true

Settings main company:
  config:
    company_id: get_ref('base.main_company')
    chart_template_id: get_ref('l10n_fr.l10n_fr_pcg_chart_template')
    context: {lang: fr_FR}
```

### System parameters (`ir.config_parameter`)

```yaml
System Params:
  system_parameter:
    web.base.url: https://prod.example.com
    mail.default.from_filter: example.com
```

### Field defaults (`ir.default`)

```yaml
Defaults:
  defaults:
    Default partner type:
      model: res.partner
      field: company_type
      value: company
    Default pricelist currency:
      model: product.pricelist
      field: currency_id
      condition: company_id=1
      value: get_ref('base.EUR')
```

---

## Records

### Create or update

`force_id` is the xml_id used to look up an existing record; if not found, the record is created.

```yaml
Partners:
  datas:
    ACME Corp:
      model: res.partner
      force_id: external_config.partner_acme
      name: ACME Corp
      ref: ACME
      street: 12 rue de la Paix
      country_id/id: base.fr

    Admin user:
      model: res.users
      force_id: base.user_admin
      name: Administrator
```

Use `search_key` to match by field value instead of xml_id:

```yaml
    Update ACME by ref:
      model: res.partner
      search_key: ref
      ref: ACME
      name: ACME Corp Updated
```

### Field name suffixes

| Suffix | Example value | Meaning |
|---|---|---|
| `field/id` (string) | `country_id/id: base.fr` | Many2one — resolve xml_id to int |
| `field/id` (list) | `tag_ids/id: [base.tag_a, base.tag_b]` | Many2many — resolve list of xml_ids |
| `field/json` | `config/json: {key: val}` | Serialize dict or list to JSON string |

```yaml
    My record:
      model: res.partner
      force_id: external_config.partner_1
      name: Partner 1
      country_id/id: base.fr
      category_id/id:
        - base.res_partner_category_0
        - base.res_partner_category_1
      extra_config/json:
        theme: blue
        layout: grid
```

### Multi-language values

Write a field in multiple languages with `languages`:

```yaml
Mail Templates:
  datas:
    Invoice notification:
      model: mail.template
      force_id: account.email_template_edi_invoice
      languages:
        - fr_FR
        - en_US
      body_html: |
        <p>Please find your invoice attached.</p>
```

`languages` can also be set at the section level to apply to all records in that section.

### Delete records

```yaml
Cleanup:
  datas:
    Remove old partner:
      model: res.partner
      delete_id: external_config.partner_old

    Remove demo leads:
      model: crm.lead
      delete_domain: [['name', 'like', 'demo']]

    Remove all demo partners:
      model: res.partner
      delete_all: true
```

### Activate / deactivate

```yaml
    Deactivate doctor title:
      model: res.partner.title
      search_value_xml_id: base.res_partner_title_doctor
      deactivate: "[('id', '=', 'search_value_xml_id')]"

    Activate portal group:
      model: res.groups
      activate: "[('category_id.name', '=', 'Portal')]"
```

`search_value_xml_id` substitutes the resolved id for the literal string `'search_value_xml_id'` in the domain.

### Bulk update by domain

```yaml
    Reset all partner refs:
      model: res.partner
      update_domain: [['ref', '!=', false]]
      values:
        ref: false
```

---

## Users

```yaml
Users:
  users:
    portal_example:
      login: portal@example.com
      force_id: external_config.user_portal_example
      groups_id:
        - unlink all
        - base.group_portal
      values:
        name: Portal User Example
        lang: fr_FR
```

`unlink all` removes the user from every group before applying the new list.

---

## Roles

Requires the `base_user_role` OCA module.

```yaml
Roles:
  datas_roles:
    sales_role:
      force_id: external_config.role_sales
      values:
        name: Sales
        implied_ids:
          - base.group_user
          - sales_team.group_sale_salesman
        line_ids:
          - user_id: base.user_demo
```

---

## Method calls

```yaml
Calls:
  call:
    Recompute pricelists:
      model: product.pricelist
      method: _compute_price_rule_multi
      args: [[]]
      context: {active_test: false}

    Reset password:
      model: res.users
      method: action_reset_password
      args: [[get_ref('external_config.user_new')]]
      no_raise: true
```

---

## Translations

```yaml
translations:
  - fr_FR
  - nl_NL
```

Can also be set at the section level:

```yaml
Base:
  translations:
    - de_DE
```

---

## CSV import

```yaml
Imports:
  import_data:
    Partners:
      model: res.partner
      file_path: datas/partners.csv
      batch_size: 200
      skip_lines: 0
      limit: 1000
      context: {tracking_disable: true}
      name_create_enabled_fields:
        - category_id
      ignore_fields:
        - message_ids
```

File paths are resolved relative to the config file directory, then `datas/`.

The CSV must have an `id` column (xml_id) to enable updates. All other columns use technical field names.

### Custom import handler

```yaml
    Partners custom:
      model: res.partner
      file_path: datas/partners.csv
      handler: scripts/import_helpers.py::import_partners
      batch_size: 100
```

```python
# scripts/import_helpers.py
def import_partners(ctx, file_path, model, params):
    data = parse_my_csv(file_path)
    ctx.client.odoo.load_batch(model, data, batch_size=params['batch_size'])
```

---

## Python scripts

```yaml
Scripts:
  script:
    Transfer analytic lines:
      handler: scripts/transfer.py::transfer_analytic_lines
      params:
        source_db: staging
        dry_run: false
```

```python
# scripts/transfer.py
def transfer_analytic_lines(ctx, params):
    lines = ctx.client.odoo.search_read(
        'account.analytic.line', [], fields=['name', 'amount']
    )
    for line in lines:
        ctx.logger.info('Line: %s', line['name'])
```

The function receives `(ctx, params)`. `ctx.client` is the primary Odoo connection. `ctx.extra_clients['name']` gives access to secondary connections defined in `auth`.

### Legacy syntax

The older `python_script:` key with `file` + `method` is still accepted but deprecated — use `script:` with `handler: file.py::function` instead.

---

## SQL connections

Requires an extra: `pip install "odoo-configurator[postgresql]"`.

```yaml
sql_auth:
  legacy_db:
    db_type: postgresql    # postgresql | mysql | mssql
    url: localhost
    db: legacy_prod
    user: admin
    password: env://LEGACY_DB_PASSWORD
```

Access in scripts via `ctx.sql_clients['legacy_db']`:

```python
def migrate_data(ctx, params):
    cr = ctx.sql_clients['legacy_db'].execute('SELECT name, email FROM res_partner')
    for row in cr.fetchall():
        ctx.logger.info('%s', row['name'])
```

Query results can be cached to disk to avoid re-running expensive queries across runs:

```python
cr = ctx.sql_clients['legacy_db'].execute('SELECT ...', cache='partners_cache')
```

---

## Notifications

### Slack

```yaml
slack_token: env://SLACK_BOT_TOKEN
slack_channel: "#deployments"
```

The Slack app must be added to the channel. The token can also be passed with `--slack-token`.

Send from a section:

```yaml
Notify:
  slack:
    message: "Config applied successfully"
    message_type: valid     # valid | error | warning | start
    title: "Deploy complete"
```

### Mattermost

```yaml
mattermost_url: https://mattermost.example.com/hooks/abc123
mattermost_channel: deployments
```

Send from a section:

```yaml
Notify:
  mattermost:
    message: "Config applied"
    url: https://mattermost.example.com/hooks/abc123
    channel: deployments
```

---

## Website theme

```yaml
Website:
  website:
    theme: theme_clean
```

---

## Architecture

The tool follows a three-phase pipeline:

```
YAML files  →  Planner  →  list[Operation]  →  Executor  →  Odoo
```

**Loader** (`loader.py`) reads YAML files and produces an ordered list of config dicts. `includes:` are resolved via deep merge (later files win). `sequence:` expands recursively into ordered steps. Multiple CLI files are merged. All output is plain Python dicts.

**Planner** (`planner.py`) walks the merged config dict and emits an ordered list of typed `Operation` dataclasses — no Odoo calls happen at this stage. Within each section, operations are emitted in a fixed order: modules → translations → system parameters → settings → records/roles/defaults → users → calls → imports → scripts. Sections are processed in YAML insertion order.

**Executor** (`executor.py`) takes the operation list and dispatches each one to the appropriate Odoo calls via `ctx.client`. YAML expression evaluation (`get_ref(...)` etc.) happens per-record here, which means a record created by an earlier operation is immediately referenceable by a later one.

**Adding a new YAML directive** requires three changes:
1. Add an `Operation` dataclass in `operations.py`
2. Add a clause in `planner.py:_emit_section()`
3. Add a `_execute_*` function in `executor.py`

**Plugin functions** (`handler: file.py::function`) receive a `Context` object as their first argument. `Context` bundles the primary Odoo client, secrets provider, path utilities, extra Odoo clients, and SQL clients. Plugin modules are cached — a file referenced multiple times is `exec`'d only once.

---

## Contributors

- David Halgand
- Michel Perrocheau — [Github](https://github.com/myrrkel)

## Maintainer

Created by [Hodei](https://www.hodei.net) (formerly Teclib' ERP).  
Maintained by [Scalizer](https://www.scalizer.fr).

<div style="text-align: center;">

[![Scalizer](./logo_scalizer.png)](https://www.scalizer.fr)
[![Hodei](./logo_hodei.jpg)](https://www.hodei.net)

</div>
