#!/usr/bin/env python3

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
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.error import HTTPError

import yaml
from colorist import green, yellow, red, blue, cyan
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
    parser.add_argument("-f", "--force-metadata",
                        help="Force overwrite existing metadata.",
                        action="store_true")
    parser.add_argument("-fv", "--force-version",
                        help="Force updating version name and code even if they are already specified in the YML file.",
                        action="store_true")
    parser.add_argument("-fs", "--force-screenshots",
                        help="Force overwrite existing screenshots.",
                        action="store_true")
    parser.add_argument("-fi", "--force-icons",
                        help="Force overwrite existing icons.",
                        action="store_true")
    parser.add_argument("-fa", "--force-all",
                        help="Force overwrite existing metadata, screenshots and icons.",
                        action="store_true")
    parser.add_argument("-ca", "--convert-apks",
                        help="Convert APKS files to APK and sign them.",
                        action="store_true")
    parser.add_argument("-kf", "--key-file",
                        help="Key file used to sign the APK, required if --convert-apks is used.",
                        nargs=1)
    parser.add_argument("-cf", "--cert-file",
                        help="Cert file used to sign the APK, required if --convert-apks is used.",
                        nargs=1)
    parser.add_argument("-cpw", "--certificate-password",
                        help="Password to sign the APK.",
                        nargs=1)
    parser.add_argument("-btp", "--build-tools-path",
                        help="Path to Android SDK buildtools binaries.",
                        nargs=1)
    parser.add_argument("-aep", "--apk-editor-path",
                        help="Path to the ApkEditor.jar file.",
                        nargs=1)
    parser.add_argument("-dls", "--download-screenshots",
                        help="Download screenshots which will be stored in the repo directory.",
                        action="store_true")
    parser.add_argument("-df", "--data-file",
                        help="Path to the JSON formatted data file. "
                             "Defaults to data.json located in the program directory.",
                        default=os.path.join(Path(__file__).resolve().parent, "data.json"))
    parser.add_argument("-rf", "--replacement-file",
                        help="JSON formatted file containing a dict with replacements for the package name of all found"
                             " apps.")

    args = parser.parse_args()

    if args.metadata_dir is None and args.repo_dir is None:
        red("ERROR: Please provide either the metadata directory or the repository directory.")
        exit(1)

    if args.metadata_dir is not None and args.repo_dir is not None:
        red("ERROR: Please provide only the metadata directory or the repository directory. Not both.")
        exit(1)

    if args.metadata_dir is not None and len(args.metadata_dir) == 0:
        red("ERROR: Metadata directory path cannot be empty.")
        exit(1)

    if args.repo_dir is not None and len(args.repo_dir) == 0:
        red("ERROR: Repo directory path cannot be empty.")
        exit(1)

    if args.metadata_dir is not None:
        metadata_dir = os.path.abspath(args.metadata_dir)
        if os.path.split(metadata_dir)[1] != "metadata":
            red("ERROR: Metadata directory path doesn't look like a F-Droid repository metadata directory, aborting...")
            exit(1)
        elif not os.path.exists(metadata_dir):
            red("ERROR: Metadata directory path doesn't exist, aborting...")
            exit(1)

    if args.repo_dir is not None:
        repo_dir = os.path.abspath(args.repo_dir)
        if os.path.split(repo_dir)[1] != "repo":
            red("ERROR: Repo directory path doesn't look like a F-Droid repository directory, aborting...")
            exit(1)
        elif not os.path.exists(repo_dir):
            red("ERROR: Repo directory path doesn't exist, aborting...")
            exit(1)

    if not os.path.exists(os.path.abspath(args.data_file)) or not os.path.isfile(os.path.abspath(args.data_file)):
        red("ERROR: Invalid data file.")
        exit(1)

    if shutil.which("aapt") is None:
        red("ERROR: Please install aapt before running this program.")
        exit(1)

    if shutil.which("aapt2") is None:
        red("ERROR: Please install aapt2 before running this program.")
        exit(1)

    if args.replacement_file is not None:
        if (not os.path.exists(os.path.abspath(args.replacement_file)) or
                not os.path.isfile(os.path.abspath(args.replacement_file))):
            red("ERROR: Invalid replace file.")
            exit(1)

    try:
        data_file_stream = open(args.data_file, mode="r", encoding="utf_8")
    except FileNotFoundError:
        red("ERROR: Data file not found.")
        exit(1)
    except PermissionError:
        red("ERROR: Couldn't read data file. Permission denied.")
        exit(1)

    try:
        data_file_content = json.load(data_file_stream)  # type: Dict
    except json.decoder.JSONDecodeError:
        red("ERROR: Error decoding data file.")
        exit(1)

    data_file_stream.close()

    if not check_data_file(data_file_content=data_file_content):
        exit(1)

    lang = sanitize_lang(lang=args.language)

    if lang not in data_file_content["Locales"]:
        red("ERROR: Invalid language.")
        exit(1)

    if args.convert_apks:
        if args.build_tools_path is None and shutil.which("apksigner") is None:
            red("ERROR: Please install the build-tools package of the Android SDK if you want to convert APKS files.")
            exit(1)

        if args.build_tools_path is not None:
            build_tools_path = os.path.abspath(args.build_tools_path[0])
            if (not os.path.exists(build_tools_path) or not os.path.isdir(build_tools_path)
                    or not (os.path.exists(os.path.join(build_tools_path, "apksigner"))
                            or os.path.exists(os.path.join(build_tools_path, "apksigner.bat")))):
                red("ERROR: Invalid build-tools path.")
                exit(1)

        if shutil.which("java") is None:
            red("ERROR: Please install java if you want to convert APKS files.")
            exit(1)

        if args.apk_editor_path is None:
            red("ERROR: Please specify the full path of the ApkEditor.jar file.")
            exit(1)
        elif (not os.path.exists(os.path.abspath(args.apk_editor_path[0])) or
              not os.path.isfile(os.path.abspath(args.apk_editor_path[0]))):
            red("ERROR: Invalid ApkEditor.jar path.")
            exit(1)

    if args.key_file is not None and (not os.path.exists(os.path.abspath(args.key_file[0])) or not os.path.isfile(
            os.path.abspath(args.key_file[0]))):
        red("ERROR: Invalid key file path.")
        exit(1)

    if args.cert_file is not None and (not os.path.exists(os.path.abspath(args.cert_file[0])) or not os.path.isfile(
            os.path.abspath(args.cert_file[0]))):
        red("ERROR: Invalid cert file path.")
        exit(1)

    if args.key_file is None or args.cert_file is None:
        red("ERROR: Please provide the key and certificate files for APKS conversion.\n")
        exit(1)

    package_list = {}
    package_and_version = {}

    force_metadata = args.force_metadata
    force_version = args.force_version
    force_screenshots = args.force_screenshots
    force_icons = args.force_icons

    if args.force_all:
        force_metadata = True
        force_screenshots = True
        force_icons = True

    if "metadata_dir" in locals():
        if not os.path.isdir(metadata_dir):
            red("ERROR: Invalid metadata directory, supplied path is not a directory")
            exit(1)

        repo_dir = os.path.join(os.path.split(metadata_dir)[0], "repo")

        if args.convert_apks:
            convert_apks(key_file=args.key_file[0], cert_file=args.cert_file[0], password=args.certificate_password,
                         repo_dir=repo_dir, build_tools_path=args.build_tools_path,
                         apk_editor_path=args.apk_editor_path[0])

        mapped_apk_files = map_apk_to_packagename(repo_dir=repo_dir)

        for item in os.listdir(metadata_dir):
            base_name = os.path.splitext(item)[0]
            try:
                apk_file_path = os.path.join(repo_dir, mapped_apk_files[base_name])
            except KeyError:
                apk_file_path = None

            if os.path.splitext(item)[1].lower() != ".yml":
                yellow("WARNING: Skipping %s.\n" % item)
            else:
                new_base_name = get_new_packagename(replacement_file=args.replacement_file, base_name=base_name)

                if new_base_name is not None:
                    package_list[base_name] = new_base_name
                else:
                    package_list[base_name] = base_name

                if apk_file_path is not None and os.path.exists(apk_file_path) and os.path.isfile(apk_file_path):
                    if new_base_name is not None:
                        package_and_version[new_base_name] = (int(ApkFile(apk_file_path).version_code),
                                                              str(ApkFile(apk_file_path).version_name))
                    else:
                        package_and_version[base_name] = (int(ApkFile(apk_file_path).version_code),
                                                          str(ApkFile(apk_file_path).version_name))
                else:
                    if new_base_name is not None:
                        package_and_version[new_base_name] = (0, "0")
                    else:
                        package_and_version[base_name] = (0, "0")

        retrieve_info(package_list=package_list, package_and_version=package_and_version, lang=lang,
                      metadata_dir=metadata_dir, repo_dir=repo_dir, force_metadata=force_metadata,
                      force_version=force_version, force_screenshots=force_screenshots, force_icons=force_icons,
                      dl_screenshots=args.download_screenshots, data_file_content=data_file_content)
    elif "repo_dir" in locals():
        if not os.path.isdir(repo_dir):
            red("ERROR: Invalid repo directory, supplied path is not a directory")
            exit(1)

        if args.convert_apks:
            convert_apks(key_file=args.key_file[0], cert_file=args.cert_file[0], password=args.certificate_password,
                         repo_dir=repo_dir, build_tools_path=args.build_tools_path,
                         apk_editor_path=args.apk_editor_path[0])

        metadata_dir = os.path.join(os.path.split(repo_dir)[0], "metadata")

        green("Getting package names, version names and version codes...\n")

        for apk_file in os.listdir(repo_dir):
            apk_file_path = os.path.join(repo_dir, apk_file)

            if os.path.isfile(os.path.join(repo_dir, apk_file)) and os.path.splitext(apk_file)[1].lower() == ".apk":
                base_name = ApkFile(apk_file_path).package_name
                new_base_name = get_new_packagename(replacement_file=args.replacement_file, base_name=base_name)

                if new_base_name is not None:
                    package_list[base_name] = new_base_name
                    package_and_version[new_base_name] = (int(ApkFile(apk_file_path).version_code),
                                                          str(ApkFile(apk_file_path).version_name))
                else:
                    package_list[base_name] = base_name
                    package_and_version[base_name] = (int(ApkFile(apk_file_path).version_code),
                                                      str(ApkFile(apk_file_path).version_name))

        green("Finished getting package names, version names and version.\n")

        retrieve_info(package_list=package_list, package_and_version=package_and_version, lang=lang,
                      metadata_dir=metadata_dir, repo_dir=repo_dir, force_metadata=force_metadata,
                      force_version=force_version, force_screenshots=force_screenshots, force_icons=force_icons,
                      dl_screenshots=args.download_screenshots, data_file_content=data_file_content)
    else:
        red("ERROR: We shouldn't have got here.")
        exit(1)


