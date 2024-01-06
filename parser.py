from __future__ import annotations

import argparse
import html
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
from typing import Dict, List
from urllib.error import HTTPError

import yaml
from yaml import Loader, Dumper

from dep.apkfile_fork import ApkFile


def main():
    parser = argparse.ArgumentParser(description="Parser for PlayStore information to F-Droid YML metadata files.")
    parser.add_argument("-m", "--metadata-dir",
                        help="Directory where F-Droid metadata files are stored.")
    parser.add_argument("-r", "--repo-dir",
                        help="Directory where F-Droid repo files are stored.")
    parser.add_argument("-l", "--language",
                        help="Language of the information to retrieve.",
                        required=True)
    parser.add_argument("-f", "--force",
                        help="Force parsing of information and overwrite existing metadata.",
                        action="store_true")
    parser.add_argument("-fv", "--force-version",
                        help="Force updating version name and code even if they are already specified in the YML file.",
                        action="store_true")
    parser.add_argument("-cs", "--convert-apks",
                        help="Convert APKS files to APK and sign them.",
                        action="store_true")
    parser.add_argument("-k", "--key-file",
                        help="Key file used to sign the APK, required if --convert-apks is used.",
                        nargs=1)
    parser.add_argument("-c", "--cert-file",
                        help="Cert file used to sign the APK, required if --convert-apks is used.",
                        nargs=1)
    parser.add_argument("-cp", "--certificate-password",
                        help="Password to sign the APK.",
                        nargs=1)
    parser.add_argument("-bt", "--build-tools-path",
                        help="Path to Android SDK buildtools binaries.",
                        nargs=1)
    parser.add_argument("-ae", "--apk-editor-path",
                        help="Path to the ApkEditor.jar file.",
                        nargs=1)
    parser.add_argument("-ds", "--download-screenshots",
                        help="Download screenshots which will be stored in the repo directory.",
                        action="store_true")

    args = parser.parse_args()

    if args.metadata_dir is None and args.repo_dir is None:
        print("Please provide either the metadata directory or the repository directory.")
        exit(1)

    if args.metadata_dir is not None and args.repo_dir is not None:
        print("Please provide only the metadata directory or the repository directory. Not both.")
        exit(1)

    if args.metadata_dir is not None and len(args.metadata_dir) == 0:
        print("Metadata directory path cannot be empty.")
        exit(1)

    if args.repo_dir is not None and len(args.repo_dir) == 0:
        print("Repo directory path cannot be empty.")
        exit(1)

    if args.metadata_dir is not None:
        metadata_dir = os.path.abspath(args.metadata_dir)
        if os.path.split(metadata_dir)[1] != "metadata":
            print("Metadata directory path doesn't look like a F-Droid repository metadata directory, aborting...")
            exit(1)

    if args.repo_dir is not None:
        repo_dir = os.path.abspath(args.repo_dir)
        if os.path.split(repo_dir)[1] != "repo":
            print("Repo directory path doesn't look like a F-Droid repository directory, aborting...")
            exit(1)

    if shutil.which("aapt") is None:
        print("Please install aapt before running this script.")

    if shutil.which("aapt2") is None:
        print("Please install aapt2 before running this script.")

    # Source: https://support.google.com/googleplay/android-developer/table/4419860?hl=en
    supported_langs = ["af", "am", "bg", "ca", "zh-HK", "zh-CN", "zh-TW", "hr", "cs", "da", "nl", "en-GB", "en-US",
                       "et", "fil", "fi", "fr-CA", "fr-FR", "de", "el", "he", "hi", "hu", "is", "id", "in", "it", "ja",
                       "ko", "lv", "lt", "ms", "no", "pl", "pt-BR", "pt-PT", "ro", "ru", "sr", "sk", "sl", "es-419",
                       "es-ES", "sw", "sv", "th", "tr", "uk", "vi", "zu"]

    lang = sanitize_lang(args.language)

    if lang not in supported_langs:
        print("Invalid language")
        exit(1)

    if args.convert_apks:
        if args.build_tools_path is None and shutil.which("apksigner") is None:
            print("Please install the build-tools package of the Android SDK if you want to convert APKS files.")
            exit(1)

        if args.build_tools_path is not None:
            if (not os.path.exists(os.path.abspath(args.build_tools_path[0])) or
                    not os.path.isdir(os.path.abspath(args.build_tools_path[0]))):
                print("Invalid build-tools path.")
                exit(1)

        if shutil.which("java") is None:
            print("Please install java if you want to convert APKS files.")
            exit(1)

        if args.apk_editor_path is None:
            print("Please specify the full path of the ApkEditor.jar file.")
            exit(1)
        elif (not os.path.exists(os.path.abspath(args.apk_editor_path[0])) or
              not os.path.isfile(os.path.abspath(args.apk_editor_path[0]))):
            print("Invalid ApkEditor.jar path.")
            exit(1)

    if args.key_file is not None:
        if not os.path.exists(os.path.abspath(args.key_file[0])) or not os.path.isfile(
                os.path.abspath(args.key_file[0])):
            print("Invalid key file path.")
            exit(1)

    if args.cert_file is not None:
        if not os.path.exists(os.path.abspath(args.cert_file[0])) or not os.path.isfile(
                os.path.abspath(args.cert_file[0])):
            print("Invalid cert file path.")
            exit(1)

    package_list = []
    package_and_version = {}  # type: Dict[str: List[int, str]]

    if "metadata_dir" in locals():
        if not os.path.isdir(metadata_dir):
            print("Invalid metadata directory, supplied path is not a directory")
            exit(1)

        repo_dir = os.path.join(os.path.split(metadata_dir)[0], "repo")

        if args.convert_apks:
            convert_apks(key_file=args.key_file[0], cert_file=args.cert_file[0], password=args.certificate_password,
                         repo_dir=repo_dir, build_tools_path=args.build_tools_path,
                         apk_editor_path=args.apk_editor_path[0])

        mapped_apk_files = map_apk_to_packagename(repo_dir)

        for item in os.listdir(metadata_dir):
            base_name = os.path.splitext(item)[0]
            try:
                apk_file_path = os.path.join(repo_dir, mapped_apk_files[base_name])
            except KeyError:
                apk_file_path = None

            if os.path.splitext(item)[1].lower() != ".yml":
                print("Skipping " + item)
            else:
                package_list.append(base_name)
                if apk_file_path is not None and os.path.exists(apk_file_path) and os.path.isfile(apk_file_path):
                    package_and_version[base_name] = ApkFile(apk_file_path).version_code, ApkFile(
                            apk_file_path).version_name
                else:
                    package_and_version[base_name] = 0, "0"

        retrieve_info(package_list, package_and_version, lang, metadata_dir, repo_dir, args.force, args.force_version,
                      args.download_screenshots)
    elif "repo_dir" in locals():
        if not os.path.isdir(repo_dir):
            print("Invalid repo directory, supplied path is not a directory")
            exit(1)

        if args.convert_apks:
            convert_apks(key_file=args.key_file[0], cert_file=args.cert_file[0], password=args.certificate_password,
                         repo_dir=repo_dir, build_tools_path=args.build_tools_path,
                         apk_editor_path=args.apk_editor_path[0])

        metadata_dir = os.path.join(os.path.split(repo_dir)[0], "metadata")

        for apk_file in os.listdir(repo_dir):
            apk_file_path = os.path.join(repo_dir, apk_file)

            if os.path.isfile(os.path.join(repo_dir, apk_file)) and os.path.splitext(apk_file)[1].lower() == ".apk":
                package_list.append(ApkFile(apk_file_path).package_name)
                package_and_version[ApkFile(apk_file_path).package_name] = ApkFile(apk_file_path).version_code, ApkFile(
                        apk_file_path).version_name

        retrieve_info(package_list, package_and_version, lang, metadata_dir, repo_dir, args.force, args.force_version,
                      args.download_screenshots)
    else:
        print("We shouldn't have got here.")
        exit(1)


