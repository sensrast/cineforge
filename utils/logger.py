import logging, os

def setup_logging() -> None:
 logging.basicConfig(level=getattr(logging,os.getenv('LOG_LEVEL','INFO').upper(),logging.INFO),format='%(asctime)s | %(levelname)s | %(name)s | %(message)s')
