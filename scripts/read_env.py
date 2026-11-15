"""Emit dotenv values for the Windows launcher without shell quote parsing."""
import json

from dotenv import dotenv_values


if __name__ == '__main__':
    print(json.dumps({key: value for key, value in dotenv_values('.env', encoding='utf-8-sig').items() if value is not None}))