def convert_apks(key_file: str, cert_file: str, password: List[str] | None, repo_dir: str,
                 build_tools_path: List[str] | None, apk_editor_path: str):
    print("Starting APKS conversion...")

    if platform.system() == "Windows":
        try:
            from win32_setctime import setctime
        except ImportError:
            setctime = None
            print(
                    "win32_setctime module is not installed, creation times wont be restored for the converted APK files.")

    if build_tools_path is not None:
        apksigner_path = "\"" + os.path.join(build_tools_path[0], "apksigner") + "\""
    else:
        apksigner_path = "\"" + shutil.which("apksigner") + "\""

    if password is not None:
        sign_command = apksigner_path + " sign --key \"" + key_file + "\" --cert \"" + cert_file + "\" --key-pass pass:" + \
                       password[0] + " --in \"%s\" --out \"%s\""
    else:
        sign_command = (apksigner_path + " sign --key \"" + key_file + "\" --cert \"" + cert_file +
                        "\" --key-pass pass: --in \"%s\" --out \"%s\"")

    convert_command = "java -jar \"" + apk_editor_path + "\" m -i \"%s\" -o \"%s\" -f"

    proc = False

    for file in os.listdir(repo_dir):
        if os.path.splitext(file)[1].lower() == ".apks":
            try:
                apks_path = os.path.join(repo_dir, file)
                apk_path_unsigned = os.path.join(repo_dir, os.path.splitext(file)[0] + "_unsigned.apk")
                apk_path_signed = os.path.join(repo_dir, os.path.splitext(file)[0] + ".apk")

                old_app_stats = os.lstat(apks_path)

                subprocess.run(convert_command % (apks_path, apk_path_unsigned))

                try:
                    subprocess.run(sign_command % (apk_path_unsigned, apk_path_signed))
                    os.utime(apk_path_signed, (old_app_stats.st_atime, old_app_stats.st_mtime))
                    if platform.system() == "Windows" and "win32_setctime" in sys.modules:
                        setctime(apk_path_signed, old_app_stats.st_birthtime)
                    os.remove(apks_path)
                    os.remove(apk_path_unsigned)
                    proc = True
                except subprocess.CalledProcessError as e:
                    print("There was an error signing " + os.path.splitext(file)[0] + ".apk\nError: %s" % e)
                    continue
                except PermissionError:
                    print("Error deleting file " + os.path.join(repo_dir, file) + ". Permission denied")
                    continue
            except subprocess.CalledProcessError as e:
                print("There was an error converting " + file + " to .apk\nError: %s" % e)
                continue

    if proc:
        print("Finished converting all APKS files.")
    else:
        print("No APKS files were converted.")


