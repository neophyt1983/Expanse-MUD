"""Internet accounts. Secrets stay in the host's private save directory."""
import unicodedata
import hashlib, secrets
from http.cookies import SimpleCookie

COOKIE = '__Host-expanse'

class CharacterNameUnavailable(ValueError):
    pass

def display_name(value):
    if not isinstance(value, str):
        raise ValueError('Enter a character name.')
    name = ' '.join(unicodedata.normalize('NFKC', value).split()).replace('’', "'")
    if not 1 <= len(name) <= 61 or not any(c.isalpha() for c in name) or any(
        not (c.isalnum() or unicodedata.category(c).startswith('M') or c in " -'_") for c in name
    ):
        raise ValueError('Use a character name with letters, spaces, digits, hyphens or apostrophes.')
    return name

def name_key(value):
    return display_name(value).casefold()

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def password_hash(password, salt=None):
    if not isinstance(password,str) or not 15 <= len(password) <= 128:
        raise ValueError('Use a password of 15 to 128 characters.')
    salt = salt or secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=131072,r=8,p=1,maxmem=256*1024*1024)
    return salt+':'+key.hex()

def token_from_cookie(header):
    try:
        c=SimpleCookie();c.load(header or '')
        return c[COOKIE].value if COOKIE in c else ''
    except Exception:return ''

