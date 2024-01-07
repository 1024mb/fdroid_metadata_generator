from __future__ import annotations

import argparse
import html
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
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
    parser.add_argument("-df", "--data-file",
                        help="Path to the JSON formatted data file. "
                             "Defaults to data.json located in the program directory.",
                        default=os.path.join(Path(__file__).resolve().parent, "data.json"))

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
        elif not os.path.exists(metadata_dir):
            print("Metadata directory path doesn't exist, aborting...")
            exit(1)

    if args.repo_dir is not None:
        repo_dir = os.path.abspath(args.repo_dir)
        if os.path.split(repo_dir)[1] != "repo":
            print("Repo directory path doesn't look like a F-Droid repository directory, aborting...")
            exit(1)
        elif not os.path.exists(repo_dir):
            print("Repo directory path doesn't exist, aborting...")
            exit(1)

    if not os.path.exists(os.path.abspath(args.data_file)) or not os.path.isfile(os.path.abspath(args.data_file)):
        print("Invalid data file.")
        exit(1)

    if shutil.which("aapt") is None:
        print("Please install aapt before running this program.")
        exit(1)

    if shutil.which("aapt2") is None:
        print("Please install aapt2 before running this program.")
        exit(1)

    data_file_stream = open(args.data_file, mode="r", encoding="utf_8")
    data_file_content = json.load(data_file_stream)  # type: Dict
    data_file_stream.close()

    if not check_data_file(data_file_content):
        exit(1)

    lang = sanitize_lang(args.language)

    if lang not in data_file_content["Locales"]:
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
    package_and_version = {}  # type: Dict[str: List[int | None, str | None]]

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
                    package_and_version[base_name] = None, None

        retrieve_info(package_list, package_and_version, lang, metadata_dir, repo_dir, args.force, args.force_version,
                      args.download_screenshots, data_file_content)
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
                      args.download_screenshots, data_file_content)
    else:
        print("We shouldn't have got here.")
        exit(1)


def check_data_file(data_file_content) -> bool:
    if data_file_content.get("Locales") is None or len(data_file_content.get("Locales")) == 0:
        print("ERROR: \"Locales\" key is missing or empty in the data file.\n")
        return False

    if data_file_content.get("Licenses") is None or len(data_file_content.get("Licenses")) == 0:
        print("ERROR: \"Licenses\" key is missing or empty in the data file.\n")
        return False

    if data_file_content.get("App_Categories") is None or len(data_file_content.get("App_Categories")) == 0:
        print("ERROR: \"App_Categories\" key is missing or empty in the data file.\n")
        return False

    if data_file_content.get("Game_Categories") is None or len(data_file_content.get("Game_Categories")) == 0:
        print("ERROR: \"Game_Categories\" key is missing or empty in the data file.\n")
        return False

    if data_file_content.get("Icon_Relations") is None or len(data_file_content.get("Icon_Relations")) == 0:
        print("ERROR: \"Icon_Relations\" key is missing or empty in the data file.\n")
        return False

    return True


def convert_apks(key_file: str, cert_file: str, password: List[str] | None, repo_dir: str,
                 build_tools_path: List[str] | None, apk_editor_path: str):
    print("Starting APKS conversion...\n")

    if platform.system() == "Windows":
        try:
            from win32_setctime import setctime
        except ImportError:
            setctime = None
            print("win32_setctime module is not installed,"
                  " creation times wont be restored for the converted APK files.\n")

    if build_tools_path is not None:
        apksigner_path = "\"" + os.path.join(build_tools_path[0], "apksigner") + "\""
    else:
        apksigner_path = "\"" + shutil.which("apksigner") + "\""

    if password is not None:
        sign_command = (apksigner_path + " sign --key \"" + key_file + "\" --cert \"" + cert_file +
                        "\" --key-pass pass:" + password[0] + " --in \"%s\" --out \"%s\"")
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
                    print("There was an error signing " + os.path.splitext(file)[0] + ".apk\nError: %s\n" % e)
                    continue
                except PermissionError:
                    print("Error deleting file " + os.path.join(repo_dir, file) + ". Permission denied\n")
                    continue
            except subprocess.CalledProcessError as e:
                print("There was an error converting " + file + " to .apk\nError: %s\n" % e)
                continue

    if proc:
        print("\nFinished converting all APKS files.\n")
    else:
        print("No APKS files were converted.\n")


