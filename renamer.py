"""
Rename APK and APKS files to new names based on a supplied pattern.
"""

import argparse
import copy
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime

from colorama import Fore, init

from common import get_program_dir

APK_EXTENSION = ".apk"
APKS_EXTENSION = ".apks"

PACKAGE_NAME = "Package Name"
PACKAGE_VERSION_CODE = "Version Code"
PACKAGE_VERSION_NAME = "Version Name"
PACKAGE_MIN_SDK = "Minimum SDK"
PACKAGE_MAX_SDK = "Maximum SDK"
PACKAGE_TARGET_SDK = "Target SDK"
PACKAGE_COMPILE_SDK = "Compile SDK"
PACKAGE_SUPPORTED_SCREENS = "Supported Screens"
PACKAGE_SUPPORTED_ABIS = "Supported ABIs"
PACKAGE_SUPPORTED_DEVICES = "Supported Devices"
PACKAGE_DENSITIES = "Densities"
PACKAGE_LOCALES = "Locales"
PACKAGE_LABEL = "Label"


def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description=textwrap.dedent(
                                             """
    Rename APK and APKS files based on the supplied pattern.
    If any placeholder contains multiple values they are all merged with a comma as the separator.
    If any placeholder contains illegal characters or spaces they are all replaced with the supplied separator or '_' 
    by default.
    
    Placeholders supported:
    ======================================
    - Original filename:          %orig_name%
    - Original app name:          %label% | %name%
    - Version name:               %version% | %version_name%
    - Version code:               %build% | %version_code%
    - Package ID/Name:            %package% | %package_name% | %package_id%
    - SDK:                        %min_sdk%, %max_sdk%, %target_sdk%, %compile_sdk%
    - Android version number:     %min_android_num%, %max_android_num%, %target_android_num%, %compile_android_num%
    - Android version name:       %min_android_name%, %max_android_name%, %target_android_name%, %compile_android_name%
    - Supported screens:          %supported_screens% | %screens%
    - Supported DPIs:             %supported_dpis% | %dpis%
    - Supported ABIs:             %supported_abis% | %abis%
    - Supported devices:          %supported_devices% | %devices%
    - Supported locales:          %supported_locales% | %locales%
    ======================================
    """))
    parser.add_argument("--path",
                        help="Path to a directory or a single APK file.",
                        required=True,
                        type=str,
                        nargs=1)
    parser.add_argument("--pattern",
                        help="Pattern used to rename files.",
                        required=True,
                        type=str,
                        nargs=1)
    parser.add_argument("--separator",
                        help="Replace any white space and invalid characters in the filename with this character. "
                             "It doesn't apply to ABIs, densities, screens, locales and supported devices."
                             " Optional, default is one underscore (_).",
                        default=["_"],
                        type=str,
                        nargs=1)
    parser.add_argument("--skip-if-exists",
                        help="Skip renaming if the file already exists. "
                             "By default a numeric suffix is appended to the name.",
                        action="store_true")
    parser.add_argument("--build-tools-path",
                        help="Path to aapt and aapt2 executables. By default uses the ones located in PATH.",
                        type=str,
                        nargs=1)
    parser.add_argument("--log-path",
                        help="Path to the directory where to store the log files. Default: Program's directory.",
                        type=str,
                        nargs=1)
    parser.add_argument("--no-log",
                        help="Don't create log files.",
                        action="store_true")
    parser.add_argument("--convert-apks",
                        help="Convert .apks files to .apk.",
                        action="store_true")
    parser.add_argument("--apk-editor-path",
                        help="Path to the ApkEditor.jar file.",
                        type=str,
                        nargs=1)
    parser.add_argument("--sign-apk",
                        help="Sign converted APK files.",
                        action="store_true")
    parser.add_argument("--key-file",
                        help="Key file used to sign the APK, required if --convert-apks is used.",
                        type=str,
                        nargs=1)
    parser.add_argument("--cert-file",
                        help="Certificate file used to sign the APK, required if --convert-apks is used.",
                        type=str,
                        nargs=1)
    parser.add_argument("--certificate-password",
                        help="Certificate's password used to sign the converted APK.",
                        type=str,
                        nargs=1)

    args = parser.parse_args()

    init(autoreset=True)

    if args.build_tools_path is None:
        build_tools_path = args.build_tools_path
    else:
        build_tools_path = os.path.abspath(args.build_tools_path[0])  # type: str | None

    if args.key_file is None:
        key_file = args.key_file
    else:
        key_file = os.path.abspath(args.key_file[0])  # type: str | None

    if args.cert_file is None:
        cert_file = args.cert_file
    else:
        cert_file = os.path.abspath(args.cert_file[0])  # type: str | None

    if args.certificate_password is None:
        certificate_password = args.certificate_password
    else:
        certificate_password = args.certificate_password[0]  # type: str | None

    if args.apk_editor_path is None:
        apk_editor_path = args.apk_editor_path
    else:
        apk_editor_path = os.path.abspath(args.apk_editor_path[0])  # type: str | None

    if args.log_path is None:
        log_path = get_program_dir()
    else:
        log_path = os.path.abspath(args.log_path[0])

    item_path = os.path.abspath(args.path[0])
    pattern = args.pattern[0]  # type: str
    separator = args.separator[0]  # type: str

    no_log = args.no_log  # type: bool
    skip_if_exists = args.skip_if_exists  # type: bool
    convert_apks = args.convert_apks  # type: bool
    sign_apk = args.sign_apk  # type: bool

    if build_tools_path is None:
        if shutil.which("aapt") is None:
            print(Fore.RED + "ERROR: Could not find aapt executable in PATH. Please install it.")
            sys.exit(1)

        if shutil.which("aapt2") is None:
            print("Could not find aapt2 executable in PATH. Please install it.")
            sys.exit(1)
    else:
        if not os.path.exists(build_tools_path):
            print(Fore.RED + "ERROR: Provided aapt path doesn't exist.")
            sys.exit(1)
        if not os.path.isdir(build_tools_path):
            print(Fore.RED + "ERROR: Provided aapt path is not a directory.")
            sys.exit(1)

    if not os.path.exists(log_path):
        os.makedirs(log_path)
    elif not os.path.isdir(log_path):
        print(Fore.RED + "ERROR: Provided log path is not a directory.")
        sys.exit(1)

    if convert_apks:
        if shutil.which("java") is None:
            print(Fore.RED + "ERROR: Java not found in PATH, can't convert .apks files to .apk.")
            sys.exit(1)

        if apk_editor_path is None:
            print(Fore.RED + "ERROR: Please specify the full path to the ApkEditor JAR file.")
            sys.exit(1)
        elif not os.path.isfile(apk_editor_path):
            print(Fore.RED + "ERROR: Invalid ApkEditor JAR path.")
            sys.exit(1)

    if sign_apk:
        if build_tools_path is None and shutil.which("apksigner") is None:
            print(Fore.RED + "ERROR:Please install the build-tools package of the Android SDK if you want to convert "
                             "APKS files.")
            print(Fore.RED + "Apksigner not found.")
            sys.exit(1)

        if key_file is None or cert_file is None:
            print(Fore.RED + "ERROR: Please provide the key and certificate files for APK signing.\n")
            sys.exit(1)
        else:
            if not os.path.isfile(key_file):
                print(Fore.RED + "ERROR: Invalid key file path.")
                sys.exit(1)

            if not os.path.isfile(cert_file):
                print(Fore.RED + "ERROR: Invalid cert file path.")
                sys.exit(1)

    if (os.path.isfile(item_path) and os.path.splitext(item_path)[1].lower() != APK_EXTENSION
            and os.path.splitext(item_path)[1].lower() != APKS_EXTENSION):
        print(Fore.RED + "ERROR: Supplied path is not an APK or APKS file.")
        sys.exit(1)

    errored_apps_list = []

    process_path(item_path=item_path,
                 pattern=pattern,
                 separator=separator,
                 errored_apps_list=errored_apps_list,
                 build_tools_path=build_tools_path,
                 convert_apks=convert_apks,
                 apk_editor_path=apk_editor_path,
                 sign_apk=sign_apk,
                 key_file=key_file,
                 cert_file=cert_file,
                 certificate_password=certificate_password,
                 skip_if_exists=skip_if_exists)

    if len(errored_apps_list) > 0 and not no_log:
        write_log(items=errored_apps_list,
                  file_name="ErroredApps",
                  log_path=log_path)

    print(Fore.GREEN + "All done!")


