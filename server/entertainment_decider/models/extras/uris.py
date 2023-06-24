from __future__ import annotations

from abc import abstractmethod, abstractproperty
from typing import Iterable, Optional, Set


class UriHolder:
    ### abstracted

    @abstractproperty
    def _primary_uri(self) -> str:
        """Returns the primary uri of this object in a naive way."""

    @abstractmethod
    def _set_primary_uri(self, uri: str) -> None:
        """Sets the primary uri of this object in a naive way."""

    @abstractproperty
    def _uri_set(self) -> Set[str]:
        """Returns the uri set of this object in a naive way."""

    @abstractmethod
    def _clear_uri_set(self) -> None:
        """Sets the uri set of this object in a naive way."""

    @abstractmethod
    def _add_uri_to_set(self, uri: str) -> bool:
        """Adds a uri to the uri set of this object in a naive way.

        Returns True if the uri was not in the uri set before.
        """

    @abstractmethod
    def _remove_uri_from_set(self, uri: str) -> bool:
        """Removes a uri to the uri set of this object in a naive way.

        Returns True if the uri was in the uri set before.
        """

    ### implemented

    @property
    def primary_uri(self) -> str:
        """Returns the current primary uri of this object."""
        return self._primary_uri

    @primary_uri.setter
    def primary_uri(self, uri: str) -> None:
        self.set_primary_uri(uri)

    @property
    def uri_set(self) -> Set[str]:
        return self._uri_set

    @uri_set.setter
    def uri_set(self, uri_list: Iterable[Optional[str]]):
        self._clear_uri_set()
        self.add_uris(uri_list)

    # uri_set has no setter due to the problem which uri then becomes primary
    # instead, set_as_only_uri & add_uris should be used so the primary becomes obvious

    def is_primary_uri(self, compare_uri: str) -> bool:
        """Returns True if the given uri is equal to the current primary uri."""
        return self.primary_uri == compare_uri

    def set_primary_uri(self, uri: str) -> bool:
        """Sets the current primary of this object.

        It will also add the uri to the uri set.
        Returns True if the uri was not in the uri set before.

        You may also just write the primary_uri property if you do not need the return value.
        """
        ret = self._add_uri_to_set(uri)  # might fail, so try first
        self._set_primary_uri(uri)
        return ret

    def set_as_only_uri(self, uri: str) -> None:
        self._clear_uri_set()
        self.set_primary_uri(uri)

    def add_single_uri(self, uri: str) -> bool:
        return self._add_uri_to_set(uri)

    def add_uris(self, uri_list: Iterable[Optional[str]]) -> bool:
        return any([self.add_single_uri(uri) for uri in set(uri_list) if uri])

    def remove_single_uri(self, uri: str) -> bool:
        return self._remove_uri_from_set(uri)

    def remove_uris(self, uri_list: Iterable[Optional[str]]) -> bool:
        return any([self.remove_single_uri(uri) for uri in set(uri_list) if uri])