def map_apk_to_packagename(repo_dir: str) -> Dict:
    mapped_apk_files = {}

    for apk_file in os.listdir(repo_dir):
        apk_file_path = os.path.join(repo_dir, apk_file)
        if os.path.isfile(apk_file_path) and os.path.splitext(apk_file_path)[1].lower() == ".apk":
            mapped_apk_files[ApkFile(apk_file_path).package_name] = apk_file

    return mapped_apk_files


def is_metadata_complete(package_content: Dict) -> bool:
    if (package_content.get("AuthorName") is None or package_content.get("WebSite") is None
            or package_content.get("Categories") is None or package_content.get("Name") is None
            or package_content.get("Summary") is None or package_content.get("Description") is None
            or package_content.get("AuthorEmail") is None or package_content.get("AntiFeatures") is None
            or package_content.get("CurrentVersionCode") is None or package_content.get("CurrentVersion") is None
            or package_content.get("License") is None):
        return False
    if (package_content.get("AuthorName", "") != "" and package_content.get("WebSite", "") != ""
            and package_content.get("Categories", "") != "" and package_content.get("Categories", "") != ["fdroid_repo"]
            and package_content.get("Name", "") != "" and package_content.get("Summary", "") != ""
            and package_content.get("Description", "") != "" and package_content.get("AuthorEmail", "") != ""
            and package_content.get("AntiFeatures", "") != "" and package_content.get("CurrentVersionCode", "") != ""
            and package_content.get("CurrentVersion", "") != "" and package_content.get("License", "") != ""
            and package_content.get("License", "") != "Unknown"):
        return True
    else:
        return False


def is_icon_complete(package: str, version_code: int | None, repo_dir: str, data_file_content: dict) -> bool:
    if version_code is None:
        return True

    filename = package + "." + str(version_code) + ".png"

    icon_relations = {}

    for key in data_file_content["Icon_Relations"].keys():
        icon_relations[key] = False

    for dirname in icon_relations.keys():
        icon_path = os.path.join(repo_dir, dirname, filename)
        if os.path.exists(icon_path):
            icon_relations[dirname] = True

    if all(icon_relations.values()):
        return True
    else:
        return False


def screenshot_exist(package: str, repo_dir: str) -> bool:
    screenshots_path = os.path.join(repo_dir, package, "en-US", "phoneScreenshots")

    if not os.path.exists(screenshots_path):
        return False
    elif len(os.listdir(screenshots_path)) > 0:
        return True
    else:
        return False


