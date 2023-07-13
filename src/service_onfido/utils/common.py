import os
import time
import uuid
import random
import string
from decimal import Decimal
from logging import getLogger


logger = getLogger('django')


def to_cents(amount: Decimal, divisibility: int) -> int:
    return int(amount * Decimal('10')**divisibility)


def from_cents(amount: int, divisibility: int) -> Decimal:
    return Decimal(amount) / Decimal('10')**divisibility


def id_generator(size=20, chars=string.ascii_letters + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def get_unique_filename(filename):
    name, ext = os.path.splitext(filename)
    return "{}_{}{}".format(uuid.uuid4().hex, str(int(time.time())), ext)


def truncate(string, size: int = 300, suffix='...'):
    """
    Truncate the given string at a set length with a prefix.

    string: String to truncate
    size: Max size of the string before truncate
    suffix: String that is appended to the truncated string
    """
    return "".join((str(string)[:size - len(suffix)], suffix)) \
        if len(str(string)) > size else str(string)