def process_path(item_path: str,
                 pattern: str,
                 separator: str = "_",
                 errored_apps_list: list[str] | None = None,
                 build_tools_path: str | None = None,
                 convert_apks: bool = False,
                 apk_editor_path: str | None = None,
                 sign_apk: bool = False,
                 key_file: str | None = None,
                 cert_file: str | None = None,
                 certificate_password: str | None = None,
                 skip_if_exists: bool = False) -> None:
    """
    | Rename APK and APKS files based on the supplied pattern.
    |
    | If any placeholder contains multiple values, they are all merged with a comma as the separator.
    |
    | If any placeholder contains illegal characters or spaces, they are all replaced with the supplied separator or
     one '_' (underscore) by default.
    |

    | Placeholders supported:
    * **Original filename**:          %orig_name%
    * **Original app name**:          %label% **|** %name%
    * **Version name**:               %version% **|** %version_name%
    * **Version code**:               %build% **|** %version_code%
    * **Package ID/Name**:            %package% **|** %package_name% **|** %package_id%
    * **SDK**:                        %min_sdk%, %max_sdk%, %target_sdk%, %compile_sdk%
    * **Android version number**:     %min_android_num%, %max_android_num%, %target_android_num%, %compile_android_num%
    * **Android version name**:       %min_android_name%, %max_android_name%, %target_android_name%,
      %compile_android_name%
    * **Supported screens**:          %supported_screens% **|** %screens%
    * **Supported DPIs**:             %supported_dpis% **|** %dpis%
    * **Supported ABIs**:             %supported_abis% **|** %abis%
    * **Supported devices**:          %supported_devices% **|** %devices%
    * **Supported locales**:          %supported_locales% **|** %locales%

    :param item_path: Path to a file or directory.
    :param pattern: Pattern for file renaming.
    :param separator: Character to replace with any spaces and illegal characters found in the placeholder values.
    :param errored_apps_list: List to store errored files.
    :param build_tools_path: Path to build-tools directory of the Android SDK. Only *aapt* and *aapt2* are used from
     this directory unless `sign_apk` is `True` in which case *apksigner* will be used too. If not supplied, they will
     be searched for in **PATH**.
    :param convert_apks: Whether to convert APKS files to APK. Defaults to `False`.
    :param apk_editor_path: Path to the ApkEditor JAR file used to convert APKS files.
    :param sign_apk: Whether to sign the resulting APK files. Defaults to `False`.
    :param key_file: Path to the key file used for APK signing.
    :param cert_file: Path to the certificate file used for APK signing.
    :param certificate_password: Certificate's password.
    :param skip_if_exists: Skip the rename if the output filename already exists. Defaults to `False`.
    """

    if os.path.isfile(item_path):
        process_file(item_path=item_path,
                     pattern=pattern,
                     separator=separator,
                     errored_apps_list=errored_apps_list,
                     build_tools_path=build_tools_path,
                     convert_apks=convert_apks,
                     apk_editor_path=apk_editor_path,
                     sign_apk=sign_apk,
                     key_file=key_file,
                     cert_file=cert_file,
                     certificate_password=certificate_password,
                     skip_if_exists=skip_if_exists)
    elif os.path.isdir(item_path):
        # for root, dirs, files in os.walk(item_path):
        #    filenames = dirs + files
        #    for file in filenames:
        for file in os.listdir(item_path):
            file_path = os.path.join(item_path, file)

            process_file(item_path=file_path,
                         pattern=pattern,
                         separator=separator,
                         errored_apps_list=errored_apps_list,
                         build_tools_path=build_tools_path,
                         convert_apks=convert_apks,
                         apk_editor_path=apk_editor_path,
                         sign_apk=sign_apk,
                         key_file=key_file,
                         cert_file=cert_file,
                         certificate_password=certificate_password,
                         skip_if_exists=skip_if_exists)


