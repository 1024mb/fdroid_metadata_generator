#!/usr/bin/env python3

from __future__ import annotations

import argparse
import copy
import html
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from sys import exit
from typing import Dict, List, Tuple, Optional
from urllib.error import HTTPError

import requests
import ruamel.yaml
from PIL import Image
from colorama import Fore, init

from dep.apkfile_fork import ApkFile


def main():
    parser = argparse.ArgumentParser(description="Parser for PlayStore information to F-Droid YML metadata files.")
    parser.add_argument("-m", "--metadata-dir",
                        help="Directory where F-Droid metadata files are stored.",
                        nargs=1)
    parser.add_argument("-r", "--repo-dir",
                        help="Directory where F-Droid repo files are stored.",
                        nargs=1)
    parser.add_argument("-u", "--unsigned-dir",
                        help="Directory where unsigned app files are stored.",
                        nargs=1)
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
                             "Default: data.json located in the program directory.",
                        default=[os.path.join(Path(__file__).resolve().parent, "data.json")],
                        nargs=1)
    parser.add_argument("-rf", "--replacement-file",
                        help="JSON formatted file containing a dict with replacements for the package name of all found"
                             " apps.",
                        nargs=1)
    parser.add_argument("-lp", "--log-path",
                        help="Path to the directory where to store the log files. Default: Program directory.",
                        default=[str(Path(__file__).resolve().parent)],
                        nargs=1)
    parser.add_argument("--cookie-path",
                        help="Path to a Netscape cookie file.",
                        nargs=1)
    parser.add_argument("--use-eng-name",
                        help="Use the English app name instead of the localized one.",
                        action="store_true")

    args = parser.parse_args()

    init(autoreset=True)

    if args.metadata_dir is None and args.repo_dir is None and args.unsigned_dir is None:
        print(Fore.RED + "ERROR: Please provide at least the metadata directory, "
                         "the repository directory or the unsigned directory.")
        exit(1)

    if args.metadata_dir is not None and args.repo_dir is not None and args.unsigned_dir is not None:
        print(Fore.RED + "ERROR: Please provide only the metadata, "
                         "the repository or the unsigned directory. Not all of them.")
        exit(1)

    if ((args.metadata_dir is not None and args.repo_dir is not None)
            or (args.repo_dir is not None and args.unsigned_dir is not None)
            or (args.metadata_dir is not None and args.unsigned_dir is not None)):
        print(Fore.RED + "ERROR: Please provide only one of the directories.")
        exit(1)

    if args.metadata_dir is not None and len(args.metadata_dir) == 0:
        print(Fore.RED + "ERROR: Metadata directory path cannot be empty.")
        exit(1)

    if args.repo_dir is not None and len(args.repo_dir) == 0:
        print(Fore.RED + "ERROR: Repo directory path cannot be empty.")
        exit(1)

    if args.unsigned_dir is not None and len(args.unsigned_dir) == 0:
        print(Fore.RED + "ERROR: Unsigned directory path cannot be empty.")
        exit(1)

    if args.metadata_dir is not None:
        metadata_dir = os.path.abspath(args.metadata_dir[0])
        if os.path.split(metadata_dir)[1] != "metadata":
            print(Fore.RED + "ERROR: Metadata directory path doesn't look like a "
                             "F-Droid repository metadata directory, aborting...")
            exit(1)
        elif not os.path.exists(metadata_dir):
            print(Fore.RED + "ERROR: Metadata directory path doesn't exist, aborting...")
            exit(1)
        elif not os.path.isdir(metadata_dir):
            print(Fore.RED + "ERROR: Invalid metadata directory, supplied path is not a directory")
            exit(1)

    if args.repo_dir is not None:
        repo_dir = os.path.abspath(args.repo_dir[0])
        if os.path.split(repo_dir)[1] != "repo":
            print(Fore.RED + "ERROR: Repo directory path doesn't look like a F-Droid repository directory, aborting...")
            exit(1)
        elif not os.path.exists(repo_dir):
            print(Fore.RED + "ERROR: Repo directory path doesn't exist, aborting...")
            exit(1)
        elif not os.path.isdir(repo_dir):
            print(Fore.RED + "ERROR: Invalid repo directory, supplied path is not a directory")
            exit(1)

    if args.unsigned_dir is not None:
        unsigned_dir = os.path.abspath(args.unsigned_dir[0])
        if os.path.split(unsigned_dir)[1] != "unsigned":
            print(Fore.RED + "ERROR: Unsigned directory path doesn't look like a F-Droid unsigned directory, "
                             "aborting...")
            exit(1)
        elif not os.path.exists(unsigned_dir):
            print(Fore.RED + "ERROR: Unsigned directory path doesn't exist, aborting...")
            exit(1)
        if not os.path.isdir(unsigned_dir):
            print(Fore.RED + "ERROR: Invalid unsigned directory, supplied path is not a directory")
            exit(1)

    if not os.path.exists(os.path.abspath(args.data_file[0])) or not os.path.isfile(os.path.abspath(args.data_file[0])):
        print(Fore.RED + "ERROR: Invalid data file.")
        exit(1)

    if args.build_tools_path is None:
        if shutil.which("aapt") is None:
            print(Fore.RED + "ERROR: Please install aapt before running this program.")
            exit(1)

        if shutil.which("aapt2") is None:
            print(Fore.RED + "ERROR: Please install aapt2 before running this program.")
            exit(1)

    if args.replacement_file is not None:
        if (not os.path.exists(os.path.abspath(args.replacement_file[0])) or
                not os.path.isfile(os.path.abspath(args.replacement_file[0]))):
            print(Fore.RED + "ERROR: Invalid replacement file.")
            exit(1)

    replacement_file = args.replacement_file[0]

    try:
        data_file_stream = open(args.data_file[0], mode="r", encoding="utf_8")
    except FileNotFoundError:
        print(Fore.RED + "ERROR: Data file not found.")
        exit(1)
    except PermissionError:
        print(Fore.RED + "ERROR: Couldn't read data file. Permission denied.")
        exit(1)

    try:
        data_file_content = json.load(data_file_stream)  # type: Dict
    except json.decoder.JSONDecodeError:
        print(Fore.RED + "ERROR: Error decoding data file.")
        exit(1)

    data_file_stream.close()

    if not check_data_file(data_file_content=data_file_content):
        exit(1)

    lang = sanitize_lang(lang=args.language)

    if lang not in data_file_content["Locales"]["Play_Store"]:
        print(Fore.RED + "ERROR: Invalid language.")
        exit(1)

    if args.cookie_path is None:
        print(Fore.YELLOW + "WARNING: Cookie file not specified, Amazon scraping wont work.\n")
    else:
        if not os.path.isfile(args.cookie_path[0]):
            print(Fore.RED + "ERROR: Specified cookie path is not a file.")
            exit(1)

    if args.convert_apks:
        if args.build_tools_path is None and shutil.which("apksigner") is None:
            print(Fore.RED + "ERROR: Please install the build-tools package of "
                             "the Android SDK if you want to convert APKS files.")
            exit(1)

        if args.build_tools_path is not None:
            build_tools_path = os.path.abspath(args.build_tools_path[0])
            if (not os.path.exists(build_tools_path) or not os.path.isdir(build_tools_path)
                    or not (os.path.exists(os.path.join(build_tools_path, "apksigner"))
                            or os.path.exists(os.path.join(build_tools_path, "apksigner.bat")))):
                print(Fore.RED + "ERROR: Invalid build-tools path.")
                exit(1)

        if shutil.which("java") is None:
            print(Fore.RED + "ERROR: Please install java if you want to convert APKS files.")
            exit(1)

        if args.apk_editor_path is None:
            print(Fore.RED + "ERROR: Please specify the full path of the ApkEditor.jar file.")
            exit(1)
        elif (not os.path.exists(os.path.abspath(args.apk_editor_path[0])) or
              not os.path.isfile(os.path.abspath(args.apk_editor_path[0]))):
            print(Fore.RED + "ERROR: Invalid ApkEditor.jar path.")
            exit(1)

        if args.key_file is not None and (not os.path.exists(os.path.abspath(args.key_file[0])) or not os.path.isfile(
                os.path.abspath(args.key_file[0]))):
            print(Fore.RED + "ERROR: Invalid key file path.")
            exit(1)

        if args.cert_file is not None and (not os.path.exists(os.path.abspath(args.cert_file[0])) or not os.path.isfile(
                os.path.abspath(args.cert_file[0]))):
            print(Fore.RED + "ERROR: Invalid cert file path.")
            exit(1)

        if args.key_file is None or args.cert_file is None:
            print(Fore.RED + "ERROR: Please provide the key and certificate files for APKS conversion.\n")
            exit(1)

    log_path = args.log_path[0]

    if os.path.exists(log_path) and not os.path.isdir(log_path):
        print(Fore.RED + "Invalid log path.")
        exit(1)

    if not os.path.exists(log_path):
        os.makedirs(log_path)

    package_list = {}
    package_and_version = {}

    force_metadata = args.force_metadata  # type: bool
    force_version = args.force_version  # type: bool
    force_screenshots = args.force_screenshots  # type: bool
    force_icons = args.force_icons  # type: bool
    cookie_path = args.cookie_path
    use_eng_name = args.use_eng_name  # type: bool

    if args.force_all:
        force_metadata = True
        force_screenshots = True
        force_icons = True

    if "metadata_dir" in locals():
        repo_dir = os.path.join(os.path.split(metadata_dir)[0], "repo")
        os.makedirs(repo_dir, exist_ok=True)

        if args.convert_apks:
            convert_apks(key_file=args.key_file[0],
                         cert_file=args.cert_file[0],
                         password=args.certificate_password,
                         apks_dir=repo_dir,
                         build_tools_path=args.build_tools_path,
                         apk_editor_path=args.apk_editor_path[0])

        mapped_apk_files = map_apk_to_packagename(repo_dir=repo_dir)

        for item in os.listdir(metadata_dir):
            base_name = os.path.splitext(item)[0]
            try:
                apk_file_path = os.path.join(repo_dir, mapped_apk_files[base_name])
            except KeyError:
                apk_file_path = None

            if os.path.splitext(item)[1].lower() != ".yml":
                print(Fore.YELLOW + "WARNING: Skipping %s.\n" % item)
            else:
                new_base_name = get_new_packagename(replacement_file=replacement_file,
                                                    base_name=base_name)

                if new_base_name is not None:
                    package_list[base_name] = new_base_name
                else:
                    package_list[base_name] = base_name

                if apk_file_path is not None and os.path.exists(apk_file_path) and os.path.isfile(apk_file_path):
                    apk_info = ApkFile(apk_file_path)
                    if new_base_name is not None:
                        package_and_version[new_base_name] = (int(apk_info.version_code),
                                                              str(apk_info.version_name))
                    else:
                        package_and_version[base_name] = (int(apk_info.version_code),
                                                          str(apk_info.version_name))
                else:
                    if new_base_name is not None:
                        package_and_version[new_base_name] = (0, "0")
                    else:
                        package_and_version[base_name] = (0, "0")

        retrieve_info(package_list=package_list,
                      package_and_version=package_and_version,
                      lang=lang,
                      metadata_dir=metadata_dir,
                      repo_dir=repo_dir,
                      force_metadata=force_metadata,
                      force_version=force_version,
                      force_screenshots=force_screenshots,
                      force_icons=force_icons,
                      dl_screenshots=args.download_screenshots,
                      data_file_content=data_file_content,
                      log_path=log_path,
                      cookie_path=cookie_path,
                      use_eng_name=use_eng_name)
    elif "repo_dir" in locals():
        if args.convert_apks:
            convert_apks(key_file=args.key_file[0],
                         cert_file=args.cert_file[0],
                         password=args.certificate_password,
                         apks_dir=repo_dir,
                         build_tools_path=args.build_tools_path,
                         apk_editor_path=args.apk_editor_path[0])

        metadata_dir = os.path.join(os.path.split(repo_dir)[0], "metadata")
        os.makedirs(metadata_dir, exist_ok=True)

        print(Fore.GREEN + "Getting package names, version names and version codes...\n")

        for apk_file in os.listdir(repo_dir):
            apk_file_path = os.path.join(repo_dir, apk_file)

            if os.path.isfile(apk_file_path) and os.path.splitext(apk_file)[1].lower() == ".apk":
                apk_info = ApkFile(apk_file_path)
                base_name = apk_info.package_name
                new_base_name = get_new_packagename(replacement_file=replacement_file,
                                                    base_name=base_name)

                if new_base_name is not None:
                    package_list[base_name] = new_base_name
                    package_and_version[new_base_name] = (int(apk_info.version_code),
                                                          str(apk_info.version_name))
                else:
                    package_list[base_name] = base_name
                    package_and_version[base_name] = (int(apk_info.version_code),
                                                      str(apk_info.version_name))

        print(Fore.GREEN + "Finished getting package names, version names and version.\n")

        retrieve_info(package_list=package_list,
                      package_and_version=package_and_version,
                      lang=lang,
                      metadata_dir=metadata_dir,
                      repo_dir=repo_dir,
                      force_metadata=force_metadata,
                      force_version=force_version,
                      force_screenshots=force_screenshots,
                      force_icons=force_icons,
                      dl_screenshots=args.download_screenshots,
                      data_file_content=data_file_content,
                      log_path=log_path,
                      cookie_path=cookie_path,
                      use_eng_name=use_eng_name)
    elif "unsigned_dir" in locals():
        metadata_dir = os.path.join(os.path.split(unsigned_dir)[0], "metadata")
        repo_dir = os.path.join(os.path.split(unsigned_dir)[0], "repo")
        os.makedirs(metadata_dir, exist_ok=True)
        os.makedirs(repo_dir, exist_ok=True)

        if args.convert_apks:
            convert_apks(key_file=args.key_file[0],
                         cert_file=args.cert_file[0],
                         password=args.certificate_password,
                         apks_dir=unsigned_dir,
                         build_tools_path=args.build_tools_path,
                         apk_editor_path=args.apk_editor_path[0])

        print(Fore.GREEN + "Getting package names, version names and version codes...\n")

        for apk_file in os.listdir(unsigned_dir):
            apk_file_path = os.path.join(unsigned_dir, apk_file)

            if os.path.isfile(apk_file_path) and os.path.splitext(apk_file)[1].lower() == ".apk":
                apk_info = ApkFile(apk_file_path)
                base_name = apk_info.package_name
                new_base_name = get_new_packagename(replacement_file=replacement_file,
                                                    base_name=base_name)

                if new_base_name is not None:
                    package_list[base_name] = new_base_name
                    package_and_version[new_base_name] = (int(apk_info.version_code),
                                                          str(apk_info.version_name))
                else:
                    package_list[base_name] = base_name
                    package_and_version[base_name] = (int(apk_info.version_code),
                                                      str(apk_info.version_name))

        print(Fore.GREEN + "Finished getting package names, version names and version.\n")

        retrieve_info(package_list=package_list,
                      package_and_version=package_and_version,
                      lang=lang,
                      metadata_dir=metadata_dir,
                      repo_dir=repo_dir,
                      force_metadata=force_metadata,
                      force_version=force_version,
                      force_screenshots=force_screenshots,
                      force_icons=force_icons,
                      dl_screenshots=args.download_screenshots,
                      data_file_content=data_file_content,
                      log_path=log_path,
                      cookie_path=cookie_path,
                      use_eng_name=use_eng_name)
    else:
        print(Fore.RED + "ERROR: We shouldn't have got here.")
        exit(1)