def map_apk_to_packagename(repo_dir: str) -> Dict:
    mapped_apk_files = {}

    for apk_file in os.listdir(repo_dir):
        apk_file_path = os.path.join(repo_dir, apk_file)
        if os.path.isfile(apk_file_path) and os.path.splitext(apk_file_path)[1].lower() == ".apk":
            mapped_apk_files[ApkFile(apk_file_path).package_name] = apk_file

    return mapped_apk_files


def retrieve_info(package_list: list, package_and_version: dict, lang: str, metadata_dir: str, repo_dir: str,
                  force: bool, force_version: bool, dl_screenshots: bool):
    playstore_url = "https://play.google.com/store/apps/details?id="

    for package in package_list:
        print("Processing " + package + "...")

        playstore_url_comp_int = playstore_url + package + "&hl=en-US"
        playstore_url_comp = playstore_url + package + "&hl=" + lang

        try:
            resp = urllib.request.urlopen(playstore_url_comp).read().decode()
        except HTTPError as e:
            if e.code == 404:
                print("%s was not found on the Play Store." % package)
            continue

        try:
            resp_int = urllib.request.urlopen(playstore_url_comp_int).read().decode()
        except HTTPError as e:
            if e.code == 404:
                print("%s was not found on the Play Store." % package)
            continue

        if ">We're sorry, the requested URL was not found on this server.</div>" in resp_int:
            print("%s was not found on the Play Store." % package)
            continue

        if os.path.exists(os.path.join(metadata_dir, package + ".yml")):
            try:
                stream = open(os.path.join(metadata_dir, package + ".yml"), "r", encoding="utf_8")
                package_content = yaml.load(stream, Loader=Loader)  # type:Dict
                stream.close()
            except PermissionError:
                print("Couldn't read metadata file, permission denied.")
                continue
        else:
            package_content = {}

        try:
            if package_content.get("AuthorName", "") == "" or force:
                package_content["AuthorName"] = \
                    html.unescape(
                            re.search(r"div\sclass=\"Vbfug\sauoIOc\"><a\shref[^>]+><span>(.+?)<\/span>", resp).group(
                                    1)).strip()
        except (IndexError, AttributeError):
            print("WARNING: Couldn't get the Author name.")

        website = ""
        try:
            website = \
                re.search(r"<meta\sname=\"appstore:developer_url\"\scontent=\"([^\"]+)\"><meta", resp).group(1).strip()
        except (IndexError, AttributeError):
            print("WARNING: Couldn't get the website.")

        if website != "" and (package_content.get("WebSite", "") == "" or force):
            package_content["WebSite"] = website.replace("http://", "https://")

        if "https://github.com/" in website or "http://github.com/" in website:
            repo = re.sub(r"(https?)(://github.com/[^/]+/[^/]+).*", r"https\2", website)
            if package_content.get("IssueTracker", "") == "" or force:
                package_content["IssueTracker"] = repo + "/issues"
            if package_content.get("SourceCode", "") == "" or force:
                package_content["SourceCode"] = repo
            if package_content.get("Changelog", "") == "" or force:
                package_content["Changelog"] = repo + "/releases/latest"
            if package_content.get("Repo", "") == "" or force:
                package_content["Repo"] = repo
        elif "https://gitlab.com/" in website or "http://gitlab.com/" in website:
            repo = re.sub(r"(https?)(://gitlab.com/[^/]+/[^/]+).*", r"https\2", website)
            if package_content.get("IssueTracker", "") == "" or force:
                package_content["IssueTracker"] = repo + "/-/issues"
            if package_content.get("SourceCode", "") == "" or force:
                package_content["SourceCode"] = repo
            if package_content.get("Changelog", "") == "" or force:
                package_content["Changelog"] = repo + "/-/releases"
            if package_content.get("Repo", "") == "" or force:
                package_content["Repo"] = repo

        pattern = (r"<span\sjsname=\"V67aGc\"\sclass=\"VfPpkd-vQzf8d\"\saria-hidden=\"true\">(["
                   r"^<]+)<\/span><a\sclass=\"WpHeLc\sVfPpkd-mRLv6\sVfPpkd-RLmnJb\"\shref=\"\/store\/("
                   r"?:apps\/category|search\?)")

        if package_content.get("Categories", "") == "" or force:
            ret_grp = re.search(pattern, resp_int)

            if ret_grp is not None:
                cat_list = extract_categories(ret_grp, resp_int)
                package_content["Categories"] = cat_list
            else:
                print("WARNING: Couldn't get the categories.")

        if package_content.get("Name", "") == "" or force:
            try:
                package_content["Name"] = html.unescape(
                        re.search(r"itemprop=\"name\">(.+?)<\/h1>", resp).group(1)).strip()
            except (IndexError, AttributeError):
                print("WARNING: Couldn't get the application name.")

        if package_content.get("Summary", "") == "" or force:
            try:
                summary = html.unescape(
                        re.search(r"<div\sclass=\"[^\"]+\"\sdata-g-id=\"description\">(.+?)<br>", resp).group(
                                1)).strip()

                while len(summary) > 80:
                    try:
                        summary = re.search(r"(^.+\.)\s+.+$", summary).group(1)
                    except (IndexError, AttributeError):
                        summary = re.search(r"^(.+)\s\S+\s*$", summary[:77]).group(1) + "..."

                package_content["Summary"] = summary
            except (IndexError, AttributeError):
                print("WARNING: Couldn't get the summary.")

        if package_content.get("Description", "") == "" or force:
            try:
                package_content["Description"] = html.unescape(
                        re.search(r"<div\sclass=\"[^\"]+\"\sdata-g-id=\"description\">(.+?)<\/div>", resp).group(
                                1)).replace(
                        "<br>", "\n").strip()  # TODO: Test without replacing <br> as it's supported in F-Droid.
            except (IndexError, AttributeError):
                print("WARNING: Couldn't get the description.")

        if package_content.get("AuthorEmail", "") == "" or force:
            try:
                email_grps = re.findall(r"<div\sclass=\"xFVDSb\">.+?<\/div><div\sclass=\"pSEeg\">(.+?)<\/div>",
                                        resp)

                for item in email_grps:
                    if "@" not in item:
                        continue
                    else:
                        package_content["AuthorEmail"] = item
                        break
            except (IndexError, AttributeError):
                print("WARNING: Couldn't get the Author email.")

        if (package_content.get("AntiFeatures", "") == "" or
                package_content.get("AntiFeatures", "") == ["fdroid_repo"] or force):
            if ("github.com/" or "gitlab.com/") in website:
                anti_features = ["NonFreeAssets"]
            else:
                anti_features = ["UpstreamNonFree", "NonFreeAssets"]

            if re.search(r">Contains\sads<\/span>", resp_int) is not None:
                anti_features.append("Ads")

            if re.search(r">In-app\spurchases<\/span>", resp_int) is not None:
                anti_features.append("NonFreeDep")
                anti_features.append("NonFreeNet")
            package_content["AntiFeatures"] = anti_features

        if package_content.get("CurrentVersionCode", "") == "" or force or force_version:
            package_content["CurrentVersionCode"] = package_and_version[package][0]

        if package_content.get("CurrentVersion", "") == "" or force or force_version:
            package_content["CurrentVersion"] = package_and_version[package][1]

        try:
            stream = open(os.path.join(metadata_dir, package + ".yml"), "w", encoding="utf_8")
            yaml.dump(package_content, stream, Dumper=Dumper, allow_unicode=True, encoding="utf_8")
            stream.close()
        except PermissionError:
            print("Couldn't write YML file, permission denied")

        get_icon(resp_int, package, package_and_version[package][0], repo_dir, force)

        if dl_screenshots:
            get_screenshots(resp, repo_dir, force, lang, package)

        print("Finished processing " + package)

    print("\nEverything done! Don't forget to run:\nfdroid rewritemeta\nfdroid update")


