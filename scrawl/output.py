import glob
import json
import os

import xxhash
import zstandard


def read_json_object(fname):
    with zstandard.open(fname, "r") as f:
        return json.loads(f.read())


def sanitize_filename(filename_str):
    def is_valid(s):
        return s.isalpha() or s.isdigit() or s in {".", "-", "_"}

    return "".join([c if is_valid(c) else "_" for c in filename_str]).rstrip()


def truncate_filename_part(filename_part):
    if len(filename_part) > 80:
        h = xxhash.xxh64(filename_part).hexdigest()
        return filename_part[0:80-len(h)] + h
    else:
        return filename_part


def get_filename(prefix, url, counter):
    miurl = url.replace("//", "/")
    parts = [truncate_filename_part(i) for i in miurl.split("/")]

    filename = "/".join([sanitize_filename(i) for i in parts[1:]]) + f"/crawled_page_{counter}.html"

    filename = filename.replace("//","/")
    fullpath = f"{prefix}/{filename}".replace("//", "/")
    return fullpath, filename


def generate_output(source_path, target_path):
    counter = 0
    relpaths = []
    for jsonfile in glob.iglob(f"{source_path}/*.json.zst"):
        obj = read_json_object(jsonfile)
        url = obj["url"]
        counter += 1
        filename, relpath = get_filename(target_path, url, counter)
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "w") as f:
            f.write(obj["html"])
        relpaths.append(relpath)

    special_file = f"{target_path}/index.html"
    with open(special_file, "wt") as findex:
        print("<html><head></head><body>", file=findex)
        for i in relpaths:
            print(f"<a href='{i}'>page</a>", file=findex)
        print("</body></html>", file=findex)