def get_new_packagename(replacement_file: str | None,
                        base_name: str) -> str | None:
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
            print(Fore.RED + "ERROR: Couldn't read replacement file. Permission denied.\n%s\n" % e)
            exit(1)
        except json.decoder.JSONDecodeError as e:
            print(Fore.RED + "ERROR: Couldn't load replacement file. Decoding error.\n%s\n" % e)
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
        print(Fore.RED + "ERROR: \"Locales\" key is missing or empty in the data file.\n")
        return False

    if data_file_content.get("Licenses") is None or len(data_file_content.get("Licenses")) == 0:
        print(Fore.RED + "ERROR: \"Licenses\" key is missing or empty in the data file.\n")
        return False

    if data_file_content.get("App_Categories") is None or len(data_file_content.get("App_Categories")) == 0:
        print(Fore.RED + "ERROR: \"App_Categories\" key is missing or empty in the data file.\n")
        return False

    if data_file_content.get("Game_Categories") is None or len(data_file_content.get("Game_Categories")) == 0:
        print(Fore.RED + "ERROR: \"Game_Categories\" key is missing or empty in the data file.\n")
        return False

    if data_file_content.get("Icon_Relations") is None or len(data_file_content.get("Icon_Relations")) == 0:
        print(Fore.RED + "ERROR: \"Icon_Relations\" key is missing or empty in the data file.\n")
        return False

    if data_file_content.get("Regex_Patterns") is None or len(data_file_content.get("Regex_Patterns")) == 0:
        print(Fore.RED + "ERROR: \"Regex_Patterns\" key is missing or empty in the data file.\n")
        return False

    if (data_file_content.get("Sport_Category_Pattern") is None
            or len(data_file_content.get("Sport_Category_Pattern")) == 0):
        print(Fore.RED + "ERROR: \"Sport_Category_Pattern\" key is missing or empty in the data file.\n")
        return False

    return True