def get_screenshots(resp: str, repo_dir: str, force: bool, lang: str, package: str):
    print("Downloading screenshots for " + package)
    screenshots_path = os.path.join(repo_dir, package, lang, "phoneScreenshots")

    try:
        os.makedirs(screenshots_path)
    except FileExistsError:
        pass
    except PermissionError:
        print("Error creating the directory where the screenshots should be saved. Permission denied")
        return  # TODO: Should I be making these kind of errors fatal and
        # terminate the application instead of breaking the functions?

    if not force and len(os.listdir(screenshots_path)) > 0:
        print("Screenshots for %s already exists, skipping..." % package)
        return

    img_url_list = re.findall(r"<div\sjscontroller=\"RQJprf\"\sclass=\"Atcj9b\"><img\ssrc=\"([^\"]+)=w[0-9]+-h[0-9]+\"",
                              resp)  # type: List[str]

    pad_amount = len(str(len(img_url_list)))

    i = 0

    for img_url in img_url_list:
        url = img_url + "=w9999"
        ss_path = os.path.join(screenshots_path, str(i).zfill(pad_amount) + ".png")
        try:
            urllib.request.urlretrieve(url, ss_path)
            i += 1
        except HTTPError:
            pass
        except PermissionError:
            print("Error downloading screenshots. Permission denied.")
            return

    print("Finished downloading screenshots for " + package)