def process_file(item_path: str,
                 pattern: str,
                 separator: str,
                 errored_apps_list: list[str] | None = None,
                 build_tools_path: str | None = None,
                 convert_apks: bool = False,
                 apk_editor_path: str | None = None,
                 sign_apk: bool = False,
                 key_file: str | None = None,
                 cert_file: str | None = None,
                 certificate_password: str | None = None,
                 skip_if_exists: bool = False) -> None:

    apk_info = {}

    if os.path.isdir(item_path):
        return

    if (os.path.splitext(item_path)[1].lower() != APK_EXTENSION and
            os.path.splitext(item_path)[1].lower() != APKS_EXTENSION):
        return

    apk_info = get_info(app_file_path=item_path,
                        build_tools_path=build_tools_path,
                        errored_apps_list=errored_apps_list,
                        apk_info=apk_info)

    if len(apk_info) == 0:
        return

    new_file_name = rename_file(pattern=pattern,
                                apk_info=apk_info,
                                separator=separator,
                                file_path=item_path,
                                errored_apps_list=errored_apps_list,
                                skip_if_exists=skip_if_exists)

    if new_file_name is None:
        return

    if item_path.lower().endswith(APKS_EXTENSION) and convert_apks:
        convert_to_apk(key_file=key_file,
                       cert_file=cert_file,
                       certificate_password=certificate_password,
                       apks_file=new_file_name,
                       build_tools_path=build_tools_path,
                       sign_apk=sign_apk,
                       apk_editor_path=apk_editor_path)


def write_log(items: list,
              file_name: str,
              log_path: str) -> None:
    today_date = datetime.today().strftime("%Y%m%d_%H%M%S")
    file_name = os.path.join(log_path, file_name + "_" + today_date + ".log")

    try:
        log_stream = open(file_name, "w")
    except IOError as e:
        print(e, end="\n\n")
        return

    for item in items:
        try:
            log_stream.write(item + "\n")
        except IOError as e:
            print(e, end="\n\n")
            return


