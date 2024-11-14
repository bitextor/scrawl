import errno
import os
import sys
import re
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from babel import Locale
from tld import get_tld
import time
from scrawl import logger

ERROR_INVALID_NAME = 123
FORBIDDEN_DOCUMENTS = (r"(.| )+\.(pdf|pptx?|xlsx?|docx?|ods|odt|odf|odp|css|rss|js|jpeg|jpg|gif|webm|webp|tiff|ps|gz|png|"
                       r"mp3|mp4|ogg|wav|aif|cda|mid|midi|wma|wpl|7z|arj|zip|gz|gzip|tar|rar|pkg|deb|rpm|z|bin|dmg|"
                       r"iso|toast|vcd|csv|dat|db|dbf|sql|sav|mdb|ttf|otf|fon|fnt|ai|bmp|ico|psd|scr|svg|tif|key|3g2|"
                       r"3gp|mkv|avi|flv|h264|m4v|mov|mpg|mpeg|rm|swf|vob|wmv|rtf|wpd|wsdl|xsd)$")

def is_pathname_valid(pathname: str) -> bool:
    """
    `True` if the passed pathname is a valid pathname for the current OS;
    `False` otherwise.
    """
    try:
        if not isinstance(pathname, str) or not pathname:
            return False
        _, pathname = os.path.splitdrive(pathname)
        root_dirname = os.environ.get('HOMEDRIVE', 'C:') \
            if sys.platform == 'win32' else os.path.sep
        assert os.path.isdir(root_dirname)
        root_dirname = root_dirname.rstrip(os.path.sep) + os.path.sep

        for pathname_part in pathname.split(os.path.sep):
            try:
                os.lstat(root_dirname + pathname_part)
            except OSError as exc:
                if hasattr(exc, 'winerror'):
                    if exc.winerror == ERROR_INVALID_NAME:
                        return False
                elif exc.errno in {errno.ENAMETOOLONG, errno.ERANGE}:
                    return False
    except TypeError:
        return False
    else:
        return True


def is_path_creatable(pathname: str) -> bool:
    """
    `True` if the current user has sufficient permissions to create the passed
    pathname; `False` otherwise.
    """

    dirname = os.path.dirname(pathname) or os.getcwd()
    return os.access(dirname, os.W_OK)


def is_path_exists_or_creatable(pathname: str) -> bool:
    """
    `True` if the passed pathname is a valid pathname for the current OS _and_
    either currently exists or is hypothetically creatable; `False` otherwise.

    This function is guaranteed to _never_ raise exceptions.
    """
    try:
        return is_pathname_valid(pathname) and (
                os.path.exists(pathname) or is_path_creatable(pathname))
    except OSError:
        return False


def is_valid_host(valid_hosts, url2, patterns):
    try:
        if re.match(r"^mailto:", url2):
            return False
        valid_domains = {get_tld(i, as_object=True, fix_protocol=True).domain for i in valid_hosts}
        url2_domain = get_tld(url2, as_object=True, fix_protocol=True).domain

    except:
        return False

    return url2_domain in valid_domains and any(i in url2 for i in patterns)
    # return urlparse(url2).netloc.replace("www.", "") in valid_hosts and any(i in url2 for i in patterns)

def sanitize_url(url):
    o = urlparse(url)
    path = re.sub(r"[/]+", "/", o.path)
    query = ""
    if o.query != "":
        query = f"?{o.query}"

    return f"{o.scheme}://{o.netloc}{path}{query}".split("#")[0]


def filter_urls(urls, links, valid_hosts, patterns):
    global FORBIDDEN_DOCUMENTS
    links_filtered = [sanitize_url(n) for n in (urls + links) if is_valid_host(valid_hosts, n, patterns)]

    l2 = []
    for i in links_filtered:
        if re.match(FORBIDDEN_DOCUMENTS, i, re.IGNORECASE|re.DOTALL):
            logger.logger.info(f"Unsupported filetype of URL: {i}")
            l2.append(i)

    links_filtered2 = [i.split("#")[0] for i in links_filtered if not re.match(FORBIDDEN_DOCUMENTS, i, re.IGNORECASE|re.DOTALL)]

    return list(set(links_filtered2)), l2


def retrieve_more_links(valid_hosts, url, page_content, patterns):
    global FORBIDDEN_DOCUMENTS
    links = []

    soup = BeautifulSoup(page_content, "lxml")
    for i in soup.find_all("link"):
        if "href" in i.attrs and "rel" in i.attrs and "alternate" in i["rel"] and is_valid_host(valid_hosts, i["href"],
                                                                                                patterns):
            links.append(sanitize_url(i["href"]))
    for i in soup.find_all("a"):
        if "href" in i.attrs:
            u = urljoin(url, i["href"])
            if is_valid_host(valid_hosts, u, patterns):
                links.append(sanitize_url(u))

    links = list(set(links))

    links2 = []
    for i in links:
        if re.match(FORBIDDEN_DOCUMENTS, i, re.IGNORECASE|re.DOTALL):
            logger.logger.info(f"Unsupported filetype of URL: {i}")
            links2.append(i)


    links = [i.split("#")[0] for i in links if not re.match(FORBIDDEN_DOCUMENTS, i, re.IGNORECASE|re.DOTALL)]

    return links, links2


def scroll_down(page, scrolls):
    _prev_height = -1
    _max_scrolls = scrolls
    _scroll_count = 0
    while _scroll_count < _max_scrolls:
        # Execute JavaScript to scroll to the bottom of the page
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        # Wait for new content to load (change this value as needed)
        page.wait_for_timeout(1000)
        # Check whether the scroll height changed - means more pages are there
        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == _prev_height:
            break
        _prev_height = new_height
        _scroll_count += 1