def retrieve_info(package_list: list, package_and_version: Dict[str: List[int | None, str | None]], lang: str,
                  metadata_dir: str,
                  repo_dir: str, force: bool, force_version: bool, dl_screenshots: bool, data_file_content: dict):
    playstore_url = "https://play.google.com/store/apps/details?id="

    proc = False

    for package in package_list:
        print("Processing " + package + "...\n")

        if os.path.exists(os.path.join(metadata_dir, package + ".yml")):
            try:
                stream = open(os.path.join(metadata_dir, package + ".yml"), "r", encoding="utf_8")
                package_content = yaml.load(stream, Loader=Loader)  # type:Dict
                stream.close()
            except PermissionError:
                print("WARNING: Couldn't read metadata file. Permission denied, skipping package...\n")
                continue
        else:
            package_content = {}

        if not force and not force_version:  # then check for available data
            if is_metadata_complete(package_content) and is_icon_complete(package, package_and_version[package][0],
                                                                          repo_dir, data_file_content):
                if package_and_version[package][0] is None:
                    if dl_screenshots:
                        if screenshot_exist(package, repo_dir):
                            print("Skipping processing for the package as all the metadata is complete in the YML file,"
                                  " and screenshots exist.\n")
                            continue
                    else:
                        print("Skipping processing for the package as all the metadata is complete in the YML file.\n")
                        continue
                else:
                    if dl_screenshots:
                        if screenshot_exist(package, repo_dir):
                            print("Skipping processing for the package as all the metadata is complete in the YML file,"
                                  " all the icons are available and screenshots exist.\n")
                            continue
                    else:
                        print("Skipping processing for the package as all the metadata is complete in the YML file"
                              " and all the icons are available.\n")
                        continue

        proc = True

        playstore_url_comp_int = playstore_url + package + "&hl=en-US"
        playstore_url_comp = playstore_url + package + "&hl=" + lang

        resp = ""
        resp_int = ""

        try:
            resp = urllib.request.urlopen(playstore_url_comp).read().decode()
        except HTTPError as e:
            if e.code == 404:
                print("%s was not found on the Play Store.\n" % package)
            continue

        if playstore_url_comp == playstore_url_comp_int:
            rep_int = resp
        else:
            try:
                resp_int = urllib.request.urlopen(playstore_url_comp_int).read().decode()
            except HTTPError as e:
                if e.code == 404:
                    print("%s was not found on the Play Store.\n" % package)
                continue

        if ">We're sorry, the requested URL was not found on this server.</div>" in resp_int:
            print("%s was not found on the Play Store.\n" % package)
            continue

        try:
            if package_content.get("AuthorName", "") == "" or package_content.get("AuthorName") is None or force:
                package_content["AuthorName"] = \
                    html.unescape(
                            re.search(r"div\sclass=\"Vbfug\sauoIOc\"><a\shref[^>]+><span>(.+?)<\/span>", resp).group(
                                    1)).strip()
        except (IndexError, AttributeError):
            print("WARNING: Couldn't get the Author name.\n")

        website = ""
        try:
            website = \
                re.search(r"<meta\sname=\"appstore:developer_url\"\scontent=\"([^\"]+)\"><meta", resp).group(1).strip()
        except (IndexError, AttributeError):
            print("WARNING: Couldn't get the app website.\n")

        if website != "" and (package_content.get("WebSite", "") == "" or package_content.get("WebSite") is None
                              or force):
            package_content["WebSite"] = website.replace("http://", "https://")

        if "https://github.com/" in website or "http://github.com/" in website:
            repo = re.sub(r"(https?)(://github.com/[^/]+/[^/]+).*", r"https\2", website)
            api_repo = re.sub(r"(https?)(://github.com/)([^/]+/[^/]+).*", r"https://api.github.com/repos/\3", website)

            get_license(package_content, force, api_repo, data_file_content)

            if (package_content.get("IssueTracker", "") == "" or package_content.get("IssueTracker") is None
                    or force):
                package_content["IssueTracker"] = repo + "/issues"

            if package_content.get("SourceCode", "") == "" or package_content.get("SourceCode") is None or force:
                package_content["SourceCode"] = repo

            if package_content.get("Changelog", "") == "" or package_content.get("Changelog") is None or force:
                package_content["Changelog"] = repo + "/releases/latest"

            if package_content.get("Repo", "") == "" or package_content.get("Repo") is None or force:
                package_content["Repo"] = repo

        elif "https://gitlab.com/" in website or "http://gitlab.com/" in website:
            repo = re.sub(r"(https?)(://gitlab.com/[^/]+/[^/]+).*", r"https\2", website)
            git_repo = urllib.request.urlopen(repo).read().decode()

            try:
                repo_id = re.search(
                        r"<span\sclass=\"gl-sr-only\"\sdata-testid=\"project-id-content\"\sitemprop=\"identifier\">\n*Project\sID:\s([0-9]+)\n*</span>",
                        git_repo).groups(1)
                api_repo = "https://gitlab.com/api/v4/projects/" + repo_id[0].strip() + "?license=yes"
                get_license(package_content, force, api_repo, data_file_content)
            except (IndexError, AttributeError):
                pass

            if (package_content.get("IssueTracker", "") == "" or package_content.get("IssueTracker") is None
                    or force):
                package_content["IssueTracker"] = repo + "/-/issues"

            if package_content.get("SourceCode", "") == "" or package_content.get("SourceCode") is None or force:
                package_content["SourceCode"] = repo

            if package_content.get("Changelog", "") == "" or package_content.get("Changelog") is None or force:
                package_content["Changelog"] = repo + "/-/releases"

            if package_content.get("Repo", "") == "" or package_content.get("Repo") is None or force:
                package_content["Repo"] = repo

        elif (package_content.get("License", "") == "" or package_content.get("License", "") == "Unknown"
              or package_content.get("License") is None or force):
            package_content["License"] = "Copyright"

        pattern = (r"<span\sjsname=\"V67aGc\"\sclass=\"VfPpkd-vQzf8d\"\saria-hidden=\"true\">(["
                   r"^<]+)<\/span><a\sclass=\"WpHeLc\sVfPpkd-mRLv6\sVfPpkd-RLmnJb\"\shref=\"\/store\/("
                   r"?:apps\/category|search\?)")

        if (package_content.get("Categories", "") == "" or
                package_content.get("Categories", "") == ["fdroid_repo"]
                or package_content.get("Categories") is None
                or None in package_content.get("Categories") or force):
            ret_grp = re.search(pattern, resp_int)

            if ret_grp is not None:
                cat_list = extract_categories(ret_grp, resp_int, data_file_content)
                package_content["Categories"] = cat_list
            else:
                print("WARNING: Couldn't get the categories.\n")

        if package_content.get("Name", "") == "" or package_content.get("Name") is None or force:
            try:
                package_content["Name"] = html.unescape(
                        re.search(r"itemprop=\"name\">(.+?)<\/h1>", resp).group(1)).strip()
            except (IndexError, AttributeError):
                print("WARNING: Couldn't get the application name.\n")

        if package_content.get("Summary", "") == "" or package_content.get("Summary") is None or force:
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
                print("WARNING: Couldn't get the summary.\n")

        if package_content.get("Description", "") == "" or package_content.get("Description") is None or force:
            try:
                package_content["Description"] = html.unescape(
                        re.search(r"<div\sclass=\"[^\"]+\"\sdata-g-id=\"description\">(.+?)<\/div>", resp).group(
                                1)).replace(
                        "<br>", "\n").strip()
            except (IndexError, AttributeError):
                print("WARNING: Couldn't get the description.\n")

        if package_content.get("AuthorEmail", "") == "" or package_content.get("AuthorEmail") is None or force:
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
                print("WARNING: Couldn't get the Author email.\n")

        if (package_content.get("AntiFeatures", "") == "" or package_content.get("AntiFeatures") is None
                or None in package_content.get("AntiFeatures") or force):
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

        if (package_content.get("CurrentVersionCode", "") == "" or package_content.get("CurrentVersionCode") is None
                or force or force_version):
            package_content["CurrentVersionCode"] = package_and_version[package][0]

        if (package_content.get("CurrentVersion", "") == "" or package_content.get("CurrentVersion") is None
                or force or force_version):
            package_content["CurrentVersion"] = package_and_version[package][1]

        try:
            stream = open(os.path.join(metadata_dir, package + ".yml"), "w", encoding="utf_8")
            yaml.dump(package_content, stream, Dumper=Dumper, allow_unicode=True, encoding="utf_8")
            stream.close()
        except PermissionError:
            print("Couldn't write YML file. Permission denied.\n")
            continue

        if force or not is_icon_complete(package, package_and_version[package][0], repo_dir, data_file_content):
            get_icon(resp_int, package, package_and_version[package][0], repo_dir, force, data_file_content)

        if dl_screenshots and (not screenshot_exist(package, repo_dir) or force):
            get_screenshots(resp, repo_dir, force, package)

        print("Finished processing %s.\n" % package)

    if proc:
        print("\nEverything done! Don't forget to run:\nfdroid rewritemeta\nfdroid update")
    else:
        print("\nNothing was processed, no files changed.")