def get_new_packagename(replacement_file: str | None, base_name: str) -> str | None:
    if replacement_file is not None:
        try:
            replace_stream = open(os.path.abspath(replacement_file), encoding="utf_8", mode="r")
        except UnicodeDecodeError as e:
            print("ERROR: Decode error.\n%s\n" % e)
            return None
        except PermissionError as e:
            print("ERROR: Couldn't open replacement file. Permission denied.\n%s\n" % e)
            return None

        try:
            replacements = json.load(replace_stream)["Replacements"]  # type: Dict[str: str]
        except PermissionError as e:
            red("ERROR: Couldn't read replacement file. Permission denied.\n%s\n" % e)
            exit(1)
        except json.decoder.JSONDecodeError as e:
            red("ERROR: Couldn't load replacement file. Decoding error.\n%s\n" % e)
            exit(1)

        for term in replacements.keys():
            search_term = term
            replace_term = replacements[term]

            if search_term in base_name:
                base_name = base_name.replace(search_term, replace_term)
                break
        return base_name
    else:
        return None


def check_data_file(data_file_content) -> bool:
    if data_file_content.get("Locales") is None or len(data_file_content.get("Locales")) == 0:
        red("ERROR: \"Locales\" key is missing or empty in the data file.\n")
        return False

    if data_file_content.get("Licenses") is None or len(data_file_content.get("Licenses")) == 0:
        red("ERROR: \"Licenses\" key is missing or empty in the data file.\n")
        return False

    if data_file_content.get("App_Categories") is None or len(data_file_content.get("App_Categories")) == 0:
        red("ERROR: \"App_Categories\" key is missing or empty in the data file.\n")
        return False

    if data_file_content.get("Game_Categories") is None or len(data_file_content.get("Game_Categories")) == 0:
        red("ERROR: \"Game_Categories\" key is missing or empty in the data file.\n")
        return False

    if data_file_content.get("Icon_Relations") is None or len(data_file_content.get("Icon_Relations")) == 0:
        red("ERROR: \"Icon_Relations\" key is missing or empty in the data file.\n")
        return False

    return True