def rename_file(file_path: str,
                pattern: str,
                apk_info: dict,
                separator: str = "_",
                errored_apps_list: list = None,
                skip_if_exists: bool = False) -> str | None:
    """
    Rename file and return new filename.

    :param file_path: Path to the file to rename.
    :param pattern: The pattern to rename to.
    :param apk_info: Dict containing the information of the APK/APKS file.
    :param separator: The separator to use for the replacing of spaces and invalid characters.
    :param errored_apps_list: List to store errored files.
    :param skip_if_exists: Whether to skip the renaming if output file exists.

    :return: The new name of the file, or the same name if `skip_if_exists` is `True` and the new filename already
     exists.
    """

    new_name = pattern

    if "%original_name%" in new_name:
        new_name = new_name.replace("%original_name%", apk_info["Original Name"].replace(" ", separator))

    if "%label%" in new_name:
        new_name = new_name.replace("%label%", apk_info[PACKAGE_LABEL].replace(" ", separator))
    if "%name%" in new_name:
        new_name = new_name.replace("%name%", apk_info[PACKAGE_LABEL].replace(" ", separator))
    if "%version%" in new_name:
        new_name = new_name.replace("%version%", apk_info[PACKAGE_VERSION_NAME].replace(" ", separator))
    if "%version_name%" in new_name:
        new_name = new_name.replace("%version_name%", apk_info[PACKAGE_VERSION_NAME].replace(" ", separator))
    if "%build%" in new_name:
        new_name = new_name.replace("%build%", apk_info[PACKAGE_VERSION_CODE].replace(" ", separator))
    if "%version_code%" in new_name:
        new_name = new_name.replace("%version_code%", apk_info[PACKAGE_VERSION_CODE].replace(" ", separator))
    if "%package%" in new_name:
        new_name = new_name.replace("%package%", apk_info[PACKAGE_NAME].replace(" ", separator))
    if "%package_name%" in new_name:
        new_name = new_name.replace("%package_name%", apk_info[PACKAGE_NAME].replace(" ", separator))
    if "%package_id%" in new_name:
        new_name = new_name.replace("%package_id%", apk_info[PACKAGE_NAME].replace(" ", separator))

    if "%min_sdk%" in new_name:
        new_name = new_name.replace("%min_sdk%", apk_info[PACKAGE_MIN_SDK].replace(" ", separator))
    if "%max_sdk%" in new_name:
        new_name = new_name.replace("%max_sdk%", apk_info[PACKAGE_MAX_SDK].replace(" ", separator))
    if "%target_sdk%" in new_name:
        new_name = new_name.replace("%target_sdk%", apk_info[PACKAGE_TARGET_SDK].replace(" ", separator))
    if "%compile_sdk%" in new_name:
        new_name = new_name.replace("%compile_sdk%", apk_info[PACKAGE_COMPILE_SDK].replace(" ", separator))

    if "%min_android_num%" in new_name:
        new_name = new_name.replace("%min_android_num%",
                                    translate_sdk(apk_info[PACKAGE_MIN_SDK], True).replace(" ", separator))
    if "%max_android_num%" in new_name:
        new_name = new_name.replace("%max_android_num%",
                                    translate_sdk(apk_info[PACKAGE_MAX_SDK], True).replace(" ", separator))
    if "%target_android_num%" in new_name:
        new_name = new_name.replace("%target_android_num%",
                                    translate_sdk(apk_info[PACKAGE_TARGET_SDK], True).replace(" ", separator))
    if "%compile_android_num%" in new_name:
        new_name = new_name.replace("%compile_android_num%",
                                    translate_sdk(apk_info[PACKAGE_COMPILE_SDK], True).replace(" ", separator))

    if "%min_android_name%" in new_name:
        new_name = new_name.replace("%min_android_name%",
                                    translate_sdk(apk_info[PACKAGE_MIN_SDK], False).replace(" ", separator))
    if "%max_android_name%" in new_name:
        new_name = new_name.replace("%max_android_name%",
                                    translate_sdk(apk_info[PACKAGE_MAX_SDK], False).replace(" ", separator))
    if "%target_android_name%" in new_name:
        new_name = new_name.replace("%target_android_name%",
                                    translate_sdk(apk_info[PACKAGE_TARGET_SDK], False).replace(" ", separator))
    if "%compile_android_name%" in new_name:
        new_name = new_name.replace("%compile_android_name%",
                                    translate_sdk(apk_info[PACKAGE_COMPILE_SDK], False).replace(" ", separator))

    if "%supported_screens%" in new_name:
        new_name = new_name.replace("%screens%",
                                    join_values(apk_info[PACKAGE_SUPPORTED_SCREENS]).replace(" ", separator))
    if "%screens%" in new_name:
        new_name = new_name.replace("%screens%",
                                    join_values(apk_info[PACKAGE_SUPPORTED_SCREENS]).replace(" ", separator))
    if "%supported_dpis%" in new_name:
        new_name = new_name.replace("%supported_dpis%",
                                    join_values(apk_info[PACKAGE_DENSITIES]).replace(" ", separator))
    if "%dpis%" in new_name:
        new_name = new_name.replace("%dpis%",
                                    join_values(apk_info[PACKAGE_DENSITIES]).replace(" ", separator))
    if "%supported_abis%" in new_name:
        new_name = new_name.replace("%supported_abis%",
                                    join_values(apk_info[PACKAGE_SUPPORTED_ABIS]).replace(" ", separator))
    if "%abis%" in new_name:
        new_name = new_name.replace("%abis%",
                                    join_values(apk_info[PACKAGE_SUPPORTED_ABIS]).replace(" ", separator))
    if "%supported_devices%" in new_name:
        new_name = new_name.replace("%supported_devices%",
                                    join_values(apk_info[PACKAGE_SUPPORTED_DEVICES]).replace(" ", separator))
    if "%devices%" in new_name:
        new_name = new_name.replace("%devices%",
                                    join_values(apk_info[PACKAGE_SUPPORTED_DEVICES]).replace(" ", separator))
    if "%supported_locales%" in new_name:
        new_name = new_name.replace("%supported_locales%",
                                    join_values(apk_info[PACKAGE_LOCALES]).replace(" ", separator))
    if "%locales%" in new_name:
        new_name = new_name.replace("%locales%",
                                    join_values(apk_info[PACKAGE_LOCALES]).replace(" ", separator))

    new_name = sanitize_name(name=new_name, separator=separator)

    new_name_ext = os.path.splitext(file_path)[1]

    old_name = os.path.splitext(os.path.basename(file_path))[0]
    if new_name == old_name:
        return file_path

    new_name = os.path.join(os.path.split(file_path)[0], new_name)

    new_new_name = new_name
    i = 1
    # str(i).zfill(pad_amount)

    if skip_if_exists and os.path.exists(new_name + new_name_ext):
        return file_path

    while os.path.exists(new_new_name + new_name_ext):
        new_new_name = new_name + separator + str(i).zfill(2)
        i += 1

    try:
        os.rename(file_path, new_new_name + new_name_ext)
    except PermissionError as e:
        print(Fore.RED + "ERROR: Couldn't rename {}. Permission denied.".format(file_path), end="\n\n")
        print(e, end="\n\n")
        if errored_apps_list is not None:
            errored_apps_list.append(file_path)
        return None

    sig_ext = ".idsig"

    if os.path.exists(file_path + sig_ext):
        try:
            os.rename(file_path + sig_ext, new_new_name + new_name_ext + sig_ext)
        except PermissionError as e:
            print(Fore.RED + "ERROR: Couldn't rename {}. Permission denied.".format(file_path + sig_ext), end="\n\n")
            print(e, end="\n\n")
            if errored_apps_list is not None:
                errored_apps_list.append(file_path + sig_ext)
            return None

    return new_new_name + new_name_ext