def get_license(package_content: dict, force: bool, api_repo: str, data_file_content: dict):
    if (package_content.get("License", "") == "" or package_content.get("License", "") == "Unknown"
            or package_content.get("License") is None or force):
        try:
            api_load = urllib.request.urlopen(api_repo).read().decode()
        except HTTPError:
            print("Couldn't download the api response.\n")
            return

        try:
            resp_api = json.loads(api_load)  # type: dict
        except json.JSONDecodeError:
            print("Couldn't load the api response.\n")
            return

        if resp_api["license"] is not None:
            package_content["License"] = normalize_license(data_file_content, resp_api["license"]["key"])
        else:
            package_content["License"] = "No License"


def normalize_license(data_file_content: dict, license_key: str) -> str:
    license_dict = {}
    for key in data_file_content["Licenses"]:
        license_dict[key.lower().strip()] = key

    if license_key.lower().strip() in license_dict.keys():
        return license_dict[license_key.lower().strip()]
    elif license_key.lower().strip() + "-only" in license_dict.keys():
        return license_dict[license_key.lower().strip() + "-only"]
    else:
        return "Other"


def get_screenshots(resp: str, repo_dir: str, force: bool, package: str):
    # Locale directory must be en-US and not the real locale because that's what F-Droid
    # defaults to and this program does not do multi-lang download.
    screenshots_path = os.path.join(repo_dir, package, "en-US", "phoneScreenshots")

    try:
        os.makedirs(screenshots_path)
    except FileExistsError:
        pass
    except PermissionError:
        print("Error creating the directory where the screenshots should be saved. Permission denied.\n")
        return  # TODO: Should I be making these kind of errors fatal and
        # terminate the application instead of breaking the functions?

    if not force and len(os.listdir(screenshots_path)) > 0:
        print("Screenshots for %s already exists, skipping...\n" % package)
        return

    print("Downloading screenshots for %s\n" % package)

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
            print("Error downloading screenshots. Permission denied.\n")
            return

    print("Finished downloading screenshots for %s.\n" % package)


