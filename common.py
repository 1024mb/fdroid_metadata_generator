import os
import re
import sys
from typing import Literal

from pydantic import BaseModel, Field


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


class AppData(BaseModel):
    Licenses: list[str]
    App_Categories: dict[str, str]
    Game_Categories: dict[str, str]
    Locales: Locales
    Icon_Relations: dict[str, str]
    Regex_Patterns: StoreRegexPatterns
    Sport_Category_Pattern: SportCategoryPattern
    User_Agent: str = Field(default="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0")


def get_program_dir() -> str:
    try:
        # noinspection PyUnresolvedReferences
        return os.path.abspath(__compiled__.containing_dir)
    except NameError:
        return os.path.abspath(os.path.dirname(sys.argv[0]))


SupportedStore = Literal["Play_Store", "Amazon_Store", "Apkcombo_Store"]