def extract_icon_url(resp_int: str) -> str | None:
    try:
        icon_base_url = re.search(r"<div\sclass=\"l8YSdd\"><img\ssrc=\"(.+?=s)[0-9]", resp_int).group(1)
    except IndexError:
        return None
    except AttributeError:
        return None

    return icon_base_url


def extract_icon_url_alt(resp_int: str) -> str | None:
    try:
        icon_base_url_alt = re.search(r"<div\sclass=\"Mqg6jb\sMhrnjf\"><img\ssrc=\"(.+?=w)", resp_int).group(1)
    except IndexError:
        return None
    except AttributeError:
        return None

    return icon_base_url_alt


def get_icon(resp_int: str, package: str, version_code: int, repo_dir: str, force: bool):
    icon_base_url = extract_icon_url(resp_int)

    if icon_base_url is None:
        icon_base_url_alt = extract_icon_url_alt(resp_int)
        if icon_base_url_alt is None:
            print("Couldn't extract icon URL for " + package)
            return

    filename = package + "." + str(version_code) + ".png"

    icon_relations = {"icons"    : "48",
                      "icons-120": "36",
                      "icons-160": "48",
                      "icons-240": "72",
                      "icons-320": "96",
                      "icons-480": "144",
                      "icons-640": "192"}

    for dirname in icon_relations.keys():
        try:
            os.mkdir(os.path.join(repo_dir, dirname))
        except FileExistsError:
            pass
        except PermissionError:
            print("Can't create directory for \"" + dirname + "\", permission denied")
            return

    if icon_base_url is not None:
        for dirname in icon_relations.keys():
            icon_path = os.path.join(repo_dir, dirname, filename)
            if os.path.exists(icon_path) and not force:
                continue
            url = icon_base_url + icon_relations[dirname]
            urllib.request.urlretrieve(url, icon_path)
    elif icon_base_url_alt is not None:
        for dirname in icon_relations.keys():
            icon_path = os.path.join(repo_dir, dirname, filename)
            if os.path.exists(icon_path) and not force:
                continue
            url = icon_base_url_alt + icon_relations[dirname] + "-h" + icon_relations[dirname]  # type: str
            urllib.request.urlretrieve(url, icon_path)


