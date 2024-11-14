import json
import os
import random
import re
import tempfile

import xxhash
from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError
from scrawl import tools, output, logger
from urllib.parse import urlparse
import zstandard

import numpy as np


class Crawler:
    def __init__(self, url_list, lang_code_list, destination):
        self.url = url_list
        self.original_url = self.url
        self.link_queue = []
        self.locales = lang_code_list
        self.visited = {i: set() for i in self.locales}
        self.hashes = set()
        self.hashes_click = {i: set() for i in self.locales}
        self.valid_hosts = {urlparse(url1).netloc.replace("www.", "") for url1 in self.url}
        self.patterns = [""]
        
        self.destination = destination
        self.idx = 0
        logger.logger.debug(self.url)
        logger.logger.debug(self.locales)
        self.max_pages = 10000
        self.no_links = 0
        self.max_no_links = 5
        self.current_locale = self.locales[0]
        self.slot_size = 10
        self.downloader = False

        os.makedirs(self.destination, exist_ok=True)
        os.makedirs(os.path.join(self.destination, "json"), exist_ok=True)
        os.makedirs(os.path.join(self.destination, "html"), exist_ok=True)

    @classmethod
    def from_cli_options(cls, url_list, lang_code_list, destination):
        return cls(url_list, lang_code_list, destination)

    @classmethod
    def from_partial_download(cls, directory):
        dumpfile = os.path.join(directory, "crawler.json.zst")
        if os.path.exists(dumpfile):
            with zstandard.open(dumpfile, "rt") as fdump:
                json_obj = json.loads(fdump.read())

                obj = cls(json_obj["url"], json_obj["locales"], directory)
                obj.url = json_obj["url"]
                obj.original_url = json_obj["original_url"]
                obj.link_queue = json_obj["link_queue"]
                obj.visited = {i: set(json_obj["visited"][i]) for i in json_obj["visited"]}
                obj.hashes = set(json_obj["hashes"])
                obj.hashes_click = {i: set(json_obj["hashes_click"][i]) for i in json_obj["hashes_click"]}
                obj.valid_hosts = set(json_obj["valid_hosts"])
                obj.patterns = set(json_obj["patterns"])
                obj.idx = json_obj["idx"]
                obj.max_pages = json_obj["max_pages"]
                obj.no_links = json_obj["no_links"]
                obj.max_no_links = json_obj["max_no_links"]
                obj.current_locale = json_obj["current_locale"]
                obj.slot_size = json_obj["slot_size"]
                obj.downloader = json_obj["downloader"]

                return obj
        else:
            raise FileNotFoundError

    @classmethod
    def create_downloader(cls, url_list, directory):
        obj = cls(url_list, ["en"], directory)
        obj.downloader = True
        return obj


    def store_result(self, json_string):
        self.idx += 1

        fname = os.path.join(os.path.join(self.destination, "json"), f"{self.idx:012d}.json.zst")
        logger.logger.info(f"Storing result in {fname}")
        with zstandard.open(fname, "wt") as rfile:
            rfile.write(json_string)

        if self.idx > self.max_pages:
            logger.logger.info(f"The limit of {self.max_pages} has been reached")
            raise ValueError("The limit Crawler.max_pages of {self.max_pages} has been reached")

        if (self.idx % 1000) == 0:
            logger.logger.info(f"Persisting the crawling state after {self.idx} iterations")
            self.persist()

    def try_to_accept_cookies(self, browser):
        for i in self.original_url:
            logger.logger.info(f"Trying to click accept in the cookies dialog at {i} if it does exist...")
            page = browser.new_page()

            try:
                page.goto(i)
            except PlaywrightError:
                #traceback.print_exc()
                try:
                    logger.logger.info(f"Failed to retrieve URL {i}, retrying one more time...")
                    page.goto(i)
                    logger.logger.warning(f"Finally {i} has been retrieved.")
                except PlaywrightError:
                    logger.logger.warning(f"Couldn't retrieve {i}, skipping...")
                    continue


            try:
                #page.wait_for_load_state("domcontentloaded", timeout=100)
                #page.wait_for_load_state("networkidle", timeout=100)
                page.wait_for_load_state("load", timeout=5000)
            except PlaywrightTimeoutError:
                continue

            try:
                l = page.get_by_role("button", name=re.compile(r"\bacep|\baccep|\bok\b|\bcontin",
                                                               re.IGNORECASE))
                expect(l.last).to_be_visible()
                l.last.click()
            except AssertionError:
                break
            except PlaywrightError:
                break

            page.close()

    def test_kelloggs_problem(self, my_playwright):
        logger.logger.info("Checking for K problem")
        with tempfile.TemporaryDirectory() as workdir:
            browser = my_playwright.chromium.launch_persistent_context(workdir, locale="en")
            page = browser.new_page()
            try:
                page.goto(self.original_url[0])
            except Exception as e:
                s = str(e)
                browser.close()
                if "ERR_HTTP2_PROTOCOL_ERROR" in s:
                    logger.logger.info("K problem found: using Firefox")
                    return True
                else:
                    logger.logger.info("K problem not found")
                    return False
            browser.close()
            page.close()
            logger.logger.info("K problem not found")
            return False

    def download(self, default_browser, workdir):
        logger.logger.info(f"Downloading URL list...")
        dir_context = os.path.join(workdir, "en")
        os.mkdir(dir_context)
        browser = default_browser.launch_persistent_context(dir_context, locale="en")

        if len(self.link_queue) == 0:
            for i in self.url:
                self.link_queue.append(i)
        else:
            logger.logger.info("Resuming partial download...")

        while True:
            if len(self.link_queue) == 0:
                return
            u = self.link_queue[0]

            p = None
            try:
                logger.logger.info(f"Trying to download {u}")
                p = browser.new_page()
                p.goto(u, wait_until="commit", timeout=5000)
            except PlaywrightError:
                try:
                    logger.logger.warning(f"Failed to retrieve URL {u}, retrying one more time...")
                    if p:
                        p.goto(u, wait_until="commit", timeout=5000)
                        logger.logger.warning(f"Finally {u} has been retrieved.")
                except PlaywrightError:
                    logger.logger.warning(f"Couldn't retrieve {u}, skipping...")
                    self.visited["en"].add(u)
                    self.link_queue.pop(0)
                    if p:
                        p.close()
                    continue
            try:
                # tools.scroll_down(p, 20)
                #p.wait_for_load_state("domcontentloaded", timeout=100)
                #p.wait_for_load_state("networkidle", timeout=100)
                p.wait_for_load_state("load",
                                      timeout=5000)  # main mechanism to wait for pages to be loaded
            except PlaywrightTimeoutError:
                logger.logger.warning("Operation timed out.")
                self.link_queue.pop(0)
                p.close(run_before_unload=False)
                continue

            try:
                p_content = p.content()
            except Exception:
                p_content = ""

            self.store_result(json.dumps({"lang": "en",
                                          "url": p.url,
                                          "html": p_content,
                                          "hash": xxhash.xxh64(p.text_content("body")).hexdigest()}))
            self.link_queue.pop(0)
            p.close()


    def crawl(self):
        with (tempfile.TemporaryDirectory() as workdir):
            with sync_playwright() as pw:
                default_browser = pw.chromium
                if self.test_kelloggs_problem(pw):
                    default_browser = pw.firefox

                if self.downloader:
                    self.download(default_browser, workdir)
                else:
                    for lang_code in self.locales[self.locales.index(self.current_locale):]:
                        self.current_locale = lang_code

                        logger.logger.info(f"Starting with [{lang_code}] locale...")
                        dir_context = os.path.join(workdir, lang_code)
                        os.mkdir(dir_context)
                        browser = default_browser.launch_persistent_context(dir_context, locale=lang_code)

                        """
                        Experimental support for cookie dialog: search any button containing accep acep ok and click
                        in the entry page
                        """
                        self.try_to_accept_cookies(browser)

                        # if not resuming stopped crawl
                        if len(self.link_queue) == 0:
                            for i in self.url:
                                self.link_queue.append(i)
                        else:
                            logger.logger.info("Resuming partial crawl...")

                        self.link_queue = list(set(self.link_queue))  # unique links, important

                        while True:
                            no_action_performed = True
                            indices = random.sample(range(len(self.link_queue)),
                                                    min(len(self.link_queue), self.slot_size))
                            next_urls = [self.link_queue[n] for n in indices]

                            pages = []
                            for u in next_urls:
                                try:
                                    p = browser.new_page()
                                    p.goto(u, wait_until="commit", timeout=5000)
                                    pages.append(p)
                                except PlaywrightError:
                                    try:
                                        logger.logger.warning(f"Failed to retrieve URL {u}, retrying one more time...")
                                        p.goto(u, wait_until="commit", timeout=5000)
                                        logger.logger.warning(f"Finally {u} has been retrieved.")
                                    except PlaywrightError:
                                        logger.logger.warning(f"Couldn't retrieve {u}, skipping...")
                                        self.visited[lang_code].add(u)
                                        p.close()
                                        pages = pages[0:-1]
                                        continue

                            for p in pages:
                                try:
                                    # tools.scroll_down(p, 20)
                                    #p.wait_for_load_state("domcontentloaded", timeout=100)
                                    #p.wait_for_load_state("networkidle", timeout=100)
                                    p.wait_for_load_state("load",
                                                          timeout=5000)  # main mechanism to wait for pages to be loaded
                                except PlaywrightTimeoutError:
                                    p.close(run_before_unload=False)
                                    continue

                                if p.url in self.visited[lang_code]:
                                    p.close(run_before_unload=False)
                                    continue
                                if not tools.is_valid_host(self.valid_hosts, p.url, self.patterns):
                                    p.close(run_before_unload=False)
                                    continue
                                try:
                                    current_hash = xxhash.xxh64(p.text_content("body")).hexdigest()
                                    if current_hash in self.hashes:
                                        p.close(run_before_unload=False)
                                        continue
                                except Exception:
                                    continue

                                self.hashes.add(current_hash)
                                logger.logger.debug(p.text_content("body"))
                                logger.logger.info(f"Storing URL {p.url}")
                                try:
                                    self.store_result(json.dumps({"lang": lang_code,
                                                                  "url": p.url,
                                                                  "html": p.content(),
                                                                  # "text": p.text_content("body"),
                                                                  "hash": current_hash}))
                                except ValueError:
                                    logger.logger.warning(f"Maximum number of {self.max_pages} pages has been reached")
                                    logger.logger.info("Crawling ends. Generating HTML output")
                                    json_src = os.path.join(self.destination, "json")
                                    html_trg = os.path.join(self.destination, "html")
                                    output.generate_output(json_src, html_trg)
                                    return

                                self.visited[lang_code].add(p.url)
                                no_action_performed = False

                                # Links from the HTML code: <a href> + <link rel alternate>
                                try:
                                    p_content = p.content()
                                except Exception:
                                    p_content = ""

                                more_links, discarded = tools.retrieve_more_links(self.valid_hosts, p.url, p_content, self.patterns)

                                for link in discarded:
                                    if link not in self.visited[lang_code]:
                                        logger.logger.info(f"Discarding link {link}")
                                        self.visited[lang_code].add(link)

                                for link in more_links:
                                    if link not in self.visited[lang_code]:
                                        self.link_queue.append(link)

                                p.close(run_before_unload=False)

                            self.link_queue = list(np.delete(self.link_queue, indices))
                            self.link_queue = list(set(self.link_queue))  # unique links

                            if no_action_performed:
                                self.link_queue = [i for i in self.link_queue if i not in self.visited[lang_code]]
                                if len(self.link_queue) > 0:
                                    continue
                                else:
                                    break

        logger.logger.info("Crawling ends. Generating HTML output")
        json_src = os.path.join(self.destination, "json")
        html_trg = os.path.join(self.destination, "html")
        output.generate_output(json_src, html_trg)

        core_file = os.path.join(self.destination, "crawler.json.zst")
        if os.path.exists(core_file):
            logger.logger.info("Cleaning persistent crawler file")
            os.unlink(core_file)

    def to_json(self):
        obj = {
            "url": self.url,
            "original_url": self.original_url,
            "link_queue": self.link_queue,
            "locales": self.locales,
            "visited": {i: list(self.visited[i]) for i in self.visited},
            "hashes": list(self.hashes),
            "hashes_click": {i: list(self.hashes_click[i]) for i in self.hashes_click},
            "valid_hosts": list(self.valid_hosts),
            "patterns": self.patterns,
            "destination": self.destination,
            "idx": self.idx,
            "max_pages": self.max_pages,
            "no_links": self.no_links,
            "max_no_links": self.max_no_links,
            "current_locale": self.current_locale,
            "slot_size": self.slot_size,
            "downloader": self.downloader
        }

        return obj

    def persist(self):
        with zstandard.open(os.path.join(self.destination, "crawler.json.zst"), "wt") as fstore:
            fstore.write(json.dumps(self.to_json()))
