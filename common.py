import mimetypes
import os
import re
import sys
from http.cookiejar import MozillaCookieJar
from time import sleep
from typing import Literal, Any, TypeGuard

import requests
from colorama import Fore
from pydantic import BaseModel, Field, field_validator
from requests import HTTPError


class Locales(BaseModel):
    Play_Store: list[str]
    Apkcombo_Store: list[str]


class RegexPatterns(BaseModel):
    author_name_pattern: Literal[""] | re.Pattern[str]
    author_email_pattern: Literal[""] | re.Pattern[str]
    name_pattern: Literal[""] | re.Pattern[str]
    website_pattern: Literal[""] | re.Pattern[str]
    category_pattern: Literal[""] | re.Pattern[str]
    summary_pattern: Literal[""] | re.Pattern[str]
    summary_pattern_alt: Literal[""] | re.Pattern[str]
    description_pattern: Literal[""] | re.Pattern[str]
    screenshot_pattern: Literal[""] | re.Pattern[str]
    screenshot_pattern_alt: Literal[""] | re.Pattern[str]
    icon_pattern: Literal[""] | re.Pattern[str]
    icon_pattern_alt: Literal[""] | re.Pattern[str]
    gitlab_repo_id_pattern: Literal[""] | re.Pattern[str]
    ads_pattern: Literal[""] | re.Pattern[str]
    inapp_purchases_pattern: Literal[""] | re.Pattern[str]
    tracking_pattern: Literal[""] | re.Pattern[str]


class StoreRegexPatterns(BaseModel):
    Template: RegexPatterns
    Play_Store: RegexPatterns
    Amazon_Store: RegexPatterns
    Apkcombo_Store: RegexPatterns


class SportCategoryPattern(BaseModel):
    Play_Store: str
    Amazon_Store: str
    Apkcombo_Store: str


class AppStoreRegexPatterns(BaseModel):
    Play_Store: list[re.Pattern[str]]
    Amazon_Store: list[re.Pattern[str]]
    Apkcombo_Store: list[re.Pattern[str]]


class AppStoreStringPatterns(BaseModel):
    Play_Store: list[str]
    Amazon_Store: list[str]
    Apkcombo_Store: list[str]


class PageErrorPattern(BaseModel):
    Not_Found: AppStoreRegexPatterns
    Robot: AppStoreRegexPatterns
    Redirection: AppStoreStringPatterns


class AppData(BaseModel):
    Licenses: list[str]
    App_Categories: dict[str, str]
    Game_Categories: dict[str, str]
    Locales: Locales
    Icon_Relations: dict[str, str]
    Regex_Patterns: StoreRegexPatterns
    Sport_Category_Pattern: SportCategoryPattern
    User_Agent: str = Field(default="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0")
    Page_Error_Pattern: PageErrorPattern


class ExtensionUnknown(Exception):
    pass


AndroidDeviceType = Literal["Android", "Android TV", "Android Auto", "Wear OS"]
AndroidDensityName = Literal[
    "ldpi", "mdpi", "tvdpi", "hdpi", "xhdpi", "xxhdpi",
    "xxxhdpi", "anydpi", "nodpi", "undefineddpi"
]
AndroidDensityNumber = Literal[120, 160, 213, 240, 320, 480, 640, 65534, 65535, -1]
AndroidScreenType = Literal["small", "normal", "large", "xlarge"]
ABI = Literal["x86", "x86_64", "armeabi-v7a", "arm64-v8a", "armeabi", "mips", "mips64"]

ALL_ABIS: tuple[ABI, ...] = ("x86", "x86_64", "armeabi-v7a", "arm64-v8a", "armeabi", "mips", "mips64")
ALL_DENSITY_NUMBERS: tuple[AndroidDensityNumber, ...] = (120, 160, 213, 240, 320, 480, 640, 65534, 65535, -1)
ALL_DENSITY_NAMES: tuple[AndroidDensityName, ...] = ("ldpi", "mdpi", "tvdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi",
                                                     "anydpi", "nodpi", "undefineddpi")
ALL_DEVICE_TYPES: tuple[AndroidDeviceType, ...] = ("Android", "Android TV", "Android Auto", "Wear OS")
ALL_SCREEN_TYPES: tuple[AndroidScreenType, ...] = ("small", "normal", "large", "xlarge")


class _ApkInfo(BaseModel, validate_assignment=True):
    OriginalName: str | None = None
    PackageName: str | None = None
    Label: str | None = None
    VersionName: str | None = None
    VersionCode: int | None = None
    MinimumSDK: int | None = None
    MaximumSDK: int | None = None
    TargetSDK: int | None = None
    CompileSDK: int | None = None
    SupportedScreens: list[AndroidScreenType] = Field(default_factory=list)
    SupportedABIs: list[ABI] = Field(default_factory=list)
    SupportedDevices: list[AndroidDeviceType] = Field(default_factory=lambda: list(("Android",)))
    Densities: list[AndroidDensityName] = Field(default_factory=list)
    Locales: list[str] = Field(default_factory=list)

    def __setattr__(self,
                    name,
                    value):
        current_value = getattr(self, name, None)

        if current_value is None:
            return super().__setattr__(name, value)

        if isinstance(current_value, list) and isinstance(value, list):
            merged_list = current_value.copy()

            for item in value:
                if item not in merged_list:
                    merged_list.append(item)

            return super().__setattr__(name, merged_list)

        if isinstance(current_value, (str, int)):
            return None

        return super().__setattr__(name, value)

    @field_validator("OriginalName", "PackageName", "Label", "VersionName", mode="after")
    @classmethod
    def empty_string_to_none(cls,
                             value: str) -> str | None:
        if value == "":
            return None
        else:
            return value


