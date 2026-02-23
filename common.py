import os
import re
import sys
from http.cookiejar import MozillaCookieJar
from time import sleep
from typing import Literal

import requests
from colorama import Fore
from pydantic import BaseModel, Field
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


def get_program_dir() -> str:
    try:
        # noinspection PyUnresolvedReferences
        return os.path.abspath(__compiled__.containing_dir)
    except NameError:
        return os.path.abspath(os.path.dirname(sys.argv[0]))


SupportedStore = Literal["Play_Store", "Amazon_Store", "Apkcombo_Store"]
FailType = Literal["Not_Found", "Robot", "Redirection", ""]


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
        session.cookies = cookie_jar
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