def convert_apks(key_file: str,
                 cert_file: str,
                 password: List[str] | None,
                 apks_dir: str,
                 build_tools_path: List[str] | None,
                 apk_editor_path: str):
    print(Fore.GREEN + "Starting APKS conversion...\n")

    if platform.system() == "Windows":
        try:
            from win32_setctime import setctime
        except ImportError:
            setctime = None
            print(Fore.YELLOW + "\tWARNING: win32_setctime module is not installed,"
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

    for file in os.listdir(apks_dir):
        if os.path.splitext(file)[1].lower() != ".apks":
            continue

        apks_path = os.path.join(apks_dir, file)
        apk_path_unsigned = os.path.join(apks_dir, os.path.splitext(file)[0] + "_unsigned.apk")
        apk_path_signed = os.path.join(apks_dir, os.path.splitext(file)[0] + ".apk")
        old_app_stats = None

        try:
            old_app_stats = os.lstat(apks_path)
        except FileNotFoundError:
            print(Fore.YELLOW + "\tWARNING: %s does not exist.\n" % apks_path)
        except PermissionError:
            print(Fore.YELLOW + "\tWARNING: Couldn't get stats of the APKS file,"
                                " check permissions. Old timestamps wont be restored.\n")

        try:
            subprocess.run(convert_command % (apks_path, apk_path_unsigned), stdout=subprocess.DEVNULL,
                           stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            print(Fore.RED + "\tERROR: There was an error converting " + file + " to .apk\nError: %s\n" % e)
            if os.path.exists(apk_path_unsigned):
                try:
                    os.remove(apk_path_unsigned)
                except PermissionError:
                    print(Fore.RED + "\t\tERROR: Couldn't remove unfinished APK file. Permission denied.\n")
            continue

        try:
            subprocess.run(sign_command % (apk_path_unsigned, apk_path_signed), stdout=subprocess.DEVNULL,
                           stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            print(Fore.YELLOW + "\tWARNING: There was an error signing " + os.path.splitext(file)[0] + ".apk")
            print(Fore.RED + "\tError: %s\n" % e)
            continue

        if old_app_stats is not None:
            try:
                os.utime(apk_path_signed, (old_app_stats.st_atime, old_app_stats.st_mtime))
            except PermissionError:
                print(Fore.YELLOW + "\tWARNING: Couldn't restore old timestamps. Permission denied.\n")

            if platform.system() == "Windows" and "win32_setctime" in sys.modules:
                try:
                    setctime(apk_path_signed, old_app_stats.st_birthtime)
                except PermissionError:
                    print(Fore.YELLOW + "\tWARNING: Couldn't restore old creation date. Permission denied.\n")

        proc = True

        try:
            os.remove(apks_path)
        except PermissionError:
            print(Fore.YELLOW + "\tWARNING: Error deleting file " + apks_path + ". Permission denied\n")
            continue

        try:
            os.remove(apk_path_unsigned)
        except PermissionError:
            print(Fore.YELLOW + "\tWARNING: Error deleting file " + apk_path_unsigned + ". Permission denied\n")
            continue

    if proc:
        print(Fore.GREEN + "\nFinished converting all APKS files.\n")
    else:
        print(Fore.GREEN + "No APKS files were converted.\n")


def map_apk_to_packagename(repo_dir: str) -> Dict:
    mapped_apk_files = {}

    for apk_file in os.listdir(repo_dir):
        apk_file_path = os.path.join(repo_dir, apk_file)
        if os.path.isfile(apk_file_path) and os.path.splitext(apk_file_path)[1].lower() == ".apk":
            mapped_apk_files[ApkFile(apk_file_path).package_name] = apk_file

    return mapped_apk_files


def get_version(package_content: Dict,
                package_and_version: Dict,
                new_package: str,
                force_metadata: bool,
                force_version: bool) -> None:
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


def retrieve_info(package_list: Dict[str, str],
                  package_and_version: Dict[str, Tuple[int, str]],
                  lang: str,
                  metadata_dir: str,
                  repo_dir: str,
                  force_metadata: bool,
                  force_version: bool,
                  force_screenshots: bool,
                  force_icons: bool,
                  dl_screenshots: bool,
                  data_file_content: dict,
                  log_path: str,
                  cookie_path: list | None,
                  use_eng_name: bool):

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

        print(Fore.GREEN + "Processing " + package + "...\n")

        package_content = load_yml(metadata_dir=metadata_dir,
                                   package=package)

        if package_content is None:
            continue

        package_content_orig = copy.deepcopy(package_content)

        metadata_exist = None
        icons_exist = None
        screenshots_exist = None

        # If none of the force arguments is declared then check for available metadata, if screenshots
        # should be downloaded then check if they exist, otherwise check only for the rest of the data
        if dl_screenshots:
            if not force_metadata and not force_screenshots and not force_icons:
                metadata_exist = is_metadata_complete(package_content=package_content)
                icons_exist = is_icon_complete(package=package,
                                               version_code=package_and_version[new_package][0],
                                               repo_dir=repo_dir,
                                               data_file_content=data_file_content)
                screenshots_exist = screenshot_exist(package=package,
                                                     repo_dir=repo_dir)

                if metadata_exist and icons_exist and screenshots_exist:
                    if package_and_version[new_package][0] is None:
                        print(Fore.BLUE + "\tSkipping processing for the package as all the metadata"
                                          " is complete in the YML file, and screenshots exist.\n")
                        continue
                    else:
                        print(Fore.BLUE + "\tSkipping processing for the package as all the metadata is complete in "
                                          "the YML file, all the icons are available and screenshots exist.\n")
                        continue
        elif not force_metadata and not force_icons:
            metadata_exist = is_metadata_complete(package_content=package_content)
            icons_exist = is_icon_complete(package=package,
                                           version_code=package_and_version[new_package][0],
                                           repo_dir=repo_dir,
                                           data_file_content=data_file_content)

            if metadata_exist and icons_exist:
                if package_and_version[new_package][0] is None:
                    print(Fore.BLUE + "\tSkipping processing for the package as all the metadata "
                                      "is complete in the YML file.\n")
                    continue
                else:
                    print(Fore.BLUE + "\tSkipping processing for the package as all the metadata is complete in the "
                                      "YML file and all the icons are available.\n")
                    continue

        if (force_version and not force_metadata and not force_screenshots and not force_icons and metadata_exist
                and icons_exist):
            if screenshots_exist is not None:
                screenshots_exist = screenshot_exist(package=package,
                                                     repo_dir=repo_dir)
            if screenshots_exist:
                print(Fore.GREEN + "\tGetting version...\n")

                get_version(package_content=package_content,
                            package_and_version=package_and_version,
                            new_package=new_package,
                            force_metadata=force_metadata,
                            force_version=force_version)

                print(Fore.GREEN + "\tFinished getting version for %s.\n" % package)

                if package_content_orig != package_content:
                    write_yml(metadata_dir=metadata_dir,
                              package=package,
                              package_content=package_content)
                continue

        proc = True

        resp_list = []

        skip_package = False
        store_name = None

        for _ in [1]:
            print(Fore.GREEN + "\tDownloading Play Store page...\n")
            if get_play_store_page(new_package=new_package,
                                   resp_list=resp_list,
                                   language=lang):
                store_name = "Play_Store"
                break
            resp_list = []

            print(Fore.GREEN + "\tDownloading Amazon Appstore page...\n")
            if get_amazon_page(resp_list=resp_list,
                               language=lang,
                               new_package=new_package,
                               cookie_path=cookie_path):
                store_name = "Amazon_Store"
                break
            resp_list = []

            print(Fore.GREEN + "\tDownloading Apkcombo page...\n")
            if get_apkcombo_page(resp_list=resp_list,
                                 language=lang,
                                 new_package=new_package,
                                 data_file_content=data_file_content):
                store_name = "Apkcombo_Store"
                break
            resp_list = []

            not_found_packages.append(package)

            get_version(package_content=package_content,
                        package_and_version=package_and_version,
                        new_package=new_package,
                        force_metadata=force_metadata,
                        force_version=force_version)

            if package_content_orig != package_content:
                write_yml(metadata_dir=metadata_dir,
                          package=package,
                          package_content=package_content)

            print(Fore.GREEN + "Finished processing %s.\n" % package)
            skip_package = True

        if skip_package:
            continue

        resp = resp_list[0]
        resp_int = resp_list[1]

        print(Fore.GREEN + "\tExtracting information...\n")

        if not force_metadata:
            if metadata_exist is None:
                metadata_exist = is_metadata_complete(package_content=package_content)
            if not metadata_exist:
                get_metadata(package_content=package_content,
                             resp=resp,
                             resp_int=resp_int,
                             package=package,
                             name_not_found_packages=name_not_found_packages,
                             authorname_not_found_packages=authorname_not_found_packages,
                             authoremail_not_found_packages=authoremail_not_found_packages,
                             website_not_found_packages=website_not_found_packages,
                             category_not_found_packages=category_not_found_packages,
                             summary_not_found_packages=summary_not_found_packages,
                             description_not_found_packages=description_not_found_packages,
                             force_metadata=force_metadata,
                             data_file_content=data_file_content,
                             store_name=store_name,
                             use_eng_name=use_eng_name)
        else:
            get_metadata(package_content=package_content,
                         resp=resp,
                         resp_int=resp_int,
                         package=package,
                         name_not_found_packages=name_not_found_packages,
                         authorname_not_found_packages=authorname_not_found_packages,
                         authoremail_not_found_packages=authoremail_not_found_packages,
                         website_not_found_packages=website_not_found_packages,
                         category_not_found_packages=category_not_found_packages,
                         summary_not_found_packages=summary_not_found_packages,
                         description_not_found_packages=description_not_found_packages,
                         force_metadata=force_metadata,
                         data_file_content=data_file_content,
                         store_name=store_name,
                         use_eng_name=use_eng_name)

        get_version(package_content=package_content,
                    package_and_version=package_and_version,
                    new_package=new_package,
                    force_metadata=force_metadata,
                    force_version=force_version)

        print(Fore.GREEN + "\tFinished information extraction for %s.\n" % package)

        if package_content_orig != package_content:
            if not write_yml(metadata_dir=metadata_dir,
                             package=package,
                             package_content=package_content):
                continue

        if not force_icons and icons_exist is None:
            icons_exist = is_icon_complete(package=package,
                                           version_code=package_and_version[new_package][0],
                                           repo_dir=repo_dir,
                                           data_file_content=data_file_content)

        if force_icons or not icons_exist:
            print(Fore.GREEN + "\tDownloading icons...\n")
            # Function to download icons need to check force_icons because there might be cases where one of the icons
            # is missing, with screenshots as long as there is at least one file we assume it's complete.
            get_icon(resp_int=resp_int,
                     package=package,
                     new_package=new_package,
                     version_code=package_and_version[new_package][0],
                     repo_dir=repo_dir,
                     force_icons=force_icons,
                     data_file_content=data_file_content,
                     icon_not_found_packages=icon_not_found_packages,
                     store_name=store_name)
            print(Fore.GREEN + "\tFinished downloading icons for %s.\n" % package)
        else:
            print(Fore.BLUE + "\tAll icon files for %s already exist, skipping...\n" % package)

        if dl_screenshots:
            if not force_screenshots and screenshots_exist is None:
                screenshots_exist = screenshot_exist(package=package,
                                                     repo_dir=repo_dir)

            if force_screenshots or not screenshots_exist:
                get_screenshots(resp=resp,
                                repo_dir=repo_dir,
                                package=package,
                                new_package=new_package,
                                screenshots_not_found_packages=screenshots_not_found_packages,
                                data_file_content=data_file_content,
                                screenshots_exist=screenshots_exist,
                                store_name=store_name)
            else:
                print(Fore.BLUE + "\tScreenshots for %s already exists, skipping...\n" % package)

        print(Fore.GREEN + "Finished processing %s.\n" % package)

    if proc:
        print(Fore.GREEN + "Everything done! Don't forget to run:")
        print(Fore.CYAN + "\nfdroid rewritemeta\nfdroid update")
    else:
        print(Fore.GREEN + "Nothing was processed, no files changed.")

    if len(not_found_packages) != 0:
        print(Fore.YELLOW + "\nThese packages weren't found on any store:\n")
        for item in not_found_packages:
            print(Fore.YELLOW + item)
        write_not_found_log(items=not_found_packages, file_name="NotFound_Package", log_path=log_path)

    if len(authorname_not_found_packages) != 0:
        print(Fore.YELLOW + "\nThe AuthorName for these packages wasn't found:\n")
        for item in authorname_not_found_packages:
            print(Fore.YELLOW + item)
        write_not_found_log(items=authorname_not_found_packages, file_name="NotFound_AuthorName", log_path=log_path)

    if len(authoremail_not_found_packages) != 0:
        print(Fore.YELLOW + "\nThe AuthorName for these packages wasn't found:\n")
        for item in authoremail_not_found_packages:
            print(Fore.YELLOW + item)
        write_not_found_log(items=authoremail_not_found_packages, file_name="NotFound_AuthorEmail", log_path=log_path)

    if len(website_not_found_packages) != 0:
        print(Fore.YELLOW + "\nThe Website for these packages wasn't found:\n")
        for item in website_not_found_packages:
            print(Fore.YELLOW + item)
        write_not_found_log(items=website_not_found_packages, file_name="NotFound_Website", log_path=log_path)

    if len(summary_not_found_packages) != 0:
        print(Fore.YELLOW + "\nThe Summary for these packages wasn't found:\n")
        for item in summary_not_found_packages:
            print(Fore.YELLOW + item)
        write_not_found_log(items=summary_not_found_packages, file_name="NotFound_Summary", log_path=log_path)

    if len(description_not_found_packages) != 0:
        print(Fore.YELLOW + "\nThe Description for these packages wasn't found:\n")
        for item in description_not_found_packages:
            print(Fore.YELLOW + item)
        write_not_found_log(items=description_not_found_packages, file_name="NotFound_Description", log_path=log_path)

    if len(category_not_found_packages) != 0:
        print(Fore.YELLOW + "\nThe Category for these packages wasn't found:\n")
        for item in category_not_found_packages:
            print(Fore.YELLOW + item)
        write_not_found_log(items=category_not_found_packages, file_name="NotFound_Category", log_path=log_path)

    if len(name_not_found_packages) != 0:
        print(Fore.YELLOW + "\nThe Name for these packages wasn't found:\n")
        for item in name_not_found_packages:
            print(Fore.YELLOW + item)
        write_not_found_log(items=name_not_found_packages, file_name="NotFound_Name", log_path=log_path)

    if len(icon_not_found_packages) != 0:
        print(Fore.YELLOW + "\nThe icon URL for these packages wasn't found:\n")
        for item in icon_not_found_packages:
            print(Fore.YELLOW + item)
        write_not_found_log(items=icon_not_found_packages, file_name="NotFound_IconURL", log_path=log_path)

    if len(screenshots_not_found_packages) != 0:
        print(Fore.YELLOW + "\nThe screenshots URL for these packages weren't found:\n")
        for item in screenshots_not_found_packages:
            print(Fore.YELLOW + item)
        write_not_found_log(items=screenshots_not_found_packages,
                            file_name="NotFound_ScreenshotsURL",
                            log_path=log_path)


def get_metadata(package_content: dict,
                 resp: str,
                 resp_int: str,
                 package: str,
                 name_not_found_packages: list,
                 authorname_not_found_packages: list,
                 authoremail_not_found_packages: list,
                 website_not_found_packages: list,
                 category_not_found_packages: list,
                 summary_not_found_packages: list,
                 description_not_found_packages: list,
                 force_metadata: bool,
                 data_file_content: dict,
                 store_name: str,
                 use_eng_name: bool) -> None:
    author_name_pattern = data_file_content["Regex_Patterns"][store_name]["author_name_pattern"]
    author_email_pattern = data_file_content["Regex_Patterns"][store_name]["author_email_pattern"]
    name_pattern = data_file_content["Regex_Patterns"][store_name]["name_pattern"]
    website_pattern = data_file_content["Regex_Patterns"][store_name]["website_pattern"]
    category_pattern = data_file_content["Regex_Patterns"][store_name]["category_pattern"]
    summary_pattern = data_file_content["Regex_Patterns"][store_name]["summary_pattern"]
    summary_pattern_alt = data_file_content["Regex_Patterns"][store_name]["summary_pattern_alt"]
    description_pattern = data_file_content["Regex_Patterns"][store_name]["description_pattern"]
    gitlab_repo_id_pattern = data_file_content["Regex_Patterns"][store_name]["gitlab_repo_id_pattern"]
    ads_pattern = data_file_content["Regex_Patterns"][store_name]["ads_pattern"]
    inapp_purchases_pattern = data_file_content["Regex_Patterns"][store_name]["inapp_purchases_pattern"]
    tracking_pattern = data_file_content["Regex_Patterns"][store_name]["tracking_pattern"]

    if name_pattern != "":
        get_name(package_content=package_content,
                 name_pattern=name_pattern,
                 resp=resp,
                 resp_int=resp_int,
                 package=package,
                 name_not_found_packages=name_not_found_packages,
                 force_metadata=force_metadata,
                 use_eng_name=use_eng_name)

    if author_name_pattern != "":
        get_author_name(package_content=package_content,
                        author_name_pattern=author_name_pattern,
                        resp=resp,
                        package=package,
                        authorname_not_found_packages=authorname_not_found_packages,
                        force_metadata=force_metadata)

    if author_email_pattern != "":
        get_author_email(package_content=package_content,
                         author_email_pattern=author_email_pattern,
                         resp=resp,
                         package=package,
                         authoremail_not_found_packages=authoremail_not_found_packages,
                         force_metadata=force_metadata)

    website = ""

    if website_pattern != "":
        website = get_website(package_content=package_content,
                              website_pattern=website_pattern,
                              resp=resp,
                              package=package,
                              website_not_found_packages=website_not_found_packages,
                              force_metadata=force_metadata)

    get_repo_info_and_license(package_content=package_content,
                              gitlab_repo_id_pattern=gitlab_repo_id_pattern,
                              website=website,
                              data_file_content=data_file_content,
                              force_metadata=force_metadata)

    if category_pattern != "":
        get_categories(package_content=package_content,
                       category_pattern=category_pattern,
                       resp_int=resp_int,
                       package=package,
                       category_not_found_packages=category_not_found_packages,
                       data_file_content=data_file_content,
                       force_metadata=force_metadata,
                       store_name=store_name)

    if summary_pattern != "":
        if package_content.get("Summary", "") == "" or package_content.get("Summary") is None or force_metadata:
            if not get_summary(resp=resp,
                               package_content=package_content,
                               pattern=summary_pattern):
                if not get_summary(resp=resp,
                                   package_content=package_content,
                                   pattern=summary_pattern_alt):
                    print(Fore.YELLOW + "\tWARNING: Couldn't get the summary.\n")
                    summary_not_found_packages.append(package)

    if description_pattern != "":
        get_description(package_content=package_content,
                        description_pattern=description_pattern,
                        resp=resp,
                        package=package,
                        description_not_found_packages=description_not_found_packages,
                        force_metadata=force_metadata)

    get_anti_features(package_content=package_content,
                      website=website,
                      resp_int=resp_int,
                      force_metadata=force_metadata,
                      ads_pattern=ads_pattern,
                      inapp_purchases_pattern=inapp_purchases_pattern,
                      tracking_pattern=tracking_pattern)


def get_anti_features(package_content: dict,
                      website: str,
                      resp_int: str,
                      force_metadata: bool,
                      ads_pattern: str,
                      inapp_purchases_pattern: str,
                      tracking_pattern: str) -> None:

    if (package_content.get("AntiFeatures", "") == "" or package_content.get("AntiFeatures") is None
            or None in package_content.get("AntiFeatures") or force_metadata):
        if ("github.com/" or "gitlab.com/") in website:
            anti_features = ["NonFreeAssets"]
        else:
            anti_features = ["UpstreamNonFree", "NonFreeAssets"]

        if ads_pattern != "":
            if re.search(ads_pattern, resp_int) is not None:
                anti_features.append("Ads")

        if tracking_pattern != "":
            if re.search(tracking_pattern, resp_int) is not None:
                anti_features.append("Tracking")

        if inapp_purchases_pattern != "":
            if re.search(inapp_purchases_pattern, resp_int) is not None:
                anti_features.append("NonFreeDep")
                anti_features.append("NonFreeNet")

        package_content["AntiFeatures"] = anti_features


def get_author_email(package_content: dict,
                     author_email_pattern: str,
                     resp: str,
                     package: str,
                     authoremail_not_found_packages: list,
                     force_metadata: bool) -> None:
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
            print(Fore.YELLOW + "\tWARNING: Couldn't get the Author email.\n")
            authoremail_not_found_packages.append(package)


def get_description(package_content: dict,
                    description_pattern: str,
                    resp: str,
                    package: str,
                    description_not_found_packages: list,
                    force_metadata: bool) -> None:
    if package_content.get("Description", "") == "" or package_content.get("Description") is None or force_metadata:
        try:
            description_extracted = html.unescape(
                    re.search(description_pattern, resp).group(1)).replace("<br>", "\n").strip()

            description = ""
            for line in description_extracted.splitlines():
                if description == "":
                    description += line.strip()
                else:
                    description += "\n" + line.strip()

        except (IndexError, AttributeError):
            print(Fore.YELLOW + "\tWARNING: Couldn't get the description.\n")
            description_not_found_packages.append(package)
            return

        package_content["Description"] = description


def get_name(package_content: dict,
             name_pattern: str,
             resp: str,
             resp_int: str,
             package: str,
             name_not_found_packages: list,
             force_metadata: bool,
             use_eng_name: bool) -> None:
    if package_content.get("Name", "") == "" or package_content.get("Name") is None or force_metadata:

        if use_eng_name:
            resp_final = resp_int
        else:
            resp_final = resp

        try:
            package_content["Name"] = html.unescape(re.search(name_pattern, resp_final).group(1)).strip()
        except (IndexError, AttributeError):
            print(Fore.YELLOW + "\tWARNING: Couldn't get the application name.\n")
            name_not_found_packages.append(package)


def get_categories(package_content: dict,
                   category_pattern: str,
                   resp_int: str,
                   package: str,
                   category_not_found_packages: list,
                   data_file_content: dict,
                   force_metadata: bool,
                   store_name: str) -> None:
    if store_name == "Amazon_store":
        # Amazon Appstore doesn't show the app's categories in the app page.
        return

    if (package_content.get("Categories", "") == "" or
            package_content.get("Categories", "") == ["fdroid_repo"] or
            package_content.get("Categories") is None or
            None in package_content.get("Categories") or force_metadata):
        ret_grp = re.search(category_pattern, resp_int)

        if ret_grp is not None:
            cat_list = extract_categories(ret_grp=ret_grp,
                                          resp_int=resp_int,
                                          data_file_content=data_file_content,
                                          store_name=store_name)
            package_content["Categories"] = cat_list
        else:
            print(Fore.YELLOW + "\tWARNING: Couldn't get the categories.\n")
            category_not_found_packages.append(package)


def extract_categories(ret_grp: re.Match,
                       resp_int: str,
                       data_file_content: dict,
                       store_name: str):

    sport_category_pattern = data_file_content["Sport_Category_Pattern"][store_name]

    cat_list = []

    for cat in ret_grp.groups():
        if html.unescape(cat.strip()) == "Sports":
            if (sport_category_pattern is not None
                    and sport_category_pattern != ""
                    and resp_int.find(sport_category_pattern)):
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


def get_repo_info_and_license(package_content: dict,
                              gitlab_repo_id_pattern: str,
                              website: str,
                              data_file_content: dict,
                              force_metadata: bool) -> None:
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


def get_website(package_content: dict,
                website_pattern: str,
                resp: str,
                package: str,
                website_not_found_packages: list,
                force_metadata: bool) -> str:
    website = ""

    try:
        website = (re.search(website_pattern, resp).group(1).strip())
    except (IndexError, AttributeError):
        print(Fore.YELLOW + "\tWARNING: Couldn't get the app website.\n")
        website_not_found_packages.append(package)

    if website != "" and (package_content.get("WebSite", "") == "" or package_content.get("WebSite") is None
                          or force_metadata):
        package_content["WebSite"] = website.replace("http://", "https://")

    return website


def get_author_name(package_content: dict,
                    author_name_pattern: str,
                    resp: str,
                    package: str,
                    authorname_not_found_packages: list,
                    force_metadata: bool) -> None:
    try:
        if package_content.get("AuthorName", "") == "" or package_content.get("AuthorName") is None or force_metadata:
            package_content["AuthorName"] = html.unescape(re.search(author_name_pattern, resp).group(1)).strip()
    except (IndexError, AttributeError):
        print(Fore.YELLOW + "\tWARNING: Couldn't get the Author name.\n")
        authorname_not_found_packages.append(package)


def get_play_store_page(new_package: str,
                        resp_list: list,
                        language: str) -> bool:

    playstore_url = "https://play.google.com/store/apps/details?id="

    playstore_url_comp_int = playstore_url + new_package + "&hl=en-US"
    playstore_url_comp = playstore_url + new_package + "&hl=" + language

    try:
        resp_list.append(urllib.request.urlopen(playstore_url_comp).read().decode())
    except HTTPError as e:
        if e.code == 404:
            print(Fore.YELLOW + "\t%s was not found on the Play Store.\n" % new_package)
        return False

    if playstore_url_comp == playstore_url_comp_int:
        resp_list.append(resp_list[0])
    else:
        try:
            resp_list.append(urllib.request.urlopen(playstore_url_comp_int).read().decode())
        except HTTPError as e:
            if e.code == 404:
                print(Fore.YELLOW + "\t%s was not found on the Play Store (en-US).\n" % new_package)
            return False

    if ">We're sorry, the requested URL was not found on this server.</div>" in resp_list[1]:
        print(Fore.YELLOW + "\t%s was not found on the Play Store.\n" % new_package)
        return False

    return True


def get_summary(resp: str,
                package_content: dict,
                pattern: str) -> bool:
    try:
        summary = html.unescape(re.search(pattern, resp).group(1)).strip()
        summary = re.sub(r"(<[^>]+>)", "", summary).strip()

        while len(summary) > 80:
            try:
                summary = re.search(r"(^.+)\.\s+.+$", summary).group(1)
            except (IndexError, AttributeError):
                summary = re.search(r"^(.+)\s\S+\s*$", summary[:77]).group(1) + "..."

        package_content["Summary"] = summary.strip()

        return True
    except (IndexError, AttributeError):
        return False


def get_license(package_content: dict,
                force_metadata: bool,
                api_repo: str,
                data_file_content: dict):
    if (package_content.get("License", "") == "" or package_content.get("License", "") == "Unknown"
            or package_content.get("License") is None or force_metadata):
        try:
            api_load = urllib.request.urlopen(api_repo).read().decode()
        except HTTPError:
            print(Fore.YELLOW + "\tCouldn't download the api response for the license.\n")
            return

        try:
            resp_api = json.loads(api_load)  # type: dict
        except json.JSONDecodeError:
            print(Fore.YELLOW + "\tCouldn't load the api response for the license.\n")
            return

        if resp_api["license"] is not None:
            package_content["License"] = normalize_license(data_file_content, resp_api["license"]["key"])
        else:
            package_content["License"] = "No License"


def normalize_license(data_file_content: dict,
                      license_key: str) -> str:
    license_dict = {}
    for key in data_file_content["Licenses"]:
        license_dict[key.lower().strip()] = key

    if license_key.lower().strip() in license_dict.keys():
        return license_dict[license_key.lower().strip()]
    elif license_key.lower().strip() + "-only" in license_dict.keys():
        return license_dict[license_key.lower().strip() + "-only"]
    else:
        return "Other"


def get_screenshots(resp: str,
                    repo_dir: str,
                    package: str,
                    new_package: str,
                    screenshots_not_found_packages: list,
                    data_file_content: dict,
                    screenshots_exist: bool,
                    store_name: str) -> None:
    # Locale directory must be en-US and not the real locale because that's what F-Droid
    # defaults to and this program does not do multi-lang download.
    screenshots_path = os.path.join(repo_dir, package, "en-US", "phoneScreenshots")
    backup_path = os.path.join(repo_dir, "backup", package, "en-US", "phoneScreenshots")

    if os.path.exists(screenshots_path) and ".noscreenshots" in os.listdir(screenshots_path):
        return

    screenshot_pattern = data_file_content["Regex_Patterns"][store_name]["screenshot_pattern"]

    if screenshot_pattern == "":
        return

    print(Fore.GREEN + "\tDownloading screenshots for %s\n" % package)

    if store_name == "Apkcombo_Store":
        screenshot_pattern_alt = data_file_content["Regex_Patterns"][store_name]["screenshot_pattern_alt"]

        try:
            scrn_div = re.search(screenshot_pattern, resp).group(1)
        except (AttributeError, IndexError):
            print(Fore.YELLOW + "\tCouldn't get screenshots URLs for %s\n" % new_package)
            screenshots_not_found_packages.append(package)
            return

        img_url_list = re.findall(screenshot_pattern_alt, scrn_div)
    else:
        img_url_list = re.findall(screenshot_pattern, resp)  # type: List[str]

    if len(img_url_list) == 0:
        print(Fore.YELLOW + "\tCouldn't get screenshots URLs for %s\n" % new_package)
        screenshots_not_found_packages.append(package)
        return

    if screenshots_exist:
        try:
            shutil.rmtree(backup_path)
        except FileNotFoundError:
            pass
        except PermissionError as e:
            print(Fore.RED + "\tCouldn't remove the old backup directory. Permission denied.\n\t%s\n" % e)
            return

        try:
            os.makedirs(backup_path)
        except PermissionError as e:
            print(Fore.RED + "\tCouldn't create backup directory for screenshots. Permission denied.\n\t%s\n" % e)
            return

        try:
            os.rename(screenshots_path, backup_path)
        except FileNotFoundError:
            pass
        except PermissionError:
            print(Fore.RED + "\tCouldn't move the screenshots to the backup directory. Permission denied.\n")
            return

    try:
        os.makedirs(screenshots_path)
    except FileExistsError:
        pass
    except PermissionError:
        print(Fore.RED + "\tError creating the directory where the screenshots should be saved. Permission denied.\n")
        return

    pad_amount = len(str(len(img_url_list)))

    i = 0

    for img_url in img_url_list:
        if store_name == "Play_Store" or store_name == "Apkcombo_Store":
            url = img_url + "=w9999"
        else:
            url = img_url
        ss_path = os.path.join(screenshots_path, str(i).zfill(pad_amount) + ".png")
        try:
            urllib.request.urlretrieve(url, ss_path)
            i += 1
        except HTTPError:
            pass
        except PermissionError:
            print(Fore.RED + "\tError downloading screenshots. Permission denied.\n")
            return

    print(Fore.GREEN + "\tFinished downloading screenshots for %s.\n" % package)


def extract_icon_url(resp_int: str,
                     icon_pattern: str) -> str | None:
    try:
        icon_base_url = re.search(icon_pattern, resp_int).group(1)
    except (IndexError, AttributeError):
        return None

    if icon_base_url == "":
        return None
    else:
        return icon_base_url


def extract_icon_url_alt(resp_int: str,
                         icon_pattern_alt: str) -> str | None:
    try:
        icon_base_url_alt = re.search(icon_pattern_alt, resp_int).group(1)
    except (IndexError, AttributeError):
        return None

    if icon_base_url_alt == "":
        return None
    else:
        return icon_base_url_alt


def get_icon(resp_int: str,
             package: str,
             new_package: str,
             version_code: int | None,
             repo_dir: str,
             force_icons: bool,
             data_file_content: dict,
             icon_not_found_packages: list,
             store_name: str) -> None:
    icon_pattern = data_file_content["Regex_Patterns"][store_name]["icon_pattern"]
    icon_pattern_alt = data_file_content["Regex_Patterns"][store_name]["icon_pattern_alt"]

    if icon_pattern == "":
        return

    if version_code is None or version_code == 0:
        # if a metadata_dir is specified and the corresponding APK file doesn't exist in the repo dir then we can't
        # get the VersionCode needed to store the icons hence return
        print(Fore.YELLOW + "\tWARNING: The corresponding APK file doesn't exist in the repo directory, "
                            "version code can't be retrieved and icons wont be downloaded.\n")
        return

    icon_base_url_alt = None

    icon_base_url = extract_icon_url(resp_int, icon_pattern)

    if icon_base_url is None:
        if icon_pattern_alt == "":
            print(Fore.YELLOW + "\tCouldn't extract icon URL for %s.\n" % new_package)
            icon_not_found_packages.append(package)
            return
        else:
            icon_base_url_alt = extract_icon_url_alt(resp_int, icon_pattern_alt)
            if icon_base_url_alt is None:
                print(Fore.YELLOW + "\tCouldn't extract icon URL for %s.\n" % new_package)
                icon_not_found_packages.append(package)
                return

    filename = package + "." + str(version_code) + ".png"

    for dirname in data_file_content["Icon_Relations"].keys():
        try:
            os.makedirs(os.path.join(repo_dir, dirname))
        except FileExistsError:
            pass
        except PermissionError:
            print(Fore.RED + "\tERROR: Can't create directory for \"" + dirname +
                  "\". Permission denied, skipping icon download for this package.\n")
            icon_not_found_packages.append(package)
            return

    if icon_base_url is not None:
        if store_name == "Play_Store" or store_name == "Apkcombo_Store":
            for dirname in data_file_content["Icon_Relations"].keys():
                icon_path = os.path.join(repo_dir, dirname, filename)

                if os.path.exists(icon_path) and not force_icons:
                    continue

                url = icon_base_url + data_file_content["Icon_Relations"][dirname]

                try:
                    urllib.request.urlretrieve(url, icon_path)
                except urllib.error.HTTPError:
                    print(Fore.YELLOW + "\tCouldn't download icon for %s." % dirname)
                except PermissionError:
                    print(Fore.YELLOW + "\tCouldn't write icon file for %s. Permission denied." % dirname)
                    return
        elif store_name == "Amazon_Store":

            main_icon_path = ""

            for dirname in data_file_content["Icon_Relations"].keys():

                icon_path = os.path.join(repo_dir, dirname, filename)

                if os.path.exists(icon_path) and not force_icons:
                    continue

                if main_icon_path == "":
                    tmp_dir = tempfile.mkdtemp()
                    try:
                        urllib.request.urlretrieve(icon_base_url, os.path.join(tmp_dir, filename))
                        main_icon_path = os.path.join(tmp_dir, filename)
                    except urllib.error.HTTPError:
                        print(Fore.YELLOW + "\tCouldn't download icon for %s." % dirname)
                        return
                    except PermissionError:
                        print(Fore.YELLOW + "\tCouldn't write icon file for %s. Permission denied." % dirname)
                        return

                orig_img = Image.open(main_icon_path)
                resized_img = orig_img.resize((int(data_file_content["Icon_Relations"][dirname]),
                                               int(data_file_content["Icon_Relations"][dirname])))
                resized_img.save(icon_path)
                orig_img.close()

    elif icon_base_url_alt is not None:
        if store_name == "Play_Store":
            for dirname in data_file_content["Icon_Relations"].keys():
                icon_path = os.path.join(repo_dir, dirname, filename)

                if os.path.exists(icon_path) and not force_icons:
                    continue

                url = (icon_base_url_alt + data_file_content["Icon_Relations"][dirname] + "-h" +
                       data_file_content["Icon_Relations"][dirname])  # type: str

                try:
                    urllib.request.urlretrieve(url, icon_path)
                except urllib.error.HTTPError:
                    print(Fore.YELLOW + "\tCouldn't download icon for %s." % dirname)
                except PermissionError:
                    print(Fore.YELLOW + "\tCouldn't write icon file for %s. Permission denied." % dirname)


def sanitize_lang(lang: str):
    lang = lang.strip().lower()

    if lang == "es":
        lang = "es-Es"
    elif lang == "419":
        lang = "es-419"
    elif lang == "en":
        lang = "en-US"
    elif lang == "us":
        lang = "en-US"
    elif lang == "pt":
        lang = "pt-PT"
    elif lang == "fr":
        lang = "fr-FR"
    elif lang == "zh":
        lang = "zh-CN"
    elif lang == "br":
        lang = "pt-BR"
    elif lang == "gb":
        lang = "en-GB"
    elif lang == "ca":
        lang = "fr-CA"
    elif lang == "hk":
        lang = "zh-HK"
    elif lang == "tw":
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


def is_icon_complete(package: str,
                     version_code: int | None,
                     repo_dir: str,
                     data_file_content: dict) -> bool:
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


def screenshot_exist(package: str,
                     repo_dir: str) -> bool:
    screenshots_path = os.path.join(repo_dir, package, "en-US", "phoneScreenshots")

    if not os.path.exists(screenshots_path):
        return False
    elif len(os.listdir(screenshots_path)) > 0:
        return True
    else:
        return False


def write_yml(metadata_dir: str,
              package: str,
              package_content: Dict) -> bool:
    try:
        stream = open(os.path.join(metadata_dir, package + ".yml"), "w", encoding="utf_8")

        yaml = ruamel.yaml.YAML()
        yaml.indent(mapping=2, sequence=4, offset=2)
        ruamel.yaml.scalarstring.walk_tree(package_content)
        yaml.dump(package_content, stream)

        stream.close()

        return True
    except PermissionError:
        print(Fore.RED + "\tERROR: Couldn't write YML file for %s. Permission denied.\n" % package)
        return False


def load_yml(metadata_dir: str,
             package: str) -> Optional[Dict]:
    if os.path.exists(os.path.join(metadata_dir, package + ".yml")):
        try:
            stream = open(os.path.join(metadata_dir, package + ".yml"), "r", encoding="utf_8")

            yaml = ruamel.yaml.YAML(typ="safe")
            package_content = yaml.load(stream)  # type:Dict

            stream.close()

            if package_content is None:
                return {}
            else:
                return package_content
        except PermissionError:
            print(Fore.YELLOW + "\tWARNING: Couldn't read metadata file. Permission denied, skipping package...\n")
            return None
    else:
        return {}


def write_not_found_log(items: list,
                        file_name: str,
                        log_path: str) -> None:
    today_date = datetime.today().strftime("%Y%m%d_%H%M%S")
    file_name = os.path.join(log_path, file_name + "_" + today_date + ".log")

    try:
        log_stream = open(file_name, "w")
    except IOError as e:
        print(Fore.RED + e)
        return

    for item in items:
        try:
            log_stream.write(item + "\n")
        except IOError as e:
            print(Fore.RED + e)
            return


def get_amazon_page(resp_list: list,
                    language: str,
                    new_package: str,
                    cookie_path: list | None) -> bool:

    if cookie_path is None:
        print(Fore.YELLOW + "\tCookie file was not specified. Amazon Appstore page download will not be performed.\n")
        return False

    cookie_jar = MozillaCookieJar(cookie_path[0])
    url = "https://www.amazon.com/gp/mas/dl/android?p=" + new_package

    alt_language = re.sub(r"-.+", "", language)

    sess = requests.Session()
    sess.cookies = cookie_jar
    sess.cookies.load()

    sess.headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Accept-Language": language + "," + alt_language
    }

    resp = sess.get(url, allow_redirects=True)

    if resp.url.find("https://www.amazon.com/gp/browse.html") != -1:
        print(Fore.YELLOW + "\t%s was not found on the Amazon Appstore.\n" % new_package)
        return False

    resp = resp.content.decode(encoding="utf_8", errors="replace")

    if "<p class=\"a-last\">Sorry, we just need to make sure you're not a robot." in resp:
        print(Fore.RED + "\tERROR: Cookie file doesn't contain Amazon cookies.\n")
        return False

    if language == "en-US":
        resp_int = resp
    else:
        sess.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Accept-Language": "en-US,en"
        }

        resp_int = sess.get(url, allow_redirects=True)

        if resp_int.url.find("https://www.amazon.com/gp/browse.html") != -1:
            print(Fore.YELLOW + "\t%s was not found on the Amazon Appstore (INT).\n" % new_package)
            return False

        resp_int = resp_int.content.decode(encoding="utf_8", errors="replace")

    resp_list.append(resp)
    resp_list.append(resp_int)

    return True


def get_apkcombo_page(resp_list: list,
                      language: str,
                      new_package: str,
                      data_file_content: dict) -> bool:

    url_int = "https://apkcombo.com/xxxx/" + new_package

    alt_language = re.sub(r"-.+", "", language)
    new_language = sanitize_lang_apkcombo(language=alt_language,
                                          data_file_content=data_file_content)

    url = "https://apkcombo.com/" + new_language + "/xxxx/" + new_package

    sess = requests.Session()

    sess.headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Accept-Language": language + "," + alt_language
    }

    resp = sess.get(url, allow_redirects=True)
    resp = resp.content.decode(encoding="utf_8", errors="replace")

    if resp.find("We're sorry, the app was not found on APKCombo.") != -1:
        print(Fore.YELLOW + "\t%s was not found on Apkcombo.\n" % new_package)
        return False

    if new_language == "en":
        resp_int = resp
    else:
        sess.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Accept-Language": "en-US,en"
        }

        resp_int = sess.get(url_int, allow_redirects=True)
        resp_int = resp_int.content.decode(encoding="utf_8", errors="replace")

        if resp_int.find("We're sorry, the app was not found on APKCombo.") != -1:
            print(Fore.YELLOW + "\t%s was not found on Apkcombo.\n" % new_package)
            return False

    resp_list.append(resp)
    resp_list.append(resp_int)

    return True


def sanitize_lang_apkcombo(language: str,
                           data_file_content: dict) -> str:
    if language == "in":
        language = "id"

    if language not in data_file_content["Locales"]["Apkcombo_Store"]:
        print(Fore.YELLOW + "\tThe language %s is not available in Apkcombo, English will be used instead." % language)
        language = "en"

    return language


if __name__ == "__main__":
    main()