def sanitize_name(name: str,
                  separator: str) -> str:

    illegal_characters = ("\\",
                          "/",
                          ":",
                          "*",
                          "?",
                          "\"",
                          "<",
                          ">",
                          "|",
                          "\t",
                          "\n")

    for character in illegal_characters:
        name = name.replace(character, separator)

    regex_pattern = r"(\(\)|{}|\[\])"

    name = re.sub(separator + regex_pattern, "", name)
    name = re.sub(regex_pattern + separator, "", name)
    name = re.sub(regex_pattern, "", name)

    return name


def join_values(list_values: list) -> str:
    new_name = ""

    if len(list_values) != 0:
        for value in list_values:
            new_name += value + ","

        if new_name.endswith(","):
            new_name = new_name[:-1]

    return new_name


def translate_sdk(sdk: str,
                  number: bool) -> str:

    if sdk == "":
        return ""

    stream = open(os.path.join(get_program_dir(), "sdk_names.json"), "r", encoding="utf_8")
    sdk_names = json.load(stream)

    sdk = "SDK-" + sdk

    if number:
        new_sdk_name = sdk_names[sdk][0]
    else:
        new_sdk_name = sdk_names[sdk][1]

    return new_sdk_name


def get_info(app_file_path: str,
             build_tools_path: str = None,
             errored_apps_list: list = None,
             apk_info: dict = None) -> dict:
    """
    | Get information from an APK or APKS file.
    |
    | Available keys are:

    * Supported Devices: `list`
    * Supported Screens: `list`
    * Densities: `list`
    * Supported ABIs: `list`
    * Locales: `list`
    * Label: `str`
    * Package Name: `str`
    * Version Code: `str`
    * Version Name: `str`
    * Compile SDK: `str`
    * Minimum SDK: `str`
    * Maximum SDK: `str`
    * Target SDK: `str`

    :param app_file_path: Path to an APK file
    :param build_tools_path: Path to build-tools directory of the Android SDK. Only *aapt* and *aapt2* are used from
     this directory unless `sign_apk` is `True` in which case *apksigner* will be used too. If not supplied, they will
     be searched for in **PATH**.
    :param errored_apps_list: List to store errored files. If not supplied, no errored files are stored.
    :param apk_info: Dictionary to store the APK information. If not supplied, a new dict is created.

    :return: Dictionary containing the information about the APK/APKS file.
    """

    if apk_info is None:
        apk_info = {}

    is_apks = False
    apks_content = []

    temp_path = os.path.join(tempfile.gettempdir(), str(os.getpid()))

    if os.path.splitext(app_file_path)[1].lower() == APKS_EXTENSION:
        temp_path = pre_process_apks(apks_file=app_file_path, temp_path=temp_path)
        if temp_path is None:
            return {}
        is_apks = True

    app_directory = os.path.dirname(app_file_path)
    app_filename = os.path.basename(app_file_path)

    apk_info["Original Name"] = os.path.splitext(app_filename)[0]

    if is_apks:
        apks_content = sorted(os.listdir(temp_path))

    badging_content = badging(app_file_path=app_file_path,
                              is_apks=is_apks,
                              apks_content=apks_content,
                              build_tools_path=build_tools_path,
                              errored_apps_list=errored_apps_list,
                              temp_path=temp_path)

    try:
        shutil.rmtree(temp_path)
    except FileNotFoundError:
        pass
    except PermissionError as e:
        print(Fore.RED + "\tERROR: Couldn't remove the temp directory for {}. Permission denied.".format(app_filename),
              end="\n\n")
        print(e, end="\n\n")
        sys.exit(1)

    if badging_content is None:
        return {}

    apk_info = parse_badging(badging_content=badging_content,
                             apk_info=apk_info)

    # Essential information, if we couldn't get this info then something is either wrong with this program or the
    # APK file.
    if len(apk_info[PACKAGE_NAME]) == 0 or len(apk_info[PACKAGE_VERSION_NAME]) == 0 or len(
            apk_info[PACKAGE_VERSION_CODE]) == 0:
        basename = os.path.basename(app_filename)
        print(Fore.RED + "\tERROR: We couldn't extract information from {}, please report this.".format(basename),
              end="\n\n")
        if errored_apps_list is not None:
            errored_apps_list.append(app_file_path)
        return {}

    return apk_info


