# -*- coding: UTF-8 -*-
import typing

type AsyncCallable = typing.Callable[..., typing.Awaitable[typing.Any]]