def convert_apks(key_file: str, cert_file: str, password: List[str] | None, repo_dir: str,
                 build_tools_path: List[str] | None, apk_editor_path: str):
    green("Starting APKS conversion...\n")

    if platform.system() == "Windows":
        try:
            from win32_setctime import setctime
        except ImportError:
            setctime = None
            yellow("\tWARNING: win32_setctime module is not installed,"
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
        if os.path.splitext(file)[1].lower() != ".apks":
            continue

        apks_path = os.path.join(repo_dir, file)
        apk_path_unsigned = os.path.join(repo_dir, os.path.splitext(file)[0] + "_unsigned.apk")
        apk_path_signed = os.path.join(repo_dir, os.path.splitext(file)[0] + ".apk")
        old_app_stats = None

        try:
            old_app_stats = os.lstat(apks_path)
        except FileNotFoundError:
            yellow("\tWARNING: %s does not exist.\n" % apks_path)
        except PermissionError:
            yellow("\tWARNING: Couldn't get stats of the APKS file,"
                   " check permissions. Old timestamps wont be restored.\n")

        try:
            subprocess.run(convert_command % (apks_path, apk_path_unsigned), stdout=subprocess.DEVNULL,
                           stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            red("\tERROR: There was an error converting " + file + " to .apk\nError: %s\n" % e)
            if os.path.exists(apk_path_unsigned):
                try:
                    os.remove(apk_path_unsigned)
                except PermissionError:
                    red("\t\tERROR: Couldn't remove unfinished APK file. Permission denied.\n")
            continue

        try:
            subprocess.run(sign_command % (apk_path_unsigned, apk_path_signed), stdout=subprocess.DEVNULL,
                           stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            yellow("\tWARNING: There was an error signing " + os.path.splitext(file)[0] + ".apk")
            red("\tError: %s\n" % e)
            continue

        if old_app_stats is not None:
            try:
                os.utime(apk_path_signed, (old_app_stats.st_atime, old_app_stats.st_mtime))
            except PermissionError:
                yellow("\tWARNING: Couldn't restore old timestamps. Permission denied.\n")

            if platform.system() == "Windows" and "win32_setctime" in sys.modules:
                try:
                    setctime(apk_path_signed, old_app_stats.st_birthtime)
                except PermissionError:
                    yellow("\tWARNING: Couldn't restore old creation date. Permission denied.\n")

        proc = True

        try:
            os.remove(apks_path)
        except PermissionError:
            yellow("\tWARNING: Error deleting file " + apks_path + ". Permission denied\n")
            continue

        try:
            os.remove(apk_path_unsigned)
        except PermissionError:
            yellow("\tWARNING: Error deleting file " + apk_path_unsigned + ". Permission denied\n")
            continue

    if proc:
        green("\nFinished converting all APKS files.\n")
    else:
        green("No APKS files were converted.\n")


def map_apk_to_packagename(repo_dir: str) -> Dict:
    mapped_apk_files = {}

    for apk_file in os.listdir(repo_dir):
        apk_file_path = os.path.join(repo_dir, apk_file)
        if os.path.isfile(apk_file_path) and os.path.splitext(apk_file_path)[1].lower() == ".apk":
            mapped_apk_files[ApkFile(apk_file_path).package_name] = apk_file

    return mapped_apk_files


def get_version(package_content: Dict, package_and_version: Dict,
                new_package: str, force_metadata: bool, force_version: bool) -> None:
    if (package_content.get("CurrentVersionCode", "") == "" or package_content.get("CurrentVersionCode", "") == 0
            or package_content.get("CurrentVersionCode", "") == 2147483647
            or package_content.get("CurrentVersionCode") is None or force_metadata or force_version):
        if package_and_version[new_package][0] is not None:
            package_content["CurrentVersionCode"] = int(package_and_version[new_package][0])
        else:
            package_content["CurrentVersionCode"] = 0

    if (package_content.get("CurrentVersion", "") == "" or package_content.get("CurrentVersion", "") == "0"
            or package_content.get("CurrentVersion") is None or force_metadata or force_version):
        if package_and_version[new_package][1] is not None:
            package_content["CurrentVersion"] = str(package_and_version[new_package][1])
        else:
            package_content["CurrentVersion"] = "0"


def retrieve_info(package_list: Dict[str, str], package_and_version: Dict[str, Tuple[int, str]], lang: str,
                  metadata_dir: str, repo_dir: str, force_metadata: bool, force_version: bool, force_screenshots: bool,
                  force_icons: bool, dl_screenshots: bool, data_file_content: dict):
    playstore_url = "https://play.google.com/store/apps/details?id="

    proc = False

    not_found_packages = []
    authorname_not_found_packages = []
    authoremail_not_found_packages = []
    name_not_found_packages = []
    website_not_found_packages = []
    summary_not_found_packages = []
    description_not_found_packages = []
    category_not_found_packages = []
    icon_not_found_packages = []
    screenshots_not_found_packages = []

    for pkg in package_list.keys():
        package = pkg
        new_package = package_list[pkg]

        green("Processing " + package + "...\n")

        if os.path.exists(os.path.join(metadata_dir, package + ".yml")):
            try:
                stream = open(os.path.join(metadata_dir, package + ".yml"), "r", encoding="utf_8")
                package_content = yaml.load(stream, Loader=Loader)  # type:Dict
                stream.close()

                if package_content is None:
                    package_content = {}
            except PermissionError:
                yellow("\tWARNING: Couldn't read metadata file. Permission denied, skipping package...\n")
                continue
        else:
            package_content = {}

        metadata_exist = None
        icons_exist = None
        screenshots_exist = None

        # If none of the force arguments is declared then check for available metadata, if screenshots
        # should be downloaded then check if they exist, otherwise check only for the rest of the data
        if dl_screenshots:
            if not force_metadata and not force_version and not force_screenshots and not force_icons:
                metadata_exist = is_metadata_complete(package_content=package_content)
                icons_exist = is_icon_complete(package=package, version_code=package_and_version[new_package][0],
                                               repo_dir=repo_dir, data_file_content=data_file_content)
                screenshots_exist = screenshot_exist(package=package, repo_dir=repo_dir)

                if metadata_exist and icons_exist and screenshots_exist:
                    if package_and_version[new_package][0] is None:
                        blue("\tSkipping processing for the package as all the metadata is complete in the YML file,"
                             " and screenshots exist.\n")
                        continue
                    else:
                        blue("\tSkipping processing for the package as all the metadata is complete in the YML file,"
                             " all the icons are available and screenshots exist.\n")
                        continue
        elif not force_metadata and not force_version and not force_icons:
            metadata_exist = is_metadata_complete(package_content=package_content)
            icons_exist = is_icon_complete(package=package, version_code=package_and_version[new_package][0],
                                           repo_dir=repo_dir, data_file_content=data_file_content)

            if metadata_exist and icons_exist:
                if package_and_version[new_package][0] is None:
                    blue("\tSkipping processing for the package as all the metadata is complete in the YML file.\n")
                    continue
                else:
                    blue("\tSkipping processing for the package as all the metadata is complete in the YML file"
                         " and all the icons are available.\n")
                    continue

        proc = True

        playstore_url_comp_int = playstore_url + new_package + "&hl=en-US"
        playstore_url_comp = playstore_url + new_package + "&hl=" + lang

        resp_list = []

        green("\tDownloading Play Store pages...\n")

        if not get_play_store_page(playstore_url_comp=playstore_url_comp, playstore_url_comp_int=playstore_url_comp_int,
                                   package=package, new_package=new_package, resp_list=resp_list,
                                   not_found_packages=not_found_packages, package_content=package_content,
                                   force_metadata=force_metadata, force_version=force_version,
                                   package_and_version=package_and_version,
                                   metadata_dir=metadata_dir):
            continue

        resp = resp_list[0]
        resp_int = resp_list[1]

        green("\tExtracting information...\n")

        if not force_metadata:
            if metadata_exist is None:
                metadata_exist = is_metadata_complete(package_content=package_content)
            if not metadata_exist:
                get_metadata(package_content=package_content, resp=resp, resp_int=resp_int, package=package,
                             name_not_found_packages=name_not_found_packages,
                             authorname_not_found_packages=authorname_not_found_packages,
                             authoremail_not_found_packages=authoremail_not_found_packages,
                             website_not_found_packages=website_not_found_packages,
                             category_not_found_packages=category_not_found_packages,
                             summary_not_found_packages=summary_not_found_packages,
                             description_not_found_packages=description_not_found_packages,
                             force_metadata=force_metadata,
                             data_file_content=data_file_content)
        else:
            get_metadata(package_content=package_content, resp=resp, resp_int=resp_int, package=package,
                         name_not_found_packages=name_not_found_packages,
                         authorname_not_found_packages=authorname_not_found_packages,
                         authoremail_not_found_packages=authoremail_not_found_packages,
                         website_not_found_packages=website_not_found_packages,
                         category_not_found_packages=category_not_found_packages,
                         summary_not_found_packages=summary_not_found_packages,
                         description_not_found_packages=description_not_found_packages,
                         force_metadata=force_metadata,
                         data_file_content=data_file_content)

        get_version(package_content, package_and_version, new_package, force_metadata, force_version)

        green("\tFinished information extraction for %s.\n" % package)

        if not write_yml(metadata_dir, package, package_content):
            continue

        if not force_icons and icons_exist is None:
            icons_exist = is_icon_complete(package=package, version_code=package_and_version[new_package][0],
                                           repo_dir=repo_dir, data_file_content=data_file_content)

        if force_icons or not icons_exist:
            green("\tDownloading icons...\n")
            # Function to download icons need to check force_icons because there might be cases where one of the icons
            # is missing, with screenshots as long as there is at least one file we assume it's complete.
            get_icon(resp_int, package, new_package, package_and_version[new_package][0], repo_dir, force_icons,
                     data_file_content, icon_not_found_packages)
            green("\tFinished downloading icons for %s.\n" % package)
        else:
            blue("\tAll icon files for %s already exist, skipping...\n" % package)

        if dl_screenshots:
            if not force_screenshots and screenshots_exist is None:
                screenshots_exist = screenshot_exist(package=package, repo_dir=repo_dir)

            if force_screenshots or not screenshots_exist:
                get_screenshots(resp, repo_dir, package, new_package,
                                screenshots_not_found_packages, data_file_content, screenshots_exist)
            else:
                blue("\tScreenshots for %s already exists, skipping...\n" % package)

        green("Finished processing %s.\n" % package)

    if proc:
        green("Everything done! Don't forget to run:")
        cyan("\nfdroid rewritemeta\nfdroid update")
    else:
        green("Nothing was processed, no files changed.")

    if len(not_found_packages) != 0:
        yellow("\nThese packages weren't found on the Play Store:\n")
        for item in not_found_packages:
            yellow(item)
        write_not_found_log(not_found_packages, "NotFound_Package")

    if len(authorname_not_found_packages) != 0:
        yellow("\nThe AuthorName for these packages wasn't found on the Play Store:\n")
        for item in authorname_not_found_packages:
            yellow(item)
        write_not_found_log(authorname_not_found_packages, "NotFound_AuthorName")

    if len(authoremail_not_found_packages) != 0:
        yellow("\nThe AuthorName for these packages wasn't found on the Play Store:\n")
        for item in authoremail_not_found_packages:
            yellow(item)
        write_not_found_log(authoremail_not_found_packages, "NotFound_AuthorEmail")

    if len(website_not_found_packages) != 0:
        yellow("\nThe Website for these packages wasn't found on the Play Store:\n")
        for item in website_not_found_packages:
            yellow(item)
        write_not_found_log(website_not_found_packages, "NotFound_Website")

    if len(summary_not_found_packages) != 0:
        yellow("\nThe Summary for these packages wasn't found on the Play Store:\n")
        for item in summary_not_found_packages:
            yellow(item)
        write_not_found_log(summary_not_found_packages, "NotFound_Summary")

    if len(description_not_found_packages) != 0:
        yellow("\nThe Description for these packages wasn't found on the Play Store:\n")
        for item in description_not_found_packages:
            yellow(item)
        write_not_found_log(description_not_found_packages, "NotFound_Description")

    if len(category_not_found_packages) != 0:
        yellow("\nThe Category for these packages wasn't found on the Play Store:\n")
        for item in category_not_found_packages:
            yellow(item)
        write_not_found_log(category_not_found_packages, "NotFound_Category")

    if len(name_not_found_packages) != 0:
        yellow("\nThe Name for these packages wasn't found on the Play Store:\n")
        for item in name_not_found_packages:
            yellow(item)
        write_not_found_log(name_not_found_packages, "NotFound_Name")

    if len(icon_not_found_packages) != 0:
        yellow("\nThe icon URL for these packages wasn't found on the Play Store:\n")
        for item in icon_not_found_packages:
            yellow(item)
        write_not_found_log(icon_not_found_packages, "NotFound_IconURL")

    if len(screenshots_not_found_packages) != 0:
        yellow("\nThe screenshots URL for these packages weren't found on the Play Store:\n")
        for item in screenshots_not_found_packages:
            yellow(item)
        write_not_found_log(screenshots_not_found_packages, "NotFound_ScreenshotsURL")


def get_metadata(package_content: dict, resp: str, resp_int: str, package: str, name_not_found_packages: list,
                 authorname_not_found_packages: list, authoremail_not_found_packages: list,
                 website_not_found_packages: list, category_not_found_packages: list, summary_not_found_packages: list,
                 description_not_found_packages: list, force_metadata: bool, data_file_content: dict) -> None:
    author_name_pattern = data_file_content["Regex_Patterns"]["author_name_pattern"]
    author_email_pattern = data_file_content["Regex_Patterns"]["author_email_pattern"]
    name_pattern = data_file_content["Regex_Patterns"]["name_pattern"]
    website_pattern = data_file_content["Regex_Patterns"]["website_pattern"]
    category_pattern = data_file_content["Regex_Patterns"]["category_pattern"]
    summary_pattern = data_file_content["Regex_Patterns"]["summary_pattern"]
    summary_pattern_alt = data_file_content["Regex_Patterns"]["summary_pattern_alt"]
    description_pattern = data_file_content["Regex_Patterns"]["description_pattern"]
    gitlab_repo_id_pattern = data_file_content["Regex_Patterns"]["gitlab_repo_id_pattern"]

    get_name(package_content, name_pattern, resp, package, name_not_found_packages, force_metadata)

    get_author_name(package_content, author_name_pattern, resp, package, authorname_not_found_packages,
                    force_metadata)

    get_author_email(package_content, author_email_pattern, resp, package, authoremail_not_found_packages,
                     force_metadata)

    website = get_website(package_content, website_pattern, resp, package, website_not_found_packages,
                          force_metadata)

    get_repo_info_and_license(package_content, gitlab_repo_id_pattern, website, data_file_content, force_metadata)

    get_categories(package_content, category_pattern, resp_int, package, category_not_found_packages,
                   data_file_content, force_metadata)

    if package_content.get("Summary", "") == "" or package_content.get("Summary") is None or force_metadata:
        if not get_summary(resp, package_content, summary_pattern):
            if not get_summary(resp, package_content, summary_pattern_alt):
                yellow("\tWARNING: Couldn't get the summary.\n")
                summary_not_found_packages.append(package)

    get_description(package_content, description_pattern, resp, package, description_not_found_packages,
                    force_metadata)

    get_anti_features(package_content, website, resp_int, force_metadata)


def get_anti_features(package_content: dict, website: str, resp_int: str, force_metadata: bool) -> None:
    if (package_content.get("AntiFeatures", "") == "" or package_content.get("AntiFeatures") is None
            or None in package_content.get("AntiFeatures") or force_metadata):
        if ("github.com/" or "gitlab.com/") in website:
            anti_features = ["NonFreeAssets"]
        else:
            anti_features = ["UpstreamNonFree", "NonFreeAssets"]

        if re.search(r">Contains\sads</span>", resp_int) is not None:
            anti_features.append("Ads")

        if resp_int.find("<div>This app may share these data types with third parties<div") or resp_int.find(
                "<div>This app may collect these data types<div"):
            anti_features.append("Tracking")

        if re.search(r">In-app\spurchases</span>", resp_int) is not None:
            anti_features.append("NonFreeDep")
            anti_features.append("NonFreeNet")

        package_content["AntiFeatures"] = anti_features


def get_author_email(package_content: dict, author_email_pattern: str, resp: str, package: str,
                     authoremail_not_found_packages: list, force_metadata: bool) -> None:
    if package_content.get("AuthorEmail", "") == "" or package_content.get("AuthorEmail") is None or force_metadata:
        try:
            email_grps = re.findall(author_email_pattern, resp)

            for item in email_grps:
                if "@" not in item:
                    continue
                else:
                    package_content["AuthorEmail"] = item
                    break
        except (IndexError, AttributeError):
            yellow("\tWARNING: Couldn't get the Author email.\n")
            authoremail_not_found_packages.append(package)


def get_description(package_content: dict, description_pattern: str, resp: str, package: str,
                    description_not_found_packages: list, force_metadata: bool) -> None:
    if package_content.get("Description", "") == "" or package_content.get("Description") is None or force_metadata:
        try:
            package_content["Description"] = html.unescape(
                    re.search(description_pattern, resp).group(1)).replace("<br>", "\n").strip()
        except (IndexError, AttributeError):
            yellow("\tWARNING: Couldn't get the description.\n")
            description_not_found_packages.append(package)


def get_name(package_content: dict, name_pattern: str, resp: str, package: str,
             name_not_found_packages: list, force_metadata: bool) -> None:
    if package_content.get("Name", "") == "" or package_content.get("Name") is None or force_metadata:
        try:
            package_content["Name"] = html.unescape(re.search(name_pattern, resp).group(1)).strip()
        except (IndexError, AttributeError):
            yellow("\tWARNING: Couldn't get the application name.\n")
            name_not_found_packages.append(package)


def get_categories(package_content: dict, category_pattern: str, resp_int: str, package: str,
                   category_not_found_packages: list, data_file_content: dict, force_metadata: bool) -> None:
    if (package_content.get("Categories", "") == "" or
            package_content.get("Categories", "") == ["fdroid_repo"] or
            package_content.get("Categories") is None or
            None in package_content.get("Categories") or force_metadata):
        ret_grp = re.search(category_pattern, resp_int)

        if ret_grp is not None:
            cat_list = extract_categories(ret_grp, resp_int, data_file_content)
            package_content["Categories"] = cat_list
        else:
            yellow("\tWARNING: Couldn't get the categories.\n")
            category_not_found_packages.append(package)


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


def get_repo_info_and_license(package_content: dict, gitlab_repo_id_pattern: str, website: str,
                              data_file_content: dict, force_metadata: bool) -> None:
    if "https://github.com/" in website or "http://github.com/" in website:
        repo = re.sub(r"(https?)(://github.com/[^/]+/[^/]+).*", r"https\2", website)
        api_repo = re.sub(r"(https?)(://github.com/)([^/]+/[^/]+).*",
                          r"https://api.github.com/repos/\3", website)

        get_license(package_content, force_metadata, api_repo, data_file_content)

        if (package_content.get("IssueTracker", "") == "" or package_content.get("IssueTracker") is None
                or force_metadata):
            package_content["IssueTracker"] = repo + "/issues"

        if package_content.get("SourceCode", "") == "" or package_content.get("SourceCode") is None or force_metadata:
            package_content["SourceCode"] = repo

        if package_content.get("Changelog", "") == "" or package_content.get("Changelog") is None or force_metadata:
            package_content["Changelog"] = repo + "/releases/latest"

        if package_content.get("Repo", "") == "" or package_content.get("Repo") is None or force_metadata:
            package_content["Repo"] = repo
    elif "https://gitlab.com/" in website or "http://gitlab.com/" in website:
        repo = re.sub(r"(https?)(://gitlab.com/[^/]+/[^/]+).*", r"https\2", website)
        git_repo = urllib.request.urlopen(repo).read().decode()

        try:
            repo_id = re.search(gitlab_repo_id_pattern, git_repo).groups(1)
            api_repo = "https://gitlab.com/api/v4/projects/" + repo_id[0].strip() + "?license=yes"
            get_license(package_content, force_metadata, api_repo, data_file_content)
        except (IndexError, AttributeError):
            pass

        if (package_content.get("IssueTracker", "") == "" or package_content.get("IssueTracker") is None
                or force_metadata):
            package_content["IssueTracker"] = repo + "/-/issues"

        if package_content.get("SourceCode", "") == "" or package_content.get("SourceCode") is None or force_metadata:
            package_content["SourceCode"] = repo

        if package_content.get("Changelog", "") == "" or package_content.get("Changelog") is None or force_metadata:
            package_content["Changelog"] = repo + "/-/releases"

        if package_content.get("Repo", "") == "" or package_content.get("Repo") is None or force_metadata:
            package_content["Repo"] = repo
    elif (package_content.get("License", "") == "" or package_content.get("License", "") == "Unknown"
          or package_content.get("License") is None or force_metadata):
        package_content["License"] = "Copyright"


def get_website(package_content: dict, website_pattern: str, resp: str, package: str, website_not_found_packages: list,
                force_metadata: bool) -> str:
    website = ""

    try:
        website = (re.search(website_pattern, resp).group(1).strip())
    except (IndexError, AttributeError):
        yellow("\tWARNING: Couldn't get the app website.\n")
        website_not_found_packages.append(package)

    if website != "" and (package_content.get("WebSite", "") == "" or package_content.get("WebSite") is None
                          or force_metadata):
        package_content["WebSite"] = website.replace("http://", "https://")

    return website


def get_author_name(package_content: dict, author_name_pattern: str, resp: str, package: str,
                    authorname_not_found_packages: list, force_metadata: bool) -> None:
    try:
        if package_content.get("AuthorName", "") == "" or package_content.get("AuthorName") is None or force_metadata:
            package_content["AuthorName"] = html.unescape(re.search(author_name_pattern, resp).group(1)).strip()
    except (IndexError, AttributeError):
        yellow("\tWARNING: Couldn't get the Author name.\n")
        authorname_not_found_packages.append(package)


def get_play_store_page(playstore_url_comp: str, playstore_url_comp_int: str, package: str, new_package: str,
                        resp_list: list, not_found_packages: list, package_content: dict, force_metadata: bool,
                        force_version: bool, package_and_version: dict, metadata_dir: str) -> bool:
    try:
        resp_list.append(urllib.request.urlopen(playstore_url_comp).read().decode())
    except HTTPError as e:
        if e.code == 404:
            yellow("\t%s was not found on the Play Store.\n" % new_package)

            not_found_packages.append(package)

            get_version(package_content, package_and_version, new_package, force_metadata, force_version)
            write_yml(metadata_dir, package, package_content)

            green("Finished processing %s.\n" % package)
        return False

    if playstore_url_comp == playstore_url_comp_int:
        resp_list.append(resp_list[0])
    else:
        try:
            resp_list.append(urllib.request.urlopen(playstore_url_comp_int).read().decode())
        except HTTPError as e:
            if e.code == 404:
                yellow("\t%s was not found on the Play Store (en-US).\n" % new_package)

                not_found_packages.append(package)

                get_version(package_content, package_and_version, new_package, force_metadata, force_version)
                write_yml(metadata_dir, package, package_content)

                green("Finished processing %s.\n" % package)
            return False

    if ">We're sorry, the requested URL was not found on this server.</div>" in resp_list[1]:
        yellow("\t%s was not found on the Play Store.\n" % new_package)
        not_found_packages.append(package)

        get_version(package_content, package_and_version, new_package, force_metadata, force_version)
        write_yml(metadata_dir, package, package_content)

        green("Finished processing %s.\n" % package)
        return False

    return True


def get_summary(resp: str, package_content: dict, pattern: str) -> bool:
    try:
        summary = html.unescape(re.search(pattern, resp).group(1)).strip()
        summary = re.sub(r"(<[^>]+>)", "", summary)

        while len(summary) > 80:
            try:
                summary = re.search(r"(^.+\.)\s+.+$", summary).group(1)
            except (IndexError, AttributeError):
                summary = re.search(r"^(.+)\s\S+\s*$", summary[:77]).group(1) + "..."

        package_content["Summary"] = summary
        return True
    except (IndexError, AttributeError):
        return False


def get_license(package_content: dict, force_metadata: bool, api_repo: str, data_file_content: dict):
    if (package_content.get("License", "") == "" or package_content.get("License", "") == "Unknown"
            or package_content.get("License") is None or force_metadata):
        try:
            api_load = urllib.request.urlopen(api_repo).read().decode()
        except HTTPError:
            yellow("\tCouldn't download the api response for the license.\n")
            return

        try:
            resp_api = json.loads(api_load)  # type: dict
        except json.JSONDecodeError:
            yellow("\tCouldn't load the api response for the license.\n")
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


def get_screenshots(resp: str, repo_dir: str, package: str, new_package: str,
                    screenshots_not_found_packages: list, data_file_content: dict, screenshots_exist: bool) -> None:
    # Locale directory must be en-US and not the real locale because that's what F-Droid
    # defaults to and this program does not do multi-lang download.
    screenshots_path = os.path.join(repo_dir, package, "en-US", "phoneScreenshots")
    backup_path = os.path.join(repo_dir, "backup", package, "en-US", "phoneScreenshots")

    green("\tDownloading screenshots for %s\n" % package)

    screenshot_pattern = data_file_content["Regex_Patterns"]["screenshot_pattern"]

    img_url_list = re.findall(screenshot_pattern, resp)  # type: List[str]

    if len(img_url_list) == 0:
        yellow("\tCouldn't get screenshots URLs for %s\n" % new_package)
        screenshots_not_found_packages.append(package)
        return

    if screenshots_exist:
        try:
            shutil.rmtree(backup_path)
        except FileNotFoundError:
            pass
        except PermissionError as e:
            red("\tCouldn't remove the old backup directory. Permission denied.\n\t%s\n" % e)
            return

        try:
            os.makedirs(backup_path)
        except PermissionError as e:
            red("\tCouldn't create backup directory for screenshots. Permission denied.\n\t%s\n" % e)
            return

        try:
            os.rename(screenshots_path, backup_path)
        except FileNotFoundError:
            pass
        except PermissionError:
            red("\tCouldn't move the screenshots to the backup directory. Permission denied.\n")
            return

    try:
        os.makedirs(screenshots_path)
    except FileExistsError:
        pass
    except PermissionError:
        red("\tError creating the directory where the screenshots should be saved. Permission denied.\n")
        return

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
            red("\tError downloading screenshots. Permission denied.\n")
            return

    green("\tFinished downloading screenshots for %s.\n" % package)


def extract_icon_url(resp_int: str, icon_pattern: str) -> str | None:
    try:
        icon_base_url = re.search(icon_pattern, resp_int).group(1)
    except (IndexError, AttributeError):
        return None

    return icon_base_url


def extract_icon_url_alt(resp_int: str, icon_pattern_alt: str) -> str | None:
    try:
        icon_base_url_alt = re.search(icon_pattern_alt, resp_int).group(1)
    except (IndexError, AttributeError):
        return None

    return icon_base_url_alt


def get_icon(resp_int: str, package: str, new_package: str, version_code: int | None, repo_dir: str, force_icons: bool,
             data_file_content: dict, icon_not_found_packages: list):
    if version_code is None:
        # if a metadata_dir is specified and the corresponding APK file doesn't exist in the repo dir then we can't
        # get the VersionCode needed to store the icons hence return
        # TODO: Also check for 0 values?
        yellow("\tWARNING: The corresponding APK file doesn't exist in the repo directory, "
               "version code can't be retrieved and icons wont be downloaded.\n")
        return

    icon_pattern = data_file_content["Regex_Patterns"]["icon_pattern"]
    icon_pattern_alt = data_file_content["Regex_Patterns"]["icon_pattern_alt"]

    icon_base_url = extract_icon_url(resp_int, icon_pattern)

    if icon_base_url is None:
        icon_base_url_alt = extract_icon_url_alt(resp_int, icon_pattern_alt)
        if icon_base_url_alt is None:
            yellow("\tCouldn't extract icon URL for %s.\n" % new_package)
            icon_not_found_packages.append(package)
            return

    filename = package + "." + str(version_code) + ".png"

    for dirname in data_file_content["Icon_Relations"].keys():
        try:
            os.makedirs(os.path.join(repo_dir, dirname))
        except FileExistsError:
            pass
        except PermissionError:
            red("\tERROR: Can't create directory for \"" + dirname +
                "\". Permission denied, skipping icon download for this package.\n")
            icon_not_found_packages.append(package)
            return

    if icon_base_url is not None:
        for dirname in data_file_content["Icon_Relations"].keys():
            icon_path = os.path.join(repo_dir, dirname, filename)

            if os.path.exists(icon_path) and not force_icons:
                continue

            url = icon_base_url + data_file_content["Icon_Relations"][dirname]

            try:
                urllib.request.urlretrieve(url, icon_path)
            except urllib.error.HTTPError:
                yellow("\tCouldn't download icon for %s." % dirname)
            except PermissionError:
                yellow("\tCouldn't write icon file for %s. Permission denied." % dirname)
    elif icon_base_url_alt is not None:
        for dirname in data_file_content["Icon_Relations"].keys():
            icon_path = os.path.join(repo_dir, dirname, filename)

            if os.path.exists(icon_path) and not force_icons:
                continue

            url = (icon_base_url_alt + data_file_content["Icon_Relations"][dirname] + "-h" +
                   data_file_content["Icon_Relations"][dirname])  # type: str

            try:
                urllib.request.urlretrieve(url, icon_path)
            except urllib.error.HTTPError:
                yellow("\tCouldn't download icon for %s." % dirname)
            except PermissionError:
                yellow("\tCouldn't write icon file for %s. Permission denied." % dirname)


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


def is_metadata_complete(package_content: Dict) -> bool:
    if (package_content.get("AuthorName") is None
            or package_content.get("WebSite") is None
            or package_content.get("Categories") is None
            or package_content.get("Name") is None
            or package_content.get("Summary") is None
            or package_content.get("Description") is None
            or package_content.get("AuthorEmail") is None
            or package_content.get("AntiFeatures") is None
            or package_content.get("CurrentVersionCode") is None
            or package_content.get("CurrentVersion") is None
            or package_content.get("License") is None):
        return False

    if (package_content.get("AuthorName", "") != ""
            and package_content.get("WebSite", "") != ""
            and package_content.get("Categories", "") != ""
            and package_content.get("Categories", "") != ["fdroid_repo"]
            and package_content.get("Name", "") != ""
            and package_content.get("Summary", "") != ""
            and package_content.get("Description", "") != ""
            and package_content.get("AuthorEmail", "") != ""
            and package_content.get("AntiFeatures", "") != ""
            and package_content.get("CurrentVersionCode", "") != ""
            and package_content.get("CurrentVersionCode", "") != 0
            and package_content.get("CurrentVersionCode", "") != 2147483647
            and package_content.get("CurrentVersion", "") != ""
            and package_content.get("CurrentVersion", "") != "0"
            and package_content.get("License", "") != ""
            and package_content.get("License", "") != "Unknown"):
        return True
    else:
        return False


def is_icon_complete(package: str, version_code: int | None, repo_dir: str, data_file_content: dict) -> bool:
    if version_code is None:  # The correct filename can't be set so check for this value in parent function.
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


def write_yml(metadata_dir: str, package: str, package_content: Dict) -> bool:
    try:
        stream = open(os.path.join(metadata_dir, package + ".yml"), "w", encoding="utf_8")
        yaml.dump(package_content, stream, Dumper=Dumper, allow_unicode=True, encoding="utf_8")
        stream.close()
        return True
    except PermissionError:
        red("\tERROR: Couldn't write YML file for %s. Permission denied.\n" % package)
        return False


def write_not_found_log(items: list, file_name: str) -> None:
    today_date = datetime.today().strftime("%Y%m%d_%H%M%S")
    file_name = os.path.join(Path(__file__).resolve().parent, file_name + "_" + today_date + ".log")

    try:
        log_stream = open(file_name, "w")
    except IOError as e:
        red(e)
        return

    for item in items:
        try:
            log_stream.write(item + "\n")
        except IOError as e:
            red(e)
            return


if __name__ == "__main__":
    main()