def extract_categories(ret_grp: re.Match, resp_int: str):
    cat_list = []

    # Official categories from:
    # https://support.google.com/googleplay/android-developer/answer/9859673?hl=en

    game_categories = ["Action", "Adventure", "Arcade", "Board", "Card", "Casino", "Casual", "Educational", "Music",
                       "Puzzle", "Racing", "Role Playing", "Simulation", "Sports", "Strategy", "Trivia", "Word"]

    app_categories = {"Art and Design"           : "Graphics",
                      "Auto and Vehicles"        : "",
                      "Beauty"                   : "Sports & Health",
                      "Books and Reference"      : "Reading",
                      "Business"                 : "",
                      "Comics"                   : "Reading",
                      "Communications"           : "Internet",
                      "Dating"                   : "",
                      "Education"                : "Science & Education",
                      "Entertainment"            : "",
                      "Events"                   : "Time",
                      "Finance"                  : "Money",
                      "Food and Drink"           : "",
                      "Health and Fitness"       : "Sports & Health",
                      "House and Home"           : "",
                      "Libraries and Demo"       : "",
                      "Lifestyle"                : "Sports & Health",
                      "Maps and Navigation"      : "Navigation",
                      "Medical"                  : "Sports & Health",
                      "Music and Audio"          : "Multimedia",
                      "News and Magazines"       : "Reading",
                      "Parenting"                : "Security",
                      "Personalization"          : "Theming",
                      "Photography"              : "Graphics",
                      "Productivity"             : "Time",
                      "Shopping"                 : "",
                      "Social"                   : "",
                      "Sports"                   : "Sports & Health",
                      "Tools"                    : "System",
                      "Travel and Local"         : "",
                      "Video Players and Editors": "Multimedia",
                      "Weather"                  : "Internet"}

    for cat in ret_grp.groups():
        if html.unescape(cat.strip()) == "Sports":
            if resp_int.find("href=\"/store/apps/category/GAME_SPORTS\""):
                cat_list.append("Game - " + html.unescape(cat.strip()))
            elif app_categories[html.unescape(cat.strip())] != "":
                cat_list.append(app_categories[html.unescape(cat.strip())])
            else:
                cat_list.append(html.unescape(cat.strip()))
            continue

        if cat.strip() != "" and html.unescape(cat.strip()) in game_categories:
            cat_list.append("Game - " + html.unescape(cat.strip()))
            continue

        if cat.strip() != "" and html.unescape(cat.strip()) in app_categories.keys():
            if app_categories[html.unescape(cat.strip())] != "":
                cat_list.append(app_categories[html.unescape(cat.strip())])
            else:
                cat_list.append(html.unescape(cat.strip()))

    return cat_list


def sanitize_lang(lang: str):
    lang = lang.strip().lower()

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
