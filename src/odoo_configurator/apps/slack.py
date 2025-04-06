# Copyright (C) 2025 - Scalizer (<https://www.scalizer.fr>).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from . import base
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

MESSAGE_TYPE_EMOJIS = {
    'red': 'red_circle',  # 🔴
    'green': 'large_green_circle',  # 🟢
    'yellow': 'large_yellow_circle',  # 🟡
    'orange': 'large_orange_circle',  # 🟠
    'blue': 'large_blue_circle',  # 🔵
    'error': 'x',  # ❌
    'warning': 'warning',  # ⚠️
    'info': 'information_source',  # i️
    'valid': 'white_check_mark',  # ✅
    'start': 'arrow_forward',  # ▶️
}

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
        slack_token = self._configurator.slack_token or self._datas.get('slack_token', False)
        if slack_token and slack_token.startswith('get_'):
            self.slack_token = self.safe_eval(slack_token)
        else:
            self.slack_token = slack_token
        if self.slack_token:
            self.slack_client = WebClient(token=self.slack_token)

        if self.slack_client:
            self.logger.info('Slack client initialized')
            message = 'Starting Odoo Configurator : %s' % self.config.get('name')
            self.send_message(message, slack_channel=self.slack_channel, message_type='start')

    def send_message(self, message="This is a test! :tada:", slack_channel='', message_type='', title='', emoji=''):
        """
        Send a message to the specified Slack channel.
        :param message: The content of the message to be sent.
        :param slack_channel: The Slack channel where the message will be sent.
        :param message_type: The type of message. Available types: 'error', 'warning', 'info', 'valid', 'red', 'green',
        'yellow', 'orange', 'blue'.
        :param title: The title of the message.
        :param emoji: The Slack emoji code without the enclosing ":" e.g., "large_blue_circle".
        """
        message = self._prepare_message(message, message_type, title, emoji)
        if not self.slack_client:
            return
        try:
            self.logger.debug('Sending Slack message: %s' % message)
            channel = slack_channel or self.slack_channel
            response = self.slack_client.chat_postMessage(channel=channel, text=message)
        except SlackApiError as e:
            self.logger.error('Slack API error: %s' % e.response["error"])

    def _prepare_message(self, message, message_type, title, emoji):
        if title:
            message = f'*{title}*\n{message}'
        if message_type:
            emoji = MESSAGE_TYPE_EMOJIS.get(message_type, '')
        if emoji:
            message = f':{emoji}: {message}'

        return message
