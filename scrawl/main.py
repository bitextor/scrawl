"""
Crawls the web using Playwright and real web browsers.
Usage:
  scrawl crawl [options] <locale_list> <url_list> <working_directory>
  scrawl crawl [options] <locale_list> file <url_list_filename> <working_directory>
  scrawl download [options] <url_list> <working_directory>
  scrawl download file [options] <url_list_filename> <working_directory>
  scrawl resume [options] <working_directory>

Options:
  -h --help                          Shows this help.
  --patterns=<pattern-list>          Force string to be part of the url.
  --max-pages=<n>                    Maximum number of pages to store, 0 for no limit [default: 10000000].
  --simultaneous-pages=<n>           Number of windows opened at once [default: 10].
  --loglevel=<value>                 One of: warning, info, debug, error [default: info].
  --logfile=<value>                  Log filename.
"""

import logging
import os
import re

import docopt
import schema
import iso639
from scrawl import tools, crawler, output, logger
import sys
import signal


def main():
    def signal_handler(sig, frame):
        nonlocal c

        logger.logger.info("Signal received: exiting program")
        logger.logger.info("Persisting crawler")
        c.persist()
        logger.logger.info("Generating output")
        output.generate_output(os.path.join(c.destination, "json"),
                               os.path.join(c.destination, "html"))
        sys.exit(0)

    appname = "SuperCrawler"

    levels = {"info": logging.INFO,
              "warning": logging.WARNING,
              "debug": logging.DEBUG,
              "error": logging.ERROR}
    args = docopt.docopt(__doc__, version=f'{appname} v 1.0')

    s = schema.Schema({
        '<url_list>': schema.Or(None,
                                lambda url_list: all(re.match("^http[s]://", n.strip()) for n in url_list.split(",")),
                                error="URLs must start with http:// or https://"),
        '<working_directory>': schema.And(tools.is_path_exists_or_creatable, error="cannot create output"),
        '<url_list_filename>': schema.Or(None,
                                         schema.And(lambda f: os.path.exists(f) and os.path.isfile(f),
                                                    error="the file <url_list_filename> does not exist")),
        '<locale_list>': schema.Or(None, schema.And(lambda n: all(i.strip() in iso639.languages.part1 for i in n.split(",")),
                                    error="all locales specified must be 2-letter ISO-639 codes")),
        '--patterns': schema.Or(None, schema.And(lambda n: all(len(i.strip()) > 0 for i in n.split(",")), error="--patterns have to be non-empty")),
        '--max-pages': schema.And(schema.Use(int), lambda n: n >= 0, error='--max-pages should be >= 0'),
        '--simultaneous-pages': schema.And(schema.Use(int), lambda n: n >= 1, error="--simultaneous-pages should be >= 1"),
        '--loglevel': schema.And(schema.Use(str), lambda n: n in levels),
        '--logfile': schema.Or(None, schema.And(tools.is_path_exists_or_creatable,
                                                error="cannot create logfile")),
        '--help': schema.And(schema.Use(bool)),
        "download": schema.And(schema.Use(bool)),
        "crawl": schema.And(schema.Use(bool)),
        "file": schema.And(schema.Use(bool)),
        "resume": schema.And(schema.Use(bool))
    })

    try:
        args = s.validate(args)
    except schema.SchemaError as e:
        print(__doc__)
        exit(f"Error: {e}")

    # File handler
    if args["--logfile"] is not None:
        fh = logging.FileHandler(f'{args["--logfile"]}')
        fh.setFormatter(logger.formatter)
        fh.setLevel(levels[args["--loglevel"]])
        logger.logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(levels[args["--loglevel"]])
    ch.setFormatter(logger.formatter)
    logger.logger.addHandler(ch)
    logger.logger.propagate = False

    root = logging.getLogger('')
    root_handler = root.handlers[0]
    root_handler.setFormatter(logger.formatter)
    root.setLevel(logging.INFO)

    url_list = []
    if args["<url_list>"] is not None:
        url_list = [n.strip() for n in args["<url_list>"].split(",")]
    elif args["<url_list_filename>"] is not None:
        with open(args["<url_list_filename>"], "rt") as ulf:
            for line in ulf:
                url_list.append(line.strip())

    locale_list = []
    if args["<locale_list>"] is not None:
        locale_list = [n.strip() for n in args["<locale_list>"].split(",")]

    if args["resume"]:
        try:
            c = crawler.Crawler.from_partial_download(args["<working_directory>"])
        except FileNotFoundError:
            print(__doc__)
            exit(f"Error: Cannot recover download from <working_directory> {args['<working_directory>']}")
    elif args["crawl"]:
        c = crawler.Crawler.from_cli_options(url_list, locale_list, args["<working_directory>"])
        c.max_pages = int(args["--max-pages"])
        c.slot_size = int(args["--simultaneous-pages"])
        if args["--patterns"] is not None:
            c.patterns = [i.strip() for i in args["--patterns"].split(",")]
    elif args["download"]:
        c = crawler.Crawler.create_downloader(url_list, args["<working_directory>"])
    else:
        print(__doc__)
        exit(f"Error: unsupported execution mode")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    c.crawl()


if __name__ == '__main__':
    main()
