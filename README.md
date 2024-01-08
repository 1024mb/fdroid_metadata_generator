## This program extracts information from the Play Store and stores it in a YML file for F-Droid Server.

Python version required is 3.10+.

Dependencies
-------------------------

- [pyYAML](https://github.com/yaml/pyyaml)
- [colorist](https://github.com/jakob-bagterp/colorist-for-python)
- [win32-setctime](https://github.com/Delgan/win32-setctime) : *If on Windows*
- [apkfile](https://github.com/david-lev/apkfile) : *Included in repo, forked to add support for aapt2.*

Usage:
-------------------------

```console
usage: parser.py [-h] [-m METADATA_DIR] [-r REPO_DIR] -l LANGUAGE [-f] [-fv] [-ca] [-kf KEY_FILE] [-cf CERT_FILE] [-cpw CERTIFICATE_PASSWORD] [-btp BUILD_TOOLS_PATH] [-aep APK_EDITOR_PATH] [-dls]
                 [-df DATA_FILE] [-rf REPLACEMENT_FILE]

Parser for PlayStore information to F-Droid YML metadata files.

options:
  -h, --help            show this help message and exit
  -m METADATA_DIR, --metadata-dir METADATA_DIR
                        Directory where F-Droid metadata files are stored.
  -r REPO_DIR, --repo-dir REPO_DIR
                        Directory where F-Droid repo files are stored.
  -l LANGUAGE, --language LANGUAGE
                        Language of the information to retrieve.
  -f, --force           Force parsing of information and overwrite existing metadata.
  -fv, --force-version  Force updating version name and code even if they are already specified in the YML file.
  -ca, --convert-apks   Convert APKS files to APK and sign them.
  -kf KEY_FILE, --key-file KEY_FILE
                        Key file used to sign the APK, required if --convert-apks is used.
  -cf CERT_FILE, --cert-file CERT_FILE
                        Cert file used to sign the APK, required if --convert-apks is used.
  -cpw CERTIFICATE_PASSWORD, --certificate-password CERTIFICATE_PASSWORD
                        Password to sign the APK.
  -btp BUILD_TOOLS_PATH, --build-tools-path BUILD_TOOLS_PATH
                        Path to Android SDK buildtools binaries.
  -aep APK_EDITOR_PATH, --apk-editor-path APK_EDITOR_PATH
                        Path to the ApkEditor.jar file.
  -dls, --download-screenshots
                        Download screenshots which will be stored in the repo directory.
  -df DATA_FILE, --data-file DATA_FILE
                        Path to the JSON formatted data file. Defaults to data.json located in the program directory.
  -rf REPLACEMENT_FILE, --replacement-file REPLACEMENT_FILE
                        JSON formatted file containing a dict with replacements for the package name of all found apps.
```

Explanation
-------------------------

This program:

* Needs to know where the metadata is located, it can infer this if you provide either the metadata or repo path.
* Depends on a data file, explained below.
* Needs a language to be provided.
* Needs AAPT and AAPT2 in your PATH.

By default no data will be overwritten except for empty/dummy values.

You can force overwriting existing data (including icons and screenshots) with `-f/--force` or overwrite only the
version numbers in the YML files with `-fv/--force-version`. If `-f`/`--force` is used and screenshots already exist
they will be moved to a backup directory in `/repo/backup`. The deletion of the backup files is up to the user (you).

If the provided paths for the corresponding option don't end in `metadata` or `repo` the program will terminate.

If `-m`/`--metadata-dir` is provided only the YML files present in the `/metadata` directory will be processed, if there
are APK files in the `/repo` directory that don't have a YML file they will not be created.

If `-r`/`--repo-dir` is provided only the APK files present in the `/repo` directory will be processed, if there are YML
files in the `/metadata` directory that don't have an existing APK file they wont be processed.

By default only the icons will be downloaded from Play Store, if you want to also get the
screenshots `-dls`/`--download-screenshots` must be used, they will be stored
in `/repo/<package-id>/en-US/phoneScreenshots` regardless of the language used because that's the locale F-Droid
defaults to.

APKS files can be converted to APK with [ApkEditor][4] by using `-ca`/`--convert-apks`, if APKS conversion is enabled
then the program will require:

- Certificate file path: To sign the resulting APK file. Use `-cf`/`--certificate-file`.
- Key file path: To sign the resulting APK file. Use `-kf`/`--key-file`.
- Certificate password: Only if the certificate is encrypted. Use `-cpw`/`--certificate-password`.
- Path to the ApkEditor.jar file: To convert the APKS file to APK. This is the program that does all the work.
  Use `-aep`/`--apk-editor-path`.
- ApkSigner: It must be in your PATH or you can also specify the path with `-btp`/`--build-tools-path`.

Don't forget to run these two commands after all the download is completed:

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
* **Icon_Relations**: Dict containing the relation between the directory name (key/left) and the icon size (
  value/right). Icons are squares so only the one number is needed.

The default path for the data file is `<path-to-this-program>/data.json`, other path can be specified
using `-df`/`--data-file`

-------------------------

### About the replacement file

This is a JSON formatted file containing a single dict named `Replacements` which stores a dict containing search (key)
and replace (value) mappings.

The replacement file can be used to either replace parts of the package ID or all of it. After the first match all the
rest search terms are skipped for the package, so a package can only be affected by one replacement at the same time.
Included is an example file. Path to this file is specified with `-rf`/`--replacement-file`.

-------------------------

[1]: https://gitlab.com/fdroid/fdroiddata/-/blob/master/schemas/metadata.json

[2]: https://support.google.com/googleplay/android-developer/answer/9859673?hl=en

[3]: https://support.google.com/googleplay/android-developer/table/4419860?hl=en

[4]: https://github.com/REAndroid/APKEditor
