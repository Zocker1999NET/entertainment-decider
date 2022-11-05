from __future__ import annotations

from typing import Callable, Generic, TypeVar


T = TypeVar("T")
S = TypeVar("S")


class Chain(Generic[T]):

    __value: T

    def __init__(self, start_value: T) -> None:
        super().__init__()
        self.__value = start_value

    def use(self, converter: Callable[[T], S]) -> Chain[S]:
        return Chain(converter(self.__value))

    # infix notation
    def __or__(self, converter: Callable[[T], S]) -> Chain[S]:
        return self.use(converter=converter)

    def get(self) -> T:
        return self.__value
