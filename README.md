# Scrawl

Scrawl is a playwright-based web crawler. It crawls the web using Playwright and real web browsers.

```
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
``` 

## Installation

This is the whole process, including the creation of the virtual environment for Python. It requires python 10+.

```bash
$ python3 -m venv venv
$ source venv/bin/activate
$ pip install poetry
$ git clone https://github.com/bitextor/scrawl.git
$ cd scrawl
$ poetry update && poetry build
$ pip install dist/*.whl
$ playwright install
```
## Example

```bash
$ scrawl crawl en,es https://mydomain.here output_directory
```


**Acknowledgments**

Scrawl has been developed within Smartbic, a project funded by the NextGenerationEU funds of the Spanish Government through the grants for Artificial Intelligence Research and Development projects and other digital technologies and their implementation in value chains (C005/21-ED) by “Entidad Pública Empresarial RED.ES, M.P.”, grant number 2021/C005/00150077.