def extract_icon_url(resp_int: str) -> str | None:
    try:
        icon_base_url = re.search(r"<div\sclass=\"l8YSdd\"><img\ssrc=\"(.+?=s)[0-9]", resp_int).group(1)
    except (IndexError, AttributeError):
        return None

    return icon_base_url


def extract_icon_url_alt(resp_int: str) -> str | None:
    try:
        icon_base_url_alt = re.search(r"<div\sclass=\"Mqg6jb\sMhrnjf\"><img\ssrc=\"(.+?=w)", resp_int).group(1)
    except (IndexError, AttributeError):
        return None

    return icon_base_url_alt


def get_icon(resp_int: str, package: str, version_code: int | None, repo_dir: str, force: bool,
             data_file_content: dict):
    if version_code is None:
        # if a metadata_dir is specified and the corresponding APK file doesn't exist in the repo dir then we can't get the
        # VersionCode needed to store the icons hence return
        print("WARNING: The corresponding APK file doesn't exist in the repo directory, "
              "version code can't be retrieved and icons wont be downloaded.\n")
        return

    icon_base_url = extract_icon_url(resp_int)

    if icon_base_url is None:
        icon_base_url_alt = extract_icon_url_alt(resp_int)
        if icon_base_url_alt is None:
            print("Couldn't extract icon URL for %s.\n" % package)
            return

    filename = package + "." + str(version_code) + ".png"

    for dirname in data_file_content["Icon_Relations"].keys():
        try:
            os.makedirs(os.path.join(repo_dir, dirname))
        except FileExistsError:
            pass
        except PermissionError:
            print("Can't create directory for \"" + dirname +
                  "\". Permission denied, skipping icon download for this package.\n")
            return

    if icon_base_url is not None:
        for dirname in data_file_content["Icon_Relations"].keys():
            icon_path = os.path.join(repo_dir, dirname, filename)
            if os.path.exists(icon_path) and not force:
                continue
            url = icon_base_url + data_file_content["Icon_Relations"][dirname]
            urllib.request.urlretrieve(url, icon_path)
    elif icon_base_url_alt is not None:
        for dirname in data_file_content["Icon_Relations"].keys():
            icon_path = os.path.join(repo_dir, dirname, filename)
            if os.path.exists(icon_path) and not force:
                continue
            url = (icon_base_url_alt + data_file_content["Icon_Relations"][dirname] + "-h" +
                   data_file_content["Icon_Relations"][dirname])  # type: str
            urllib.request.urlretrieve(url, icon_path)


def extract_categories(ret_grp: re.Match, resp_int: str, data_file_content: dict):
    cat_list = []

    for cat in ret_grp.groups():
        if html.unescape(cat.strip()) == "Sports":
            if resp_int.find("href=\"/store/apps/category/GAME_SPORTS\""):
                cat_list.append(data_file_content["Game_Categories"][html.unescape(cat.strip())])
            elif data_file_content["App_Categories"][html.unescape(cat.strip())] != "":
                cat_list.append(data_file_content["App_Categories"][html.unescape(cat.strip())])
            else:
                cat_list.append(html.unescape(cat.strip()))
            continue

        if cat.strip() != "" and html.unescape(cat.strip()) in data_file_content["Game_Categories"].keys():
            cat_list.append(data_file_content["Game_Categories"][html.unescape(cat.strip())])
            continue

        if cat.strip() != "" and html.unescape(cat.strip()) in data_file_content["App_Categories"].keys():
            if data_file_content["App_Categories"][html.unescape(cat.strip())] != "":
                cat_list.append(data_file_content["App_Categories"][html.unescape(cat.strip())])
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