def badging(app_file_path: str,
            is_apks: bool,
            apks_content: list[str],
            temp_path: str,
            build_tools_path: str = None,
            errored_apps_list: list = None) -> str | None:

    output = ""

    # TODO: Add option to look in the ANDROID_HOME ENV VAR

    aapt_bin_path = shutil.which("aapt")
    aapt2_bin_path = shutil.which("aapt2")

    if build_tools_path is not None:
        aapt_bin_path = os.path.join(build_tools_path[0], "aapt")
        aapt2_bin_path = os.path.join(build_tools_path[0], "aapt2")

    orig_badging_command = [aapt_bin_path,
                            "d",
                            "--include-meta-data",
                            "badging"]
    orig_badging_command_alt = [aapt2_bin_path,
                                "d",
                                "badging",
                                "--include-meta-data"]

    error_text = "Illegal byte sequence"

    if is_apks:
        for apk_file in apks_content:
            apk_file = os.path.join(temp_path, apk_file)
            if os.path.splitext(apk_file)[1].lower() == APK_EXTENSION:
                try:
                    badging_command = copy.deepcopy(orig_badging_command)
                    badging_command.append(apk_file)
                    output += subprocess.check_output(args=badging_command,
                                                      encoding="utf_8",
                                                      errors="replace").strip() + "\n"
                except subprocess.CalledProcessError:
                    pass

        if output == "" or error_text in output:
            output = ""  # reset value
            for apk_file in apks_content:
                apk_file = os.path.join(temp_path, apk_file)
                if os.path.splitext(apk_file)[1].lower() == APK_EXTENSION:
                    try:
                        badging_command_alt = copy.deepcopy(orig_badging_command_alt)
                        badging_command_alt.append(apk_file)
                        output += subprocess.check_output(args=badging_command_alt,
                                                          encoding="utf_8",
                                                          errors="replace").strip() + "\n"
                    except subprocess.CalledProcessError:
                        pass
    else:
        try:
            badging_command = copy.deepcopy(orig_badging_command)
            badging_command.append(app_file_path)
            output = subprocess.check_output(args=badging_command,
                                             encoding="utf_8",
                                             errors="replace").strip()
        except subprocess.CalledProcessError:
            pass

        if output == "" or error_text in output:
            try:
                badging_command_alt = copy.deepcopy(orig_badging_command_alt)
                badging_command_alt.append(app_file_path)
                output = subprocess.check_output(args=badging_command_alt,
                                                 encoding="utf_8",
                                                 errors="replace").strip()
            except subprocess.CalledProcessError:
                pass

    if output == "" or error_text in output:
        if errored_apps_list is not None:
            errored_apps_list.append(app_file_path)
        print(Fore.RED + "\tERROR: There was an error getting the badge information for {}".format(app_file_path),
              end="\n\n")
        return None
    else:
        return output


def parse_badging(badging_content: str,
                  apk_info: dict) -> dict:

    badging_lines = badging_content.splitlines()

    any_density = False

    apk_info[PACKAGE_SUPPORTED_DEVICES] = ["Android"]
    apk_info[PACKAGE_SUPPORTED_SCREENS] = []
    apk_info[PACKAGE_DENSITIES] = []
    apk_info[PACKAGE_SUPPORTED_ABIS] = []
    apk_info[PACKAGE_LOCALES] = []
    apk_info[PACKAGE_LABEL] = ""
    apk_info[PACKAGE_NAME] = ""
    apk_info[PACKAGE_VERSION_CODE] = ""
    apk_info[PACKAGE_VERSION_NAME] = ""
    apk_info[PACKAGE_COMPILE_SDK] = ""
    apk_info[PACKAGE_MIN_SDK] = ""
    apk_info[PACKAGE_MAX_SDK] = ""
    apk_info[PACKAGE_TARGET_SDK] = ""

    if "leanback-launchable-activity" in badging_content:
        apk_info[PACKAGE_SUPPORTED_DEVICES].append("Android TV")

    if "com.google.android.gms.car.application" in badging_content:
        apk_info[PACKAGE_SUPPORTED_DEVICES].append("Android Auto")

    if "android.hardware.type.watch" in badging_content:
        apk_info[PACKAGE_SUPPORTED_DEVICES].append("Wear OS")

    for line in badging_lines:
        line = line.strip()

        split_values = line.split(":", maxsplit=1)

        key = split_values[0].strip()

        if len(split_values) == 1:
            value = ""
        else:
            value = split_values[1].strip()

        if key == "application-label":
            get_label(apk_info, value)
        elif key == "package":
            get_package_info(apk_info, value)
        elif key == "sdkVersion" and apk_info.get(PACKAGE_MIN_SDK, "") == "":
            get_sdk_version(apk_info, value)
        elif key == "maxSdkVersion" and apk_info.get(PACKAGE_MAX_SDK, "") == "":
            get_max_sdk_version(apk_info, value)
        elif key == "targetSdkVersion" and apk_info.get(PACKAGE_TARGET_SDK, "") == "":
            get_target_sdk_version(apk_info, value)
        elif key == "supports-screens":
            get_supported_screens(apk_info, value)
        elif key == "supports-any-density":
            if value.replace("'", "") == "true":
                any_density = True
        elif key == "densities":
            get_densities(apk_info, value)
        elif key == "native-code" or key == "alt-native-code":
            get_supported_abis(apk_info, value)
        elif key == "locales":
            get_supported_locales(apk_info, value)

    rename_densities(apk_info, any_density)

    return apk_info


def pre_process_apks(apks_file: str,
                     temp_path: str) -> str | None:
    """
    Pre-process APKS files, extracting their content and saving them in a temporary directory returning the path to
    that temporary directory.

    :param apks_file: APKS file to pre-process.
    :param temp_path: Main temporary path where to store the temporary directory and content of this APKS file.

    :return: Path to the new temporary directory or None if an error occurred.
    """

    new_temp_path = os.path.join(temp_path, os.path.splitext(os.path.basename(apks_file))[0].strip())

    try:
        os.makedirs(new_temp_path)
    except FileExistsError:
        pass

    import zipfile

    try:
        zipfile.ZipFile(apks_file).extractall(new_temp_path)
    except (zipfile.BadZipFile, PermissionError) as e:
        print(e, end="\n\n")
        return None

    return new_temp_path