class ApkInfo(_ApkInfo):
    OriginalName: str
    PackageName: str
    Label: str | None
    VersionName: str
    VersionCode: int
    MinimumSDK: int | None
    MaximumSDK: int | None
    TargetSDK: int | None
    CompileSDK: int | None
    SupportedScreens: list[str] = Field(default_factory=list)
    SupportedABIs: list[ABI] = Field(default_factory=list)
    SupportedDevices: list[AndroidDeviceType] = Field(default_factory=lambda: list(("Android",)))
    Densities: list[AndroidDensityName] = Field(default_factory=list)
    Locales: list[str] = Field(default_factory=list)


SupportedStore = Literal["Play_Store", "Amazon_Store", "Apkcombo_Store"]
FailType = Literal["Not_Found", "Robot", "Redirection", ""]

DENSITIES_MAPPING: dict[AndroidDensityNumber, AndroidDensityName] = {
    120: "ldpi",
    160: "mdpi",
    213: "tvdpi",
    240: "hdpi",
    320: "xhdpi",
    480: "xxhdpi",
    640: "xxxhdpi",
    65534: "anydpi",
    65535: "nodpi",
    -1: "undefineddpi"
}


def get_program_dir() -> str:
    try:
        # noinspection PyUnresolvedReferences
        return os.path.abspath(__compiled__.containing_dir)
    except NameError:
        return os.path.abspath(os.path.dirname(sys.argv[0]))


def get_page_content(url: str,
                     app_data: AppData,
                     package_name: str,
                     store_name: SupportedStore,
                     language: str,
                     alt_language: str,
                     cookie_file: str | None = None) -> str | None:
    wait_time = 30
    resp_content: str | None = None
    fail_type: FailType = ""

    not_found_patterns: list[re.Pattern[str]] = getattr(app_data.Page_Error_Pattern.Not_Found, store_name)
    robot_patterns: list[re.Pattern[str]] = getattr(app_data.Page_Error_Pattern.Robot, store_name)
    redirection_patterns: list[str] = getattr(app_data.Page_Error_Pattern.Redirection, store_name)

    regex_pattern_tuple: tuple[tuple[list[re.Pattern[str]], FailType], ...] = ((not_found_patterns, "Not_Found"),
                                                                               (robot_patterns, "Robot"))

    session = requests.Session()
    session.headers = {
        "User-Agent": app_data.User_Agent,
        "Accept-Language": language + "," + alt_language
    }

    if cookie_file is not None:
        cookie_jar = MozillaCookieJar(cookie_file)
        # noinspection PyTypeChecker
        session.cookies = cookie_jar
        # noinspection PyUnresolvedReferences
        session.cookies.load()

    for _ in range(1, 3):
        try:
            resp = session.get(url, allow_redirects=True)
            resp.raise_for_status()
            resp_content = resp.content.decode(encoding="utf_8", errors="replace")

            failed = False
            for pattern_list, reason in regex_pattern_tuple:
                if failed:
                    break

                for pattern in pattern_list:
                    if pattern.search(resp_content) is not None:
                        failed = True
                        fail_type = reason
                        break

            for pattern in redirection_patterns:
                if failed:
                    break

                if resp.url.startswith(pattern):
                    failed = True
                    fail_type = "Redirection"
                    break

            if failed:
                resp_content = None
                break
        except HTTPError as e:
            if e.response.status_code in (429, 403):
                print(Fore.YELLOW + f"\tWe have been rate limited, waiting {wait_time} seconds...")
                sleep(wait_time)
                wait_time += wait_time
            else:
                fail_type = "Not_Found"
                break

    if resp_content is None:
        if fail_type == "Not_Found" or fail_type == "Redirection":
            print(Fore.YELLOW + f"\t{package_name} was not found on {store_name}.", end="\n\n")
        elif fail_type == "Robot":
            if cookie_file is not None:
                print(Fore.RED + f"\tERROR: Cookie file doesn't contain cookies for {store_name}.", end="\n\n")
            else:
                print(Fore.RED + f"\tERROR: {store_name} requires a cookie file.", end="\n\n")

    return resp_content


def download_file(url: str,
                  filepath_without_extension: str) -> str:
    with requests.get(url, stream=True) as resp_stream:
        resp_stream.raise_for_status()

        extension = mimetypes.guess_extension(resp_stream.headers.get("Content-Type"))

        if extension is None:
            raise ExtensionUnknown(f"Couldn't retrieve the correct extension for '{filepath_without_extension}'.")

        with open(filepath_without_extension + extension, "wb") as file_stream:
            for chunk in resp_stream.iter_content(chunk_size=8192):
                file_stream.write(chunk)

        return filepath_without_extension + extension


def is_none_or_empty(data: dict,
                     key: Any,
                     forbidden_values: list[str] = None) -> bool:
    value = data.get(key)

    if value is None:
        return True
    elif isinstance(value, str):
        if value.strip() == "":
            return True

    if forbidden_values is not None and value in forbidden_values:
        return True

    return False


def replace_whitespace(value: str,
                       separator: str) -> str:
    return value.replace(" ", separator)


def is_abi(value: str) -> TypeGuard[ABI]:
    return value in ALL_ABIS


def is_density_name(value: str) -> TypeGuard[AndroidDensityName]:
    return value in ALL_DENSITY_NAMES


def is_density_number(value: str | int) -> TypeGuard[AndroidDensityNumber]:
    return int(value) in ALL_DENSITY_NUMBERS


def is_device_type(value: str) -> TypeGuard[AndroidDeviceType]:
    return value in ALL_DEVICE_TYPES


def is_screen_type(value: str) -> TypeGuard[AndroidScreenType]:
    return value in ALL_SCREEN_TYPES
