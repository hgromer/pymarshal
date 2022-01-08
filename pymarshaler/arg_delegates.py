import datetime
import typing

import dateutil.parser as parser

from pymarshaler.errors import UnknownFieldError
from pymarshaler.utils import get_init_params


class ArgBuilderDelegate:

    def __init__(self, cls):
        self.cls = cls

    def name(self) -> str:
        return self.cls.__name__

    def resolve(self, data):
        raise NotImplementedError(f'{ArgBuilderDelegate.__name__} has no implementation of resolve')


class FunctionalArgBuilderDelegate(ArgBuilderDelegate):

    def __init__(self, cls, func):
        super().__init__(cls)
        self.func = func

    def resolve(self, data):
        raise NotImplementedError(f'{FunctionalArgBuilderDelegate.__name__} has no implementation of resolve')


class CachedEnumArgBuilderDelegate(ArgBuilderDelegate):

    def __init__(self, cls):
        super().__init__(cls)
        members = cls.__members__.values()
        if len(members) <= 20:
            print(f'WARNING: ENUM "{cls.__name__}" HAS VERY FEW MEMBERS, IT MAY BE MORE EFFICIENT TO AVOID CACHING')
        self._table = {v.value: v for v in members}

    def resolve(self, data):
        if data not in self._table:
            raise UnknownFieldError(f'Invalid value {data} for enum {self.cls.__name__}')
        return self._table[data]


class EnumArgBuilderDelegate(ArgBuilderDelegate):

    def resolve(self, data):
        for v in self.cls.__members__.values():
            if v.value == data:
                return v
        raise UnknownFieldError(f'Invalid value {data} for enum {self.cls.__name__}')


class ListArgBuilderDelegate(FunctionalArgBuilderDelegate):

    def __init__(self, cls, func):
        super().__init__(cls, func)

    def resolve(self, data: typing.List):
        inner_type = self.cls.__args__[0]
        return [self.func(inner_type, x) for x in data]


class SetArgBuilderDelegate(FunctionalArgBuilderDelegate):

    def __init__(self, cls, func):
        super().__init__(cls, func)

    def resolve(self, data: typing.Set):
        inner_type = self.cls.__args__[0]
        return {self.func(inner_type, x) for x in data}


class TupleArgBuilderDelegate(FunctionalArgBuilderDelegate):

    def __init__(self, cls, func):
        super().__init__(cls, func)

    def resolve(self, data: typing.Tuple):
        inner_type = self.cls.__args__[0]
        return (self.func(inner_type, x) for x in data)


class DictArgBuilderDelegate(FunctionalArgBuilderDelegate):

    def __init__(self, cls, func):
        super().__init__(cls, func)

    def resolve(self, data: dict):
        key_type = self.cls.__args__[0]
        value_type = self.cls.__args__[1]
        return {
            self.func(key_type, key): self.func(value_type, value) for key, value in data.items()
        }


class BuiltinArgBuilderDelegate(ArgBuilderDelegate):

    def __init__(self, cls):
        super().__init__(cls)

    def resolve(self, data):
        if data is None:
            return None
        else:
            return self.cls(data)


class DateTimeArgBuilderDelegate(ArgBuilderDelegate):

    def __init__(self):
        super().__init__(datetime.datetime)

    def resolve(self, data):
        return parser.parse(data)


class UserDefinedArgBuilderDelegate(FunctionalArgBuilderDelegate):

    def __init__(self, cls, func, ignore_unknown_fields: bool, walk_unknown_fields: bool):
        super().__init__(cls, func)
        self.ignore_unknown_fields = ignore_unknown_fields
        self.walk_unknown_fields = walk_unknown_fields

    def resolve(self, data: dict):
        return self._resolve(self.cls, data)

    def _resolve(self, cls, data: dict):
        args = {}
        unsatisfied = get_init_params(cls)
        for key, value in data.items():
            if key in unsatisfied:
                param_type = unsatisfied[key]
                args[key] = self.func(param_type, value)
            elif not self.ignore_unknown_fields:
                raise UnknownFieldError(f'Found unknown field ({key}: {value}). '
                                        'If you would like to skip unknown fields '
                                        'create a Marshal object who can skip ignore_unknown_fields')
            elif self.walk_unknown_fields:
                if isinstance(value, dict):
                    args.update(self._resolve(cls, value))
                elif isinstance(value, (list, set, tuple)):
                    for x in value:
                        if isinstance(x, dict):
                            args.update(self._resolve(cls, x))
        return args
