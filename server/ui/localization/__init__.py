from pathlib import Path

import yaml

if Path("translations.yaml").exists():
    with open("translations.yaml", "r") as f:
        locale_database = yaml.safe_load(f)
else:
    locale_database = dict()

def localize(text, language):
    if text not in locale_database:
        locale_database[text] = dict(EN=text, PT="")
        with open("translations.yaml", "w") as f:
            f.write(yaml.dump(locale_database))
    if len(locale_database[text][language]) > 0:
        return locale_database[text][language]
    return text