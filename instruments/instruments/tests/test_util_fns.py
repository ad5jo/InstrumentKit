#!/usr/bin/python
# -*- coding: utf-8 -*-
##
# test_util_fns.py: Tests various utility functions.
##
# © 2013 Steven Casagrande (scasagrande@galvant.ca).
#
# This file is a part of the InstrumentKit project.
# Licensed under the AGPL version 3.
##
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
##

## IMPORTS ####################################################################

import quantities as pq
from cStringIO import StringIO

from nose.tools import raises, eq_

from instruments.util_fns import (
    ProxyList,
    assume_units, bool_property, enum_property, int_property,
    split_unit_str
)

from flufl.enum import Enum

## CLASSES ####################################################################

class MockInstrument(object):
    """
    Mock class that admits sendcmd/query but little else such that property
    factories can be tested by deriving from the class.
    """
    
    def __init__(self, responses=None):
        self._buf = StringIO()
        self._responses = responses if responses is not None else {}
        
    @property
    def value(self):
        return self._buf.getvalue()
        
    def sendcmd(self, cmd):
        self._buf.write("{}\n".format(cmd))
        
    def query(self, cmd):
        self.sendcmd(cmd)
        return self._responses[cmd.strip()]

## TEST CASES #################################################################

def test_ProxyList():
    class ProxyChild(object):
        def __init__(self, parent, name):
            self._parent = parent
            self._name = name
            
    class MockEnum(Enum):
        a = "aa"
        b = "bb"
            
    parent = object()
    
    proxy_list = ProxyList(parent, ProxyChild, xrange(10))
    
    child = proxy_list[0]
    assert child._parent is parent
    assert child._name == 0
    
    proxy_list = ProxyList(parent, ProxyChild, MockEnum)
    assert proxy_list['aa']._name == MockEnum.a
    assert proxy_list['b']._name  == MockEnum.b
    assert proxy_list[MockEnum.a]._name == MockEnum.a

def test_assume_units_correct():
    m = pq.Quantity(1, 'm')
    
    # Check that unitful quantities are kept unitful.
    eq_(assume_units(m, 'mm').rescale('mm').magnitude, 1000)
    
    # Check that raw scalars are made unitful.
    eq_(assume_units(1, 'm').rescale('mm').magnitude, 1000)
    
@raises(ValueError)
def test_assume_units_failures():
    assume_units(1, 'm').rescale('s')
    
def test_bool_property():
    class BoolMock(MockInstrument):
        mock1 = bool_property('MOCK1', 'ON', 'OFF')
        mock2 = bool_property('MOCK2', 'YES', 'NO')
        
    mock = BoolMock({'MOCK1?': 'OFF', 'MOCK2?': 'YES'})
    
    assert not mock.mock1
    assert mock.mock2
    
    mock.mock1 = True
    mock.mock2 = False
    
    eq_(mock.value, 'MOCK1?\nMOCK2?\nMOCK1 ON\nMOCK2 NO\n')
    
def test_enum_property():
    class SillyEnum(Enum):
        a = 'aa'
        b = 'bb'
        
    class EnumMock(MockInstrument):
        a = enum_property('MOCK:A', SillyEnum)
        b = enum_property('MOCK:B', SillyEnum)
        
    mock = EnumMock({'MOCK:A?': 'aa', 'MOCK:B?': 'bb'})
    
    assert mock.a is SillyEnum.a
    assert mock.b is SillyEnum.b
    
    # Test EnumValues, string values and string names.
    mock.a = SillyEnum.b
    mock.b = 'a'
    mock.b = 'bb'
    
    eq_(mock.value, 'MOCK:A?\nMOCK:B?\nMOCK:A bb\nMOCK:B aa\nMOCK:B bb\n')

# TODO: test other property factories!

@raises(ValueError)
def test_int_property_valid_set():
    class IntMock(MockInstrument):
        mock = int_property('MOCK', valid_set=set([1, 2]))
        
    mock = IntMock()
    mock.mock = 3

