# Copyright (C) 2023 - Teclib'ERP (<https://www.teclib-erp.com>).
# Copyright (C) 2024 - Scalizer (<https://www.scalizer.fr>).
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

import logging
import sys
import os

def get_logger(name):
    logger = logging.getLogger(name)
    format_directive = '%(asctime)s - %(levelname)s - %(name)s : %(message)s'
    # topic discussed here: https://github.com/Lightning-AI/pytorch-lightning/issues/16081
    logger.handlers.clear()
    #Sadly, Pycharm doesn't handle well stdout/stderr timings so the log order can be mixed up.
    #As a fix, we redirect all log level to stdout while adding coloring info
    if os.environ.get('PYCHARM_HOSTED'):
        formatter = ColorFormatter('%(asctime)s - %(levelname)s - %(name)s : %(message)s')
        stdout_handler = logging.StreamHandler(stream=sys.stdout)
    else:
        formatter = logging.Formatter(format_directive)
        # log lower levels to stdout
        stdout_handler = logging.StreamHandler(stream=sys.stdout)
        stdout_handler.addFilter(lambda rec: rec.levelno <= logging.INFO)
        # log higher levels to stderr (red)
        stderr_handler = logging.StreamHandler(stream=sys.stderr)
        stderr_handler.addFilter(lambda rec: rec.levelno > logging.INFO)
        stderr_handler.setFormatter(formatter)
        logger.addHandler(stderr_handler)

    logger.addHandler(stdout_handler)
    stdout_handler.setFormatter(formatter)
    logger.setLevel(logging.INFO)

    return logger

class ColorFormatter(logging.Formatter):
    # https://en.wikipedia.org/wiki/ANSI_escape_code#Colors
    GRAY8 = "38;5;8"
    GRAY7 = "38;5;7"
    ORANGE = "33"
    BLUE = "34"
    BRIGHT_BLUE = "94"
    RED = "31"
    WHITE = "0"

    def format(self, record):
        formatted_msg = super().format(record)

        level_color_map = {
            logging.DEBUG: self.BLUE,
            logging.INFO: self.WHITE,
            logging.WARNING: self.ORANGE,
            logging.ERROR: self.RED,
        }
        csi = f"{chr(27)}["
        color = level_color_map.get(record.levelno, self.WHITE)

        return f"{csi}{color}m{formatted_msg}{csi}m"
