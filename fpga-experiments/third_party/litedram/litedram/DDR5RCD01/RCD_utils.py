#
# This file is part of LiteDRAM.
#
# Copyright (c) 2023 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause

import logging
import os
import inspect


class NotSupportedException(Exception):
    def __init__(self, *args):
        if args:
            self.message = str(args[0])
        else:
            self.message = "Engineering test of this block will not be provided."

    def __str__(self):
        return self.message


class UnderConstruction(Exception):
    def __init__(self, *args):
        if args:
            self.message = str(args[0])
        else:
            self.message = "Engineering test of this block is being developed."

    def __str__(self):
        return self.message


class EngTest():
    def __init__(self, level=logging.DEBUG):
        # Setup
        dir_name = "./test_eng"
        if not os.path.exists(dir_name):
            # Test eng dir does not exist
            os.mkdir(dir_name)
        # file_name = "input_buffer"
        full_file_name = inspect.stack()[-1].filename
        file_name = (full_file_name.split('/')[-1]).split('.')[0]
        log_file_name = dir_name + '/' + file_name+".log"
        wave_file_name = dir_name + '/' + file_name+".vcd"
        # logger = logging.getLogger('root')
        log_level = level
        # log_level = logging.INFO
        log_handlers = [logging.FileHandler(
            log_file_name), logging.StreamHandler()]
        log_format = "[%(module)s.%(funcName)s] %(message)s"
        logging.basicConfig(format=log_format,
                            handlers=log_handlers, level=log_level)

        self.dir_name = dir_name
        self.file_name = file_name
        self.full_file_name = full_file_name
        self.log_file_name = log_file_name
        self.wave_file_name = wave_file_name
        self.log_handlers = log_handlers

    def __str__(self):
        description = "\n--Summary--\n"
        description += "Called:\t" + self.file_name + "\n"
        description += "Log:\t" + self.log_file_name + "\n"
        description += "Wave:\t" + self.wave_file_name + "\n"
        return description


def logger_change_log_file(old_log_file_name, new_log_file_name):
    logger = logging.getLogger('root')
    for handler in logger.handlers:
        try:
            handler_file_name = (
                (handler.baseFilename).split('/')[-1]).split('.')[0]
            if handler_file_name == old_log_file_name:
                logger.removeHandler(handler)
        except:
            pass
    fileHandler = logging.FileHandler(filename=new_log_file_name, mode='w')
    logger.addHandler(fileHandler)


if __name__ == "__main__":
    raise NotSupportedException
