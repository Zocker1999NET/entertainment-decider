from __future__ import annotations

from abc import (
    abstractmethod,
    abstractproperty,
)
from typing import (
    Iterable,
    Optional,
    Set,
)


class UriHolder:
    ### abstracted

    @abstractproperty
    def _primary_uri(self) -> str:
        """Returns the primary uri of this object in a naive way."""

    @abstractmethod
    def _set_primary_uri(self, uri: str) -> bool:
        """Sets the primary uri of this object in a naive way.

        Returns True if an action was applied, False otherwise.
        If the uri was already primary,
        both True or False might be returned.

        When overriding this method,
        if you call the super() and its call returns True,
        you should avoid making changes yourself.

        A final non-abstract version of this method must throw an error
        if it fails to set the primary uri instead of just returning False.
        The return value is mainly for overwriting methods to divert the change.
        """
        return False

    @abstractproperty
    def _uri_set(self) -> Set[str]:
        """Returns the uri set of this object in a naive way."""

    @abstractmethod
    def _clear_uri_set(self) -> None:
        """Sets the uri set of this object in a naive way."""

    @abstractmethod
    def _add_uri_to_set(self, uri: str) -> bool:
        """Adds a uri to the uri set of this object in a naive way.

        Returns True if an action was applied, False otherwise.
        If the uri was already part of the uri set,
        both True or False might be returned.

        When overriding this method,
        if you call the super() and its call returns True,
        you should avoid making changes yourself.

        A final non-abstract version of this method must throw an error
        if it fails at adding the uri instead of just returning False.
        The return value is mainly for overwriting methods to divert the change.
        """
        return False

    @abstractmethod
    def _remove_uri_from_set(self, uri: str) -> bool:
        """Removes a uri to the uri set of this object in a naive way.

        Returns True if a change was applied, False otherwise.
        If the uri was already absent from the uri set,
        both True or False might be returned.

        When overriding this method,
        if you call the super() and its call returns True,
        you should avoid making changes yourself.

        A final non-abstract version of this method must throw an error
        if it fails at removing the uri instead of just returning False.
        The return value is mainly for overwriting methods to divert the change.
        """
        return False

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
    def uri_set(self, uri_list: Iterable[Optional[str]]) -> None:
        """
        uri_set setter cannot be implemented for now!

        uri_set has no setter due to the problem which uri then becomes primary.
        Instead, set_as_only_uri & add_uris should be used so the primary becomes obvious.
        In future, when no primary uri is required, it will be implemented.
        """
        raise NotImplementedError(
            "UriHolder.uri_set setter cannot be implemented (for now)",
        )

    def is_primary_uri(self, compare_uri: str) -> bool:
        """Returns True if the given uri is equal to the current primary uri."""
        return self.primary_uri == compare_uri

    def set_primary_uri(self, uri: str) -> None:
        """Sets the current primary of this object.

        It will also add the uri to the uri set.

        You may also just write the primary_uri property.
        """
        self._add_uri_to_set(uri)  # might fail, so try first
        self._set_primary_uri(uri)

    def set_as_only_uri(self, uri: str) -> None:
        self._clear_uri_set()
        self.set_primary_uri(uri)

    def add_single_uri(self, uri: str) -> None:
        self._add_uri_to_set(uri)

    def add_uris(self, uri_list: Iterable[Optional[str]]) -> None:
        for uri in set(uri_list):
            if uri is not None:
                self.add_single_uri(uri)

    def remove_single_uri(self, uri: str) -> None:
        self._remove_uri_from_set(uri)

    def remove_uris(self, uri_list: Iterable[Optional[str]]) -> None:
        for uri in set(uri_list):
            if uri is not None:
                self.remove_single_uri(uri)
