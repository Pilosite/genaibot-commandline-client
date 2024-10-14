import pytest
from genaibot_cmd import *

def test_add():
    assert add(2, 3) == 5

def test_subtract():
    assert subtract(5, 2) == 3

def test_multiply():
    assert multiply(4, 6) == 24

def test_divide():
    assert divide(10, 2) == 5