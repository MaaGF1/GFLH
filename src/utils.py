# src/utils.py

import json
import os
import sys

class I18nManager:
    def __init__(self, lang="en"):
        self.lang = lang
        self.strings = {}
        self.load_lang(self.lang)

    def load_lang(self, lang):
        self.lang = lang
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_dir, "conf", f"lang.{lang}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.strings = json.load(f)
        except Exception as e:
            print(f"Failed to load lang {lang}: {e}")

    def get(self, key):
        return self.strings.get(key, key)

global_i18n = I18nManager("en")

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # In dev mode, we assume working dir is project root or src
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base_path, relative_path)