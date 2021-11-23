try:
    from .utils.log import logger, init_logger
    init_logger()
    from .cicd import main
    cicd = main
except (RuntimeError, AssertionError) as e:
    logger.error(e)
