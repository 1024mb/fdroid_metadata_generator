"""
Test APK files and recompile them if CRC errors are detected.
"""

import argparse
import copy
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from typing import Optional

from colorama import Fore, init

from common import get_program_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path",
                        help="Path to a directory or a single APK file.",
                        required=True,
                        nargs=1)
    parser.add_argument("--build-tools-path",
                        help="Path to aapt and aapt2 executables. By default uses the ones located in PATH.",
                        nargs=1)
    parser.add_argument("--apktool-path",
                        help="Path to apktool. By default uses apktool.jar in the current working directory.",
                        nargs=1)

    args = parser.parse_args()

    init(autoreset=True)

    path = os.path.abspath(args.path[0])

    if args.build_tools_path is not None:
        build_tools_path = args.build_tools_path[0]

        if not os.path.exists(build_tools_path):
            print(Fore.RED + "ERROR: Build tools path doesn't exist.")
            sys.exit(1)

        if not os.path.isdir(build_tools_path):
            print(Fore.RED + "ERROR: Build Tools Path is not a directory.")
            sys.exit(1)
    else:
        build_tools_path = args.build_tools_path

        if shutil.which("aapt") is None:
            print(Fore.RED + "ERROR: aapt was not found in PATH.")
            sys.exit(1)

    if args.apktool_path is None:
        apktool_path = os.path.join(get_program_dir(), "apktool.jar")
    else:
        apktool_path = args.apktool_path[0]

    if shutil.which("java") is None:
        print(Fore.RED + "ERROR: Java is missing from PATH.")
        sys.exit(1)

    if not os.path.exists(path):
        print(Fore.RED + "ERROR: Supplied path doesn't exist.")
        sys.exit(1)

    if not os.path.isfile(apktool_path):
        print(Fore.RED + "ERROR: Invalid Apktool path.")
        sys.exit(1)

    if os.path.isfile(path) and os.path.splitext(path)[1].lower() != ".apk":
        print(Fore.RED + "ERROR: Specified file path is not an APK file (needs .apk extension).")
        sys.exit(1)

    start_processing(path=path,
                     apktool_path=apktool_path,
                     build_tools_path=build_tools_path)


def start_processing(path: str,
                     apktool_path: str,
                     build_tools_path: Optional[str] = None) -> None:
    """
    Start processing of `path` and check files for CRC errors, if none are found, skip the file otherwise recompile it.

    :param path: Path to process, it can be a directory or a file.
    :param apktool_path: Path to the Apktool jar file.
    :param build_tools_path: Path to build tools from the Android SDK. Only aapt is used. By default, the one in PATH
     is used.
    """
    command_decompile_orig = [
        "java",
        "-jar",
        apktool_path,
        "decode",
        "--force",
        "--output",
        ""
    ]

    command_compile_orig = [
        "java",
        "-jar",
        apktool_path,
        "build",
        "--force-all",
        "--output",
        ""
    ]

    process_path(path=path,
                 command_decompile_orig=command_decompile_orig,
                 command_compile_orig=command_compile_orig,
                 build_tools_path=build_tools_path)


def process_path(path: str,
                 command_decompile_orig: list,
                 command_compile_orig: list,
                 build_tools_path: Optional[str]) -> None:

    if os.path.isdir(path):
        command_decompile_orig.insert(6, os.path.join(path, "decompiled_apk"))
        command_compile_orig.append(os.path.join(path, "decompiled_apk"))

        process_directory(path=path,
                          command_decompile_orig=command_decompile_orig,
                          command_compile_orig=command_compile_orig,
                          build_tools_path=build_tools_path)
    elif os.path.isfile(path):
        command_decompile_orig.insert(6, os.path.join(os.path.split(path)[0], "decompiled_apk"))
        command_compile_orig.append(os.path.join(os.path.join(os.path.split(path)[0], "decompiled_apk")))

        process_file(path=os.path.split(path)[0],
                     command_decompile_orig=command_decompile_orig,
                     command_compile_orig=command_compile_orig,
                     build_tools_path=build_tools_path,
                     apk_file=path,
                     apk_basename=os.path.basename(path))


def process_directory(path: str,
                      command_decompile_orig: list,
                      command_compile_orig: list,
                      build_tools_path: Optional[str]) -> None:
    processed_files = []

    for item in os.listdir(path):
        apk_file = os.path.join(path, item)

        process_file(path=path,
                     command_decompile_orig=command_decompile_orig,
                     command_compile_orig=command_compile_orig,
                     build_tools_path=build_tools_path,
                     apk_file=apk_file,
                     apk_basename=item,
                     processed_files=processed_files)

    if len(processed_files) != 0:
        print(Fore.GREEN + "Processed {} files:".format(len(processed_files)))
        for file in processed_files:
            print(Fore.GREEN + "\t" + file)


def process_file(path: str,
                 command_decompile_orig: list,
                 command_compile_orig: list,
                 build_tools_path: Optional[str],
                 apk_file: str,
                 apk_basename: str,
                 processed_files: Optional[list] = None) -> None:
    if os.path.isfile(apk_file) and apk_basename.lower().endswith(".apk"):
        if check_apk(apk_path=apk_file):
            print(Fore.BLUE + "Skipping OK file: {}".format(apk_basename))
            return

        print(Fore.GREEN + "Processing {}...".format(apk_basename))

        recompiled_apk_path = os.path.join(path, os.path.splitext(apk_basename)[0] + "_recomp.apk")

        command_decompile = copy.deepcopy(command_decompile_orig)
        command_decompile[7] = apk_file

        command_compile = copy.deepcopy(command_compile_orig)
        command_compile[6] = recompiled_apk_path

        if build_tools_path is not None:
            command_compile.insert(4, ["--aapt", build_tools_path])

        if not decompile_apk(command_decompile=command_decompile,
                             working_path=path):
            return

        if not recompile_apk(command_compile=command_compile,
                             recompiled_apk_path=recompiled_apk_path):
            return

        shutil.rmtree(os.path.join(path, "decompiled_apk"))

        restore_time(apk_file=apk_file,
                     recompiled_apk_path=recompiled_apk_path)

        os.remove(apk_file)
        os.rename(recompiled_apk_path, apk_file)

        if processed_files is not None:
            processed_files.append(apk_basename)

        print(Fore.GREEN + "Finished processing {}".format(apk_basename))


def check_apk(apk_path: str) -> bool:
    try:
        if zipfile.ZipFile(apk_path).testzip() is not None:
            return False
        else:
            return True
    except zipfile.BadZipfile:
        return False


def decompile_apk(command_decompile: list,
                  working_path: str) -> bool:
    try:
        subprocess.run(command_decompile, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError as e:
        print(e)
        if os.path.exists(os.path.join(working_path, "decompiled_apk")):
            shutil.rmtree(os.path.join(working_path, "decompiled_apk"))
        return False


def recompile_apk(command_compile: list,
                  recompiled_apk_path: str) -> bool:
    try:
        subprocess.run(command_compile, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        return True
    except subprocess.CalledProcessError as e:
        print(e)
        if os.path.exists(recompiled_apk_path):
            os.remove(recompiled_apk_path)
        return False


def restore_time(apk_file: str,
                 recompiled_apk_path: str) -> None:
    orig_stats = os.lstat(apk_file)

    if platform.system() == "Windows":
        try:
            from win32_setctime import setctime

            setctime(recompiled_apk_path, orig_stats.st_ctime)
        except ImportError:
            pass

    os.utime(recompiled_apk_path, (orig_stats.st_atime, orig_stats.st_mtime))


if __name__ == "__main__":
    main()
