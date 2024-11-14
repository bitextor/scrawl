import logging

logging.basicConfig()
logging.root.setLevel(logging.NOTSET)
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(f'SuperCrawler')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
