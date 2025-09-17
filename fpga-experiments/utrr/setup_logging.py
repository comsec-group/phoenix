import logging

import colorlog


def setup_logging(
    log_file_path=None, file_level=logging.DEBUG, console_level=logging.DEBUG
):
    # Create a root logger
    logger = logging.getLogger()
    logger.setLevel(
        logging.DEBUG
    )  # Root logger should capture all levels for handlers to filter

    # Remove existing handlers to avoid duplication
    if logger.hasHandlers():
        logger.handlers.clear()

    # Console handler with colorized output
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s %(levelname)s [%(filename)s:%(lineno)d]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        log_colors={
            "DEBUG": "blue",
            "INFO": "bold_blue",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        },
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler for logging to file, if a path is provided
    if log_file_path:
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setLevel(file_level)
        file_formatter = logging.Formatter(
            "%(asctime)s %(levelname)s [%(filename)s:%(lineno)d]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    logging.info("Logging setup complete.")
