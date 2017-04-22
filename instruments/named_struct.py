#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Class for quickly defining C-like structures with named fields.
"""

# IMPORTS #####################################################################

from __future__ import absolute_import
from __future__ import division

import struct
from collections import OrderedDict

from future.utils import with_metaclass

# DESIGN NOTES ################################################################

# This class uses the Django-like strategy described at
#     http://stackoverflow.com/a/3288988/267841
# to assign a "birthday" to each Field as it's instantiated. We can thus sort
# each Field in a NamedStruct by its birthday.

# Notably, this hack is not at all required on Python 3.6:
#     https://www.python.org/dev/peps/pep-0520/

# TODO: arrays other than string arrays do not currently work.

# PYLINT CONFIGURATION ########################################################

# All of the classes in this module need to interact with each other rather
# deeply, so we disable the protected-access check within this module.

# pylint:disable=protected-access

# CLASSES #####################################################################


class Field(object):
    """
    A named field within a C-style structure.

    :param str fmt: Format for the field, corresponding to the
        documentation of the :mod:`struct` standard library package.
    """

    __n_fields_created = 0
    _field_birthday = None

    _fmt = ''
    _name = None
    _owner_type = object

    def __init__(self, fmt, strip_null=False):
        super(Field, self).__init__()

        # Record our birthday so that we can sort fields later.
        self._field_birthday = Field.__n_fields_created
        Field.__n_fields_created += 1

        self._fmt = fmt.strip()
        self._strip_null = strip_null

    def is_significant(self):
        return not self._fmt.endswith('x')

    @property
    def fmt_char(self):
        return self._fmt[-1]

    def __len__(self):
        if self._fmt[:-1]:
            length = int(self._fmt[-1])
            if length < 0:
                raise TypeError("Field is specified with negative length.")

            # Although we know that length>0, this abs ensures that static
            # code checks are happy with __len__ always returning a positive number
            return abs(length)

        raise TypeError("Field is scalar and has no len().")

    def __repr__(self):
        if self._owner_type:
            return "<Field {} of {}, fmt={}>".format(
                self._name, self._owner_type, self._fmt
            )

        return "<Unbound field, fmt={}>".format(
            self._fmt
        )

    def __str__(self):
        n, fmt_char = len(self), self.fmt_char
        c_type = {
            'x': 'char',
            'c': 'char',
            'b': 'char',
            'B': 'unsigned char',
            '?': 'bool',
            'h': 'short',
            'H': 'unsigned short',
            'i': 'int',
            'I': 'unsigned int',
            'l': 'long',
            'L': 'unsigned long',
            'q': 'long long',
            'Q': 'unsigned long long',
            'f': 'float',
            'd': 'double',
            # NB: no [], since that will be implied by n.
            's': 'char',
            'p': 'char',
            'P': 'void *'
        }[fmt_char]

        if n:
            c_type = "{}[{}]".format(c_type, n)
        return (
            "{c_type} {self._name}".format(c_type=c_type, self=self)
            if self.is_significant()
            else c_type
        )

    # DESCRIPTOR PROTOCOL #

    def __get__(self, obj, type=None):
        return obj._values[self._name]

    def __set__(self, obj, value):
        obj._values[self._name] = value

class StringField(Field):
    """
    Represents a field that is interpreted as a Python string.

    :param int length: Maximum allowed length of the field, as
        measured in the number of bytes used by its encoding.
        Note that if a shorter string is provided, it will
        be padded by null bytes.
    :param str encoding: Name of an encoding to use in serialization
        and deserialization to Python strings.
    :param bool strip_null: If `True`, null bytes (``'\x00'``) will
        be removed from the right upon deserialization.
    """

    _strip_null = False
    _encoding = 'ascii'

    def __init__(self, length, encoding='ascii', strip_null=False):
        super(StringField, self).__init__('{}s'.format(length))
        self._strip_null = strip_null
        self._encoding = encoding

    def __set__(self, obj, value):
        if isinstance(value, bytes):
            value = value.decode(self._encoding)
        if self._strip_null:
            value = value.rstrip('\x00')
        value = value.encode(self._encoding)

        super(StringField, self).__set__(obj, value)

    def __get__(self, obj, type=None):
        super(StringField, self).__get__(obj, type=type).decode(self._encoding)


class Padding(Field):
    """
    Represents a field whose value is insignificant, and will not
    be kept in serialization and deserialization.

    :param int n_bytes: Number of padding bytes occupied by this field.
    """

    def __init__(self, n_bytes=1):
        super(Padding, self).__init__('{}x'.format(n_bytes))

class HasFields(type):
    def __new__(mcs, name, bases, attrs):
        # Since this is a metaclass, the __new__ method observes
        # creation of new *classes* and not new instances.
        # We call the superclass of HasFields, which is another
        # metaclass, to do most of the heavy lifting of creating
        # the new class.
        cls = super(HasFields, mcs).__new__(mcs, name, bases, attrs)

        # We now sort the fields by their birthdays and store them in an
        # ordered dict for easier look up later.
        cls._fields = OrderedDict([
            (field_name, field)
            for field_name, field in sorted(
                [
                    (field_name, field)
                    for field_name, field in attrs.items()
                    if isinstance(field, Field)
                ],
                key=lambda item: item[1]._field_birthday
            )
        ])

        # Assign names and owner types to each field so that they can follow
        # the descriptor protocol.
        for field_name, field in cls._fields.items():
            field._name = field_name
            field._owner_type = cls

        # Associate a struct.Struct instance with the new class
        # that defines how to pack/unpack the new type.
        cls._struct = struct.Struct(
            # TODO: support alignment char at start.
            " ".join([
                field._fmt for field in cls._fields.values()
            ])
        )

        return cls


class NamedStruct(with_metaclass(HasFields, object)):
    """
    Represents a C-style struct with one or more named fields,
    useful for packing and unpacking serialized data documented
    in terms of C examples. For instance, consider a struct of the
    form::

        typedef struct {
            unsigned long a = 0x1234;
            char[12] dummy;
            unsigned char b = 0xab;
        } Foo;

    This struct can be represented as the following NamedStruct::

        class Foo(NamedStruct):
            a = Field('L')
            dummy = Padding(12)
            b = Field('B')

        foo = Foo(a=0x1234, b=0xab)
    """

    # Provide reasonable defaults for the lowercase-f-fields
    # created by HasFields. This will prevent a few edge cases,
    # allow type inference and will prevent pylint false positives.
    _fields = {}
    _struct = None

    def __init__(self, **kwargs):
        super(NamedStruct, self).__init__()
        self._values = OrderedDict([
            (
                field._name, None
            )
            for field in filter(Field.is_significant, self._fields.values())
        ])

        for field_name, value in kwargs.items():
            setattr(self, field_name, value)

    def _to_seq(self):
        return tuple(self._values.values())

    @classmethod
    def _from_seq(cls, new_values):
        return cls(**{
            field._name: new_value
            for field, new_value in
            zip(list(filter(Field.is_significant, cls._fields.values())), new_values)
        })

    def pack(self):
        """
        Packs this instance into bytes, suitable for transmitting over
        a network or recording to disc. See :func:`struct.pack` for details.

        :return bytes packed_data: A serialized representation of this
            instance.
        """
        return self._struct.pack(*self._to_seq())

    @classmethod
    def unpack(cls, buffer):
        """
        Given a buffer, unpacks it into an instance of this NamedStruct.
        See :func:`struct.unpack` for details.

        :param bytes buffer: Data to use in creating a new instance.
        :return: The new instance represented by `buffer`.
        """
        return cls._from_seq(cls._struct.unpack(buffer))

    def __eq__(self, other):
        if not isinstance(other, NamedStruct):
            return False

        return self._values == other._values

    def __str__(self):
        return "{name} {{\n{fields}\n}}".format(
            name=type(self).__name__,
            fields="\n".join([
                "    {field}{value};".format(
                    field=field,
                    value=(
                        " = {}".format(repr(self._values[field._name]))
                        if field.is_significant()
                        else ""
                    )
                )
                for field in self._fields.values()
            ])
        )
