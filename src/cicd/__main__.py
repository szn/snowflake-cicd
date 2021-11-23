if __name__ == '__main__':
    try:
        from cicd.utils.log import logger, init_logger
        init_logger()
        from cicd.cicd import main
        main()
    except (RuntimeError, AssertionError) as e:
        logger.error(e)
        quit(-1)
    