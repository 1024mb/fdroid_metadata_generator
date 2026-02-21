## This program extracts information from third party stores and saves it in a YAML file for F-Droid Server.

Python version required is 3.11+.

Dependencies
-------------------------

- [ruamel.yaml](https://sourceforge.net/projects/ruamel-yaml)
- [colorama](https://github.com/tartley/colorama)
- [win32-setctime](https://github.com/Delgan/win32-setctime) : *If on Windows*
- [pillow](https://github.com/python-pillow/Pillow)
- [requests](https://github.com/psf/requests)
- [pydantic](https://github.com/pydantic/pydantic/)

Usage:
-------------------------

```console
usage: parser.py [-h] [--metadata-dir METADATA_DIR] [--repo-dir REPO_DIR]
                 [--unsigned-dir UNSIGNED_DIR] --language LANGUAGE
                 [--force-metadata] [--force-version] [--force-screenshots]
                 [--force-icons] [--force-all] [--convert-apks] [--sign-apk]
                 [--key-file KEY_FILE] [--cert-file CERT_FILE]
                 [--certificate-password CERTIFICATE_PASSWORD]
                 [--build-tools-path BUILD_TOOLS_PATH]
                 [--apk-editor-path APK_EDITOR_PATH] [--download-screenshots]
                 [--data-file DATA_FILE] [--replacement-file REPLACEMENT_FILE]
                 [--log-path LOG_PATH] [--cookie-path COOKIE_PATH]
                 [--use-eng-name] [--rename-files] [--skip-if-exists]
                 [--recompile-bad-apk] [--apktool-path APKTOOL_PATH]

Parser for PlayStore information to F-Droid YML metadata files.

options:
  -h, --help            show this help message and exit
  --metadata-dir METADATA_DIR
                        Directory where F-Droid metadata files are stored.
  --repo-dir REPO_DIR   Directory where F-Droid repo files are stored.
  --unsigned-dir UNSIGNED_DIR
                        Directory where unsigned app files are stored.
  --language LANGUAGE   Language of the information to retrieve.
  --force-metadata      Force overwrite existing metadata.
  --force-version       Force updating version name and code even if they are
                        already specified in the YML file.
  --force-screenshots   Force overwrite existing screenshots.
  --force-icons         Force overwrite existing icons.
  --force-all           Force overwrite existing metadata, screenshots and
                        icons.
  --convert-apks        Convert APKS files to APK and sign them.
  --sign-apk            Sign resulting APK files from APKS conversion.
  --key-file KEY_FILE   Key file used to sign the APK, required if --convert-
                        apks is used.
  --cert-file CERT_FILE
                        Cert file used to sign the APK, required if --convert-
                        apks is used.
  --certificate-password CERTIFICATE_PASSWORD
                        Password to sign the APK.
  --build-tools-path BUILD_TOOLS_PATH
                        Path to Android SDK buildtools binaries.
  --apk-editor-path APK_EDITOR_PATH
                        Path to the ApkEditor.jar file.
  --download-screenshots
                        Download screenshots which will be stored in the repo
                        directory.
  --data-file DATA_FILE
                        Path to the JSON formatted data file. Default:
                        data.json located in the program's directory.
  --replacement-file REPLACEMENT_FILE
                        JSON formatted file containing a dict with
                        replacements for the package name of all found apps.
  --log-path LOG_PATH   Path to the directory where to store the log files.
                        Default: Program's directory.
  --cookie-path COOKIE_PATH
                        Path to a Netscape cookie file.
  --use-eng-name        Use the English app name instead of the localized one.
  --rename-files        Rename APK files to packageName_versionCode. Requires
                        aapt2 and aapt2.
  --skip-if-exists      Skip renaming if the file already exists. By default a
                        numeric suffix is appended to the name.
  --recompile-bad-apk   Recompile APK files that have CRC errors. File dates
                        are preserved. Requires apktool.
  --apktool-path APKTOOL_PATH
                        Path to apktool. By default uses apktool.jar in the
                        program's directory.
```

Explanation
-------------------------

This program:

* Needs to know where the metadata is located, it can infer this if you provide either the metadata, repo or unsigned
  path.
* Depends on a data file, explained below.
* Needs a language to be provided.
* Requires AAPT and AAPT2.
* If using the renamer, depends on a `sdk_names.json` file

By default, no data will be overwritten except for empty or dummy values.

You can:

- Force overwrite all existing data (metadata, icons and screenshots) with `--force-all`.
- Force overwrite existing metadata with `--force-metadata`.
- Force overwrite only the version values in the YML files with `--force-version`.
- Force overwrite all the icons with `--force-icons`.
- Force overwrite the screenshots with `--force-screenshots`.
- Force use English application names with `--use-eng-name`.
- Rename files to F-Droids default naming with `--rename-files` and skip renaming if file already exists
  with `--skip-if-exists`.
- Recompile APK files with CRC errors with `--recompile-bad-apk`. (This requires `--apktool-path`)

If `--force-screenshots`/`--force-all` is used and screenshots already exist they will be moved to a backup directory
in `/repo/backup`, the backup directory will be emptied before this move operation.
The deletion of the backup files is up to the user (you).

If the provided paths for the corresponding option don't end with `metadata`, `repo` or `unsigned` the program will
terminate.

If `--metadata-dir` is provided only the YML files present in the `/metadata` directory will be processed, if there
are APK files in the `/repo` directory that don't have a YML file they will not be created.

If `--repo-dir` is provided only the APK files present in the `/repo` directory will be processed, if there are YML
files in the `/metadata` directory that don't have an existing APK file they will not be processed.

If `--unsigned-dir` is provided only the APK files present in the `/unsigned` directory will be processed, APK
files in the `repo` directory and YML files in the `metadata` directory that don't match any APK in the `unsigned`
directory will not be processed.

By default, only the icons will be downloaded from the stores, if you want to also get the
screenshots `--download-screenshots` must be used, they will be stored in `/repo/<package-id>/en-US/phoneScreenshots`
regardless of the language used because that's the locale F-Droid defaults to.

APKS files can be converted to APK with [ApkEditor][4] by using `--convert-apks`, if APKS conversion is enabled
then the program will require:

- Path to the ApkEditor.jar file: To convert the APKS file to APK. This is the program that does all the work.
  Use `--apk-editor-path` to provide the path.

If `--sign-apk` is specified:

- Certificate file path: To sign the resulting APK file. Use `--certificate-file`.
- Key file path: To sign the resulting APK file. Use `--key-file`.
- Certificate password: Only if the certificate is encrypted. Use `--certificate-password`.
- ApkSigner: It must be in your PATH, or you can also specify the path with `--build-tools-path`.

The anti-features are detected based on some keywords, is not perfect:

* `NonFreeAssets` is always assumed.
* If no repo is found `UpstreamNonFree` is assumed.
* If ads are detected `Ads` is used.
* If any data sharing or collection is detected `Tracking` is used.
* If In-app purchases are detected `NonFreeDep` and `NonFreeNet` are used.

The license extraction is done this way:

1. If the app's website is a GitHub or a GitLab repository, the license of the app is assumed to be the same as the
   license of the repository.
2. If the license from the repo doesn't match any licenses accepted by F-Droid (set in the `data` file) then "Other"
   will be used.
3. If the app's website is not a repository, "Copyright" will be assumed.

Packages not found and packages that had any data not found will be writen to a log file located by default in the same
program's directory, the path can be configured with `--log-path`.
They are also printed at the end.

-------------------------

### Supported Stores

- Play Store
- Amazon Appstore
- Apkcombo

-------------------------

Remember to run these two commands after all the download is completed:

```console
fdroid rewritemeta
fdroid update
```

-------------------------

### About the data file

The data file is a JSON formatted file that contains required information for this program to work, at the same time it
also contains mappings used to link categories and icon sizes, this can be customized by editing the `data.json` file.
The contents are as follows:

* **Licenses**: List containing the licenses accepted by F-Droid taken from the official [metadata.json][1] file.
* **App_Categories**: Dict containing the mapping for app categories. If key (left) is found, value (right) will be used
  if not empty, otherwise key (left) is used. Categories taken from the Play Store [official documentation][2].
* **Game_Categories**: Dict containing the mapping for game categories. Same logic than the one for app categories is
  used. Categories taken from the Play Store [official documentation][2].
* **Locales**: List containing the official supported languages for the Play Store. Locales taken from
  the [official documentation][3].
* **Icon_Relations**: Dict containing the relation between the directory name (key/left) and
  the icon size (value/right). Icons are squares so only the one number is needed.
* **Regex_Patterns**: Dict containing the regex search patterns for data extraction for every supported store: key/left
  is name of the pattern, value/right is the (regex) pattern.

The default path for the data file is `<path-to-this-program>/data.json`, another path can be specified
using `--data-file`.

-------------------------

### About the replacement file

This is a JSON formatted file containing a single dict named `Replacements` which stores a dict containing search (key)
and replace (value) mappings.

The replacement file can be used to either replace parts of the package ID or all of it. After the first match, all the
rest of the search terms are skipped for the package, so a package can only be affected by one replacement at the same
time.
Included is an example file. Path to this file is specified with `--replacement-file`.

-------------------------

### About the sdk_names file

This is a simple JSON file containing the SDK name as a key and a tuple of the version number and name as the value.
It's only used by the renamer, if the renaming function is not used then you don't need this.

-------------------------

[1]: https://gitlab.com/fdroid/fdroiddata/-/blob/master/schemas/metadata.json

[2]: https://support.google.com/googleplay/android-developer/answer/9859673?hl=en

[3]: https://support.google.com/googleplay/android-developer/table/4419860?hl=en

[4]: https://github.com/REAndroid/APKEditor