def test_split_unit_str_magnitude_and_units():
    """
    split_unit_str: Given the input "42 foobars" I expect the output
    to be (42, "foobars").
    
    This checks that "[val] [units]" works where val is a non-scientific number
    """
    mag, units = split_unit_str("42 foobars")
    eq_(mag, 42)
    eq_(units, "foobars")
    
def test_split_unit_str_magnitude_and_default_units():
    """
    split_unit_str: Given the input "42" and default_units="foobars"
    I expect output to be (42, "foobars").
    
    This checks that when given a string without units, the function returns
    default_units as the units.
    """
    mag, units = split_unit_str("42", default_units="foobars")
    eq_(mag, 42)
    eq_(units, "foobars")
    
def test_split_unit_str_ignore_default_units():
    """
    split_unit_str: Given the input "42 snafus" and default_units="foobars"
    I expect the output to be (42, "snafus").
    
    This verifies that if the input has units, then any specified default_units
    are ignored.
    """
    mag, units = split_unit_str("42 snafus", default_units="foobars")
    eq_(mag, 42)
    eq_(units, "snafus")
    
def test_split_unit_str_lookups():
    """
    split_unit_str: Given the input "42 FOO" and a dictionary for our units
    lookup, I expect the output to be (42, "foobars").
    
    This checks that the unit lookup parameter is correctly called, which can be
    used to map between units as string and their pyquantities equivalent.
    """
    unit_dict = {
        "FOO": "foobars",
        "SNA": "snafus"
    }
    mag, units = split_unit_str("42 FOO", lookup=unit_dict.__getitem__)
    eq_(mag, 42)
    eq_(units, "foobars")
    
def test_split_unit_str_scientific_notation():
    """
    split_unit_str: Given inputs of scientific notation, I expect the output
    to correctly represent the inputted magnitude.
    
    This checks that inputs with scientific notation are correctly converted
    to floats.
    """
    # No signs, no units
    mag, units = split_unit_str("123E1")
    eq_(mag, 1230)
    eq_(units, pq.dimensionless)
    # Negative exponential, no units
    mag, units = split_unit_str("123E-1")
    eq_(mag, 12.3)
    eq_(units, pq.dimensionless)
    # Negative magnitude, no units
    mag, units = split_unit_str("-123E1")
    eq_(mag, -1230)
    eq_(units, pq.dimensionless)
    # No signs, with units
    mag, units = split_unit_str("123E1 foobars")
    eq_(mag, 1230)
    eq_(units, "foobars")
    # Signs everywhere, with units
    mag, units = split_unit_str("-123E-1 foobars")
    eq_(mag, -12.3)
    eq_(units, "foobars")
    # Lower case e
    mag, units = split_unit_str("123e1")
    eq_(mag, 1230)
    eq_(units, pq.dimensionless)
    
@raises(ValueError)
def test_split_unit_str_empty_string():
    """
    split_unit_str: Given an empty string, I expect the function to raise
    a ValueError.
    """
    mag, units = split_unit_str("")
    
@raises(ValueError)
def test_split_unit_str_only_exponential():
    """
    split_unit_str: Given a string with only an exponential, I expect the 
    function to raise a ValueError.
    """
    mag, units = split_unit_str("E3")
    
def test_split_unit_str_magnitude_with_decimal():
    """
    split_unit_str: Given a string with magnitude containing a decimal, I
    expect the function to correctly parse the magnitude.
    """
    # Decimal and units
    mag, units = split_unit_str("123.4 foobars")
    eq_(mag, 123.4)
    eq_(units, "foobars")
    # Decimal, units, and exponential
    mag, units = split_unit_str("123.4E1 foobars")
    eq_(mag, 1234)
    eq_(units, "foobars")
    
@raises(ValueError)
def test_split_unit_str_only_units():
    """
    split_unit_str: Given a bad string containing only units (ie, no numbers),
    I expect the function to raise a ValueError.
    """
    mag, units = split_unit_str("foobars")

