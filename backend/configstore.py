"""Encrypted, machine-bound persistence for model configurations.

Model entries (name, base_url, model, api_key) are encrypted with a key derived
from the machine's hardware identifier, so a copied config file cannot be read
on another machine. Stored under the data directory.
"""
import base64
import hashlib
import json
import platform
import uuid
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .store import ROOT


def _fernet():
    material = f'datasheet2symbol:{uuid.getnode()}:{platform.node()}'.encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
    return Fernet(key)


def _path():
    return ROOT / 'models.json.enc'


def load_models():
    path = _path()
    if not path.exists():
        return []
    try:
        return json.loads(_fernet().decrypt(path.read_bytes()))
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError):
        return []


def save_models(models):
    _path().write_bytes(_fernet().encrypt(json.dumps(models, ensure_ascii=False).encode()))