def convert_to_apk(apks_file: str,
                   apk_editor_path: str,
                   sign_apk: bool = False,
                   key_file: str = None,
                   cert_file: str = None,
                   certificate_password: str = None,
                   build_tools_path: str = None) -> bool:
    """
    Convert an APKS file to APK, optionally signing it.

    :param apks_file: Path to the APKS file.
    :param apk_editor_path: Path to APKEditor JAR file.
    :param sign_apk: Whether to sign the resulting APK file.
    :param key_file: Path to the key file used to sign the resulting APK file.
    :param cert_file: Path to the certificate file used to sign the resulting APK file.
    :param certificate_password: Certificate's password.
    :param build_tools_path: Path to build-tools directory of the Android SDK. Only *apksigner* is used from this path,
        if not specified **PATH** is used.

    :return: *True* if the conversion was successful and *False* otherwise.

    """

    print(Fore.GREEN + "\tConverting {} to .APK...".format(os.path.basename(apks_file)), end="\n\n")

    convert_command_orig = ["java",
                            "-jar",
                            apk_editor_path,
                            "m",
                            "-i",
                            "",
                            "-o",
                            "",
                            "-f"]

    if sign_apk:
        apk_path_unsigned = os.path.splitext(apks_file)[0] + "_unsigned.apk"
    else:
        apk_path_unsigned = os.path.splitext(apks_file)[0] + APK_EXTENSION

    try:
        old_app_stats = os.lstat(apks_file)
    except PermissionError:
        print(Fore.YELLOW + "\tWARNING: Couldn't get stats of the APKS file, check permissions."
                            " Old timestamps wont be restored.", end="\n\n")
        old_app_stats = None

    try:
        convert_command = copy.deepcopy(convert_command_orig)
        convert_command[5] = apks_file
        convert_command[7] = apk_path_unsigned
        subprocess.run(convert_command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print(Fore.RED + "\tERROR: There was an error converting {} to .apk".format(os.path.basename(apks_file)),
              end="\n\n")
        print(e, end="\n\n")
        if os.path.exists(apk_path_unsigned):
            try:
                os.remove(apk_path_unsigned)
            except PermissionError as e:
                print(Fore.RED + "\t\tERROR: Couldn't remove unfinished APK file. Permission denied.", end="\n\n")
                print(e, end="\n\n")
        return False

    if sign_apk:
        apk_path_signed = os.path.splitext(apks_file)[0] + APK_EXTENSION

        if not sign_apk_file(key_file=key_file,
                             cert_file=cert_file,
                             apk_path_unsigned=apk_path_unsigned,
                             apk_path_signed=apk_path_signed,
                             certificate_password=certificate_password,
                             build_tools_path=build_tools_path):
            return False

        if old_app_stats is not None:
            restore_dates(old_app_stats=old_app_stats,
                          apk_file=apk_path_signed)
    elif old_app_stats is not None:
        restore_dates(old_app_stats=old_app_stats,
                      apk_file=apk_path_unsigned)

    try:
        os.remove(apks_file)
    except PermissionError as e:
        print(Fore.RED + "\tERROR: Error deleting file {}. Permission denied".format(os.path.basename(apks_file)),
              end="\n\n")
        print(e, end="\n\n")

    if sign_apk:
        try:
            os.remove(apk_path_unsigned)
        except PermissionError as e:
            print(Fore.RED + "\tERROR: Error deleting file {}. Permission denied".format(os.path.basename(
                    apk_path_unsigned)), end="\n\n")
            print(e, end="\n\n")

    print(Fore.GREEN + "\tDone converting {}.".format(os.path.basename(apks_file)), end="\n\n")
    return True


def sign_apk_file(key_file: str,
                  cert_file: str,
                  apk_path_unsigned: str,
                  apk_path_signed: str,
                  certificate_password: str = None,
                  build_tools_path: str = None) -> bool:
    """
    Sign APK file with the provided certificate.

    :param key_file: Path to the key file.
    :param cert_file: Path to the certificate file.
    :param apk_path_unsigned: Path to the APK file to sign.
    :param apk_path_signed: Path to the output file.
    :param certificate_password: Password for the certificate file.
    :param build_tools_path: Path to the build-tools directory of the Android SDK.

    :returns: True if signing was successful, False otherwise.
    """

    if build_tools_path is not None:
        apksigner_path = os.path.join(build_tools_path[0], "apksigner")
    else:
        apksigner_path = shutil.which("apksigner")

    if certificate_password is not None:
        sign_command_orig = [apksigner_path,
                             "sign",
                             "--key",
                             key_file,
                             "--cert",
                             cert_file,
                             "--key-pass",
                             "pass:" + certificate_password,
                             "--in",
                             "",
                             "--out",
                             ""]
    else:
        sign_command_orig = [apksigner_path,
                             "sign",
                             "--key",
                             key_file,
                             "--cert",
                             cert_file,
                             "--key-pass",
                             "pass:",
                             "--in",
                             "",
                             "--out",
                             ""]

    sign_command = copy.deepcopy(sign_command_orig)
    sign_command[9] = apk_path_unsigned
    sign_command[11] = apk_path_signed

    try:
        subprocess.run(sign_command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print(Fore.RED + "\tERROR: There was an error signing {}, aborting conversion...",
              format(apk_path_unsigned),
              end="\n\n")
        print(e, end="\n\n")
        return False
    except Exception as e:
        print(e, end="\n\n")
        return False

    return True


def restore_dates(old_app_stats: os.stat_result,
                  apk_file: str) -> None:
    setctime = None
    if platform.system() == "Windows":
        try:
            from win32_setctime import setctime
        except ImportError:
            setctime = None
            print(Fore.YELLOW + "\tWARNING: win32_setctime module is not installed,"
                                " creation times wont be restored for the converted APK files.", end="\n\n")

    try:
        os.utime(apk_file, (old_app_stats.st_atime, old_app_stats.st_mtime))
    except PermissionError as e:
        print(Fore.YELLOW + "\tWARNING: Couldn't restore old timestamps. Permission denied.", end="\n\n")
        print(e, end="\n\n")

    if platform.system() == "Windows" and setctime is not None:
        try:
            setctime(apk_file, old_app_stats.st_ctime)
        except PermissionError as e:
            print(Fore.YELLOW + "\tWARNING: Couldn't restore old creation date. Permission denied.", end="\n\n")
            print(e, end="\n\n")


def get_label(apk_info: dict,
              value: str) -> None:
    if value.replace("'", "").strip() != "":
        apk_info[PACKAGE_LABEL] = value.replace("'", "")


def get_package_info(apk_info: dict,
                     value: str) -> None:
    if apk_info.get(PACKAGE_NAME, "") == "":
        try:
            apk_info[PACKAGE_NAME] = re.search(r"(?:^|\s)name='([^']*)'", value).group(1)
        except (AttributeError, IndexError):
            pass
    if apk_info.get(PACKAGE_VERSION_CODE, "") == "":
        try:
            apk_info[PACKAGE_VERSION_CODE] = re.search(r"(?:^|\s)versionCode='([^']*)'", value).group(1)
        except (AttributeError, IndexError):
            pass
    if apk_info.get(PACKAGE_VERSION_NAME, "") == "":
        try:
            apk_info[PACKAGE_VERSION_NAME] = re.search(r"(?:^|\s)versionName='([^']*)'", value).group(1)
        except (AttributeError, IndexError):
            pass
    if apk_info.get(PACKAGE_COMPILE_SDK, "") == "":
        try:
            apk_info[PACKAGE_COMPILE_SDK] = re.search(r"(?:^|\s)compileSdkVersion='([^']*)'", value).group(1)
        except (AttributeError, IndexError):
            pass


def get_sdk_version(apk_info: dict,
                    value: str) -> None:
    if value.replace("'", "").strip() != "":
        apk_info[PACKAGE_MIN_SDK] = value.replace("'", "")


def get_max_sdk_version(apk_info: dict,
                        value: str) -> None:
    if value.replace("'", "").strip() != "":
        apk_info[PACKAGE_MAX_SDK] = value.replace("'", "")


def get_target_sdk_version(apk_info: dict,
                           value: str) -> None:
    if value.replace("'", "").strip() != "":
        apk_info[PACKAGE_TARGET_SDK] = value.replace("'", "")


def get_supported_screens(apk_info: dict,
                          value: str) -> None:
    if value.replace("'", "").strip() != "":
        value = value.replace("'", "").split()

        if len(apk_info[PACKAGE_SUPPORTED_SCREENS]) != 0:
            for screen in value:
                if screen not in apk_info[PACKAGE_SUPPORTED_SCREENS]:
                    apk_info[PACKAGE_SUPPORTED_SCREENS].append(screen)
        else:
            for screen in value:
                apk_info[PACKAGE_SUPPORTED_SCREENS].append(screen)


def get_supported_locales(apk_info: dict,
                          value: str) -> None:
    if value.replace("'", "").strip() != "":
        value = value.replace("'", "").split()

        if len(apk_info[PACKAGE_LOCALES]) != 0:
            for locale in value:
                if value == "--_--" or value == "---":
                    continue
                if locale not in apk_info[PACKAGE_LOCALES]:
                    apk_info[PACKAGE_LOCALES].append(locale)
        else:
            for locale in value:
                if value == "'--_--'" or value == "'---'":
                    continue
                apk_info[PACKAGE_LOCALES].append(locale)


def get_densities(apk_info: dict,
                  value: str) -> None:
    if value.replace("'", "").strip() != "":
        value = value.replace("'", "").split()

        if len(apk_info[PACKAGE_DENSITIES]) != 0:
            for density in value:
                if density not in apk_info[PACKAGE_DENSITIES]:
                    apk_info[PACKAGE_DENSITIES].append(density)
        else:
            for density in value:
                apk_info[PACKAGE_DENSITIES].append(density)


def get_supported_abis(apk_info: dict,
                       value: str) -> None:
    if value.replace("'", "").strip() != "":
        value = value.replace("'", "").split()

        if len(apk_info[PACKAGE_SUPPORTED_ABIS]) != 0:
            for abi in value:
                if abi not in apk_info[PACKAGE_SUPPORTED_ABIS]:
                    apk_info[PACKAGE_SUPPORTED_ABIS].append(abi)
        else:
            for abi in value:
                apk_info[PACKAGE_SUPPORTED_ABIS].append(abi)


def rename_densities(apk_info: dict,
                     any_density: bool) -> None:
    densities_dict = {
        "120": "ldpi",
        "160": "mdpi",
        "240": "hdpi",
        "320": "xhdpi",
        "480": "xxhdpi",
        "640": "xxxhdpi",
        "65534": "anydpi",
        "65535": "nodpi",
        "-1": "undefineddpi"
    }

    for x in densities_dict.keys():
        if x in apk_info[PACKAGE_DENSITIES]:
            index = apk_info[PACKAGE_DENSITIES].index(x)
            apk_info[PACKAGE_DENSITIES][index] = densities_dict[x]

    if any_density and "anydpi" not in apk_info[PACKAGE_DENSITIES]:
        apk_info[PACKAGE_DENSITIES].append("anydpi")


if __name__ == "__main__":
    main()
