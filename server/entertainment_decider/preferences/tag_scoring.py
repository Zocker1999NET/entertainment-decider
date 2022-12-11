from __future__ import annotations

import base64
import dataclasses
from dataclasses import dataclass
import gzip
import json
import math
from typing import Dict, Generic, Iterable, List, TypeAlias, Union

from ..extras import Chain
from .tag_protocol import T, TagableProto, TagGetter


@dataclass
class PreferenceScore(Generic[T]):
    points: Dict[T, float] = dataclasses.field(default_factory=lambda: {})

    def __add__(
        self,
        other: PreferenceScoreCompatible[T],
    ) -> PreferenceScore[T]:
        return (self & other).calculate()

    def __and__(
        self,
        other: PreferenceScoreCompatible[T],
    ) -> PreferenceScoreAppender[T]:
        return PreferenceScoreAppender[T](self, other)

    def __mul__(self, scalar: float) -> PreferenceScore[T]:
        return PreferenceScore[T](
            {tag: score * scalar for tag, score in self.points.items()}
        )

    def __neg__(self) -> PreferenceScore[T]:
        return self * -1

    @staticmethod
    def max_score_increase(score: float, adapt_count: int) -> float:
        # depends on PreferenceScoreAppender.share_score(_flat)
        return score * adapt_count

    def adapt_score(
        self,
        tagable: TagableProto[T],
        score: float,
        on_hierachy: bool = True,
    ) -> PreferenceScore[T]:
        addition = (
            PreferenceScoreAppender.share_score
            if on_hierachy
            else PreferenceScoreAppender.share_score_flat
        )(tagable, score)
        return (self & addition).calculate()

    def calculate_score(self, object: TagableProto[T]) -> float:
        return self.calculate_iter_score(object.all_tags)

    def calculate_iter_score(self, tag_iter: Iterable[T]) -> float:
        return math.fsum(self.points.get(tag, 0) for tag in tag_iter)

    @classmethod
    def from_json(cls, data: str, get_tag: TagGetter[T]) -> PreferenceScore[T]:
        dicts: Dict[int, float] = json.loads(data)
        return cls({get_tag(id): score for id, score in dicts.items()})

    @classmethod
    def from_base64(
        cls,
        in_data: str,
        get_tag: TagGetter[T],
        encoding: str = "utf-8",
    ) -> PreferenceScore[T]:
        return (
            Chain(in_data)
            | (lambda d: d.encode(encoding=encoding))
            | base64.decodebytes
            | gzip.decompress
            | (lambda d: d.decode(encoding=encoding))
            | (lambda d: PreferenceScore.from_json(d, get_tag))
        ).get()

    def to_json(self) -> str:
        return json.dumps({tag.id: score for tag, score in self.points.items()})

    def to_base64(self, encoding: str = "utf-8") -> str:
        return (
            Chain(self)
            | PreferenceScore.to_json
            | (lambda d: d.encode(encoding=encoding))
            | (
                lambda d: gzip.compress(
                    data=d,
                    compresslevel=9,
                )
            )
            | base64.encodebytes
            | (lambda d: d.decode(encoding=encoding))
        ).get()


class PreferenceScoreAppender(Generic[T]):
    points_list: List[PreferenceScore[T]]

    @staticmethod
    def share_score_flat(obj: TagableProto[T], score: float) -> PreferenceScoreSuper[T]:
        # influences PreferenceScore.max_score_increase
        direct_tags = [tag for tag in obj.direct_tags if tag.use_for_preferences]
        if len(direct_tags) <= 0:
            return PreferenceScoreAppender()
        return PreferenceScore({tag: score / len(direct_tags) for tag in direct_tags})

    @classmethod
    def share_score(cls, obj: TagableProto[T], score: float) -> PreferenceScoreSuper[T]:
        # influences PreferenceScore.max_score_increase
        direct_tags = [tag for tag in obj.direct_tags if tag.use_for_preferences]
        super_tags = [tag for tag in obj.super_tags if tag.use_for_preferences]
        direct_count = len(direct_tags)
        super_count = len(super_tags)
        if (direct_count + super_count) <= 0:
            return PreferenceScore()
        direct_fraction = super_count + direct_count
        full_dist_count = super_count + (direct_fraction * direct_count)
        single_direct_share = (direct_fraction * score) / full_dist_count
        single_super_share = score / full_dist_count
        assert (
            ((direct_count * single_direct_share) + (super_count * single_super_share))
            - score
        ) <= 0.0001
        return PreferenceScoreAppender(
            *(
                (cls.share_score_flat if obj == tag else cls.share_score)(
                    obj=tag,
                    score=single_direct_share,
                )
                for tag in direct_tags
            ),
            *(cls.share_score(tag, single_super_share) for tag in super_tags),
        )

    def __init__(self, *args: PreferenceScoreCompatible[T]):
        self.points_list = []
        for preference in args:
            self.__append(preference)

    def __append(
        self,
        preference: PreferenceScoreCompatible[T],
    ) -> None:
        if isinstance(preference, PreferenceScore):
            self.points_list.append(preference)
        elif isinstance(preference, PreferenceScoreAppender):
            self.points_list.extend(preference.points_list)
        else:
            for sub_pref in preference:
                self.__append(sub_pref)

    def __and__(
        self,
        other: PreferenceScoreCompatible[T],
    ) -> PreferenceScoreAppender[T]:
        return PreferenceScoreAppender(self, other)

    def calculate(self) -> PreferenceScore[T]:
        combined: Dict[T, List[float]] = {}
        for preference in self.points_list:
            for tag, score in preference.points.items():
                if tag not in combined:
                    combined[tag] = []
                combined[tag].append(score)
        return PreferenceScore(
            {tag: math.fsum(scores) for tag, scores in combined.items()}
        )


PreferenceScoreSuper: TypeAlias = Union[
    PreferenceScore[T],
    PreferenceScoreAppender[T],
]
PreferenceScoreCompatible: TypeAlias = Union[
    PreferenceScoreSuper[T],
    Iterable[PreferenceScoreSuper[T]],
]
