# Copyright (C) 2025 - Scalizer (<https://www.scalizer.fr>).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from . import base
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class Slack(base.OdooModule):
    _name = "Slack"
    _key = "slack"

    slack_token = ''
    slack_channel = ''
    slack_client = None

    def apply(self):
        super(Slack, self).apply()

    def init_slack_client(self):
        if self._datas.get('no_notification', False):
            return
        self.slack_channel = self._datas.get('slack_channel', False)
        slack_token = self._datas.get('slack_token', False)
        if slack_token and slack_token.startswith('get_'):
            self.slack_token = self.safe_eval(slack_token)
        else:
            self.slack_token = slack_token
        if self.slack_token:
            self.slack_client = WebClient(token=self.slack_token)

        if self.slack_client:
            message = ':large_orange_circle: Starting Odoo Configurator : %s' % self.config.get('name')
            self.send_message(message, slack_channel=self.slack_channel)


    def send_message(self, message="This is a test! :tada:", slack_channel=''):
        if not self.slack_client:
            return
        try:
            self.logger.info('Sending Slack message: %s' % message)
            channel = slack_channel or self.slack_channel
            response = self.slack_client.chat_postMessage(channel=channel, text=message)
        except SlackApiError as e:
            self.logger.error('Slack API error: %s' % e.response["error"])
