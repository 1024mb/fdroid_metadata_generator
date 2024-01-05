import argparse
import html
import os
import re
import urllib.request
from typing import Dict

import yaml


def main():
    parser = argparse.ArgumentParser(description="Parser for PlayStore information to F-Droid YML metadata files.")
    parser.add_argument("-d", "--dir", help="Directory where F-Droid metadata files are stored", required=True)
    parser.add_argument("-l", "--language", help="Language of the information to retrieve", required=True)

    args = parser.parse_args()

    fdroid_dir = os.path.abspath(args.dir)
    lang = args.language

    supported_langs = ["af", "am", "bg", "ca", "zh-HK", "zh-CN", "zh-TW", "hr", "cs", "da", "nl", "en-GB", "en-US",
                       "et", "fil", "fi", "fr-CA", "fr-FR", "de", "el", "he", "hi", "hu", "is", "id", "in", "it", "ja",
                       "ko", "lv", "lt", "ms", "no", "pl", "pt-BR", "pt-PT", "ro", "ru", "sr", "sk", "sl", "es-419",
                       "es-ES", "sw", "sv", "th", "tr", "uk", "vi", "zu"]

    lang = sanitize_lang(lang)

    if lang not in supported_langs:
        print("Invalid language")
        exit(1)

    retrieve_info(fdroid_dir, lang)


def retrieve_info(fdroid_dir, lang):
    # https://play.google.com/store/apps/details?id=org.diasurgical.devilutionx&hl=es-419&gl=pe

    playstore_url = "https://play.google.com/store/apps/details?id="

    package_list = os.listdir(fdroid_dir)

    for package in package_list:
        playstore_url_comp_int = playstore_url + os.path.basename(package) + "&hl=en-US"
        playstore_url_comp = playstore_url + os.path.basename(package) + "&hl=" + lang
        resp = urllib.request.urlopen(playstore_url_comp).read()
        resp_int = urllib.request.urlopen(playstore_url_comp_int).read()
        package_content = yaml.load(os.path.join(fdroid_dir, package))  # type:Dict

        try:
            package_content["AuthorName"] = \
                html.unescape(
                    re.search(r"div\sclass=\"Vbfug\sauoIOc\"><a\shref[^>]+><span>(.+?)<\/span>", resp).group(1))
        except IndexError:
            pass

        website = ""
        try:
            website = \
                re.search(r"<meta\sname=\"appstore:developer_url\"\scontent=\"([^\"]+)\"><meta", resp).group(1)
        except IndexError:
            pass

        if website != "":
            package_content["WebSite"] = website

        # https://github.com/JosefNemec/Playnite/releases/tag/10.32
        if "https://github.com/" in website or "http://github.com/" in website:
            repo = re.sub(r"(https?)(://github.com/[^/]+/[^/]+).+", "https\2", website)
            package_content["IssueTracker"] = repo + "/issues"
            package_content["SourceCode"] = repo
            package_content["Changelog"] = repo + "/releases/latest"
            package_content["Repo"] = repo
        elif "https://gitlab.com/" in website or "http://gitlab.com/" in website:
            repo = re.sub(r"(https?)(://gitlab.com/[^/]+/[^/]+).+", "https\2", website)
            package_content["IssueTracker"] = repo + "/-/issues"
            package_content["SourceCode"] = repo
            package_content["Changelog"] = repo + "/-/releases"
            package_content["Repo"] = repo

        cat_list = []

        pattern = (r"<span\sjsname=\"V67aGc\"\sclass=\"VfPpkd-vQzf8d\"\saria-hidden=\"true\">(["
                   r"^<]+)<\/span><a\sclass=\"WpHeLc\sVfPpkd-mRLv6\sVfPpkd-RLmnJb\"\shref=\"\/store\/("
                   r"apps\/category|search\?)")

        ret_grp = re.search(pattern, resp)

        for i, cat in ret_grp:
            if i != 0:
                cat_list.append(html.unescape(cat))

        package_content["Categories"] = cat_list

        package_content["Name"] = html.unescape(
            re.search(r"itemprop=\"name\">(.+?)<\/h1>", resp).group(1))

        package_content["Summary"] = html.unescape(
            re.search(r"<div\sclass=\"[^\"]+\"\sdata-g-id=\"description\">(.+?)<br>", resp).group(1))

        package_content["Description"] = html.unescape(
            re.search(r"<div\sclass=\"[^\"]+\"\sdata-g-id=\"description\">(.+?)<\/div>", resp).group(1)).replace("<br>",
                                                                                                                 "\n")

        package_content["AuthorEmail"] = html.unescape(
            re.search(r"<div\sclass=\"xFVDSb\">.+?<\/div><div\sclass=\"pSEeg\">(.+?)<\/div>", resp).group(1))

        anti_features = ["UpstreamNonFree", "NonFreeAssets"]

        if re.search(r">Contains\sads<\/span>", resp_int) is not None:
            anti_features.append("Ads")

        if re.search(r">In-app\spurchases<\/span>", resp_int) is not None:
            anti_features.append("NonFreeDep")
            anti_features.append("NonFreeNet")

        
def sanitize_lang(lang):
    lang = lang.lower()

    match lang:
        case "es":
            lang = "es-Es"
        case "419":
            lang = "es-419"
        case "en":
            lang = "en-US"
        case "us":
            lang = "en-US"
        case "pt":
            lang = "pt-PT"
        case "fr":
            lang = "fr-FR"
        case "zh":
            lang = "zh-CN"
        case "br":
            lang = "pt-BR"
        case "gb":
            lang = "en-GB"
        case "ca":
            lang = "fr-CA"
        case "hk":
            lang = "zh-HK"
        case "tw":
            lang = "zh-TW"

    return lang


if __name__ == "__main__":
    main()
