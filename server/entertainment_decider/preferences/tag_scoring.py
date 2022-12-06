from __future__ import annotations

import base64
import dataclasses
from dataclasses import dataclass
import gzip
import json
import math
from typing import Dict, Iterable, List, TypeAlias, Union

from ..extras import Chain
from ..models import Tag, Tagable


@dataclass
class PreferenceScore:
    points: Dict[Tag, float] = dataclasses.field(default_factory=lambda: {})

    def __add__(self, other: PreferenceScoreCompatible) -> PreferenceScore:
        return (self & other).calculate()

    def __and__(self, other: PreferenceScoreCompatible) -> PreferenceScoreAppender:
        return PreferenceScoreAppender(self, other)

    def __mul__(self, scalar: float) -> PreferenceScore:
        return PreferenceScore(
            {tag: score * scalar for tag, score in self.points.items()}
        )

    def __neg__(self) -> PreferenceScore:
        return self * -1

    @staticmethod
    def max_score_increase(score: float, adapt_count: int) -> float:
        # depends on PreferenceScoreAppender.share_score(_flat)
        return score * adapt_count

    def adapt_score(
        self,
        tagable: Tagable,
        score: float,
        on_hierachy: bool = True,
    ) -> PreferenceScore:
        addition = (
            PreferenceScoreAppender.share_score
            if on_hierachy
            else PreferenceScoreAppender.share_score_flat
        )(tagable, score)
        return (self & addition).calculate()

    def calculate_score(self, object: Tagable) -> float:
        return self.calculate_iter_score(object.all_tags)

    def calculate_iter_score(self, tag_iter: Iterable[Tag]) -> float:
        return math.fsum(self.points.get(tag, 0) for tag in tag_iter)

    @classmethod
    def from_json(cls, data: str) -> PreferenceScore:
        dicts: Dict = json.loads(data)
        return cls({Tag[id]: score for id, score in dicts.items()})

    @classmethod
    def from_base64(cls, in_data: str, encoding: str = "utf-8") -> PreferenceScore:
        return (
            Chain(in_data)
            | (lambda d: d.encode(encoding=encoding))
            | base64.decodebytes
            | gzip.decompress
            | (lambda d: d.decode(encoding=encoding))
            | PreferenceScore.from_json
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


class PreferenceScoreAppender:
    points_list: List[PreferenceScore]

    @staticmethod
    def share_score_flat(obj: Tagable, score: float) -> PreferenceScoreSuper:
        # influences PreferenceScore.max_score_increase
        direct_tags = [tag for tag in obj.direct_tags if tag.use_for_preferences]
        if len(direct_tags) <= 0:
            return PreferenceScoreAppender()
        return PreferenceScore({tag: score / len(direct_tags) for tag in direct_tags})

    @classmethod
    def share_score(cls, obj: Tagable, score: float) -> PreferenceScoreSuper:
        # influences PreferenceScore.max_score_increase
        super_tags = [tag for tag in obj.super_tags if tag.use_for_preferences]
        super_fraction = len(super_tags)
        direct_fraction = super_fraction + 1
        full_fraction = super_fraction + direct_fraction
        single_share = score / full_fraction
        direct_share = cls.share_score_flat(obj, single_share * direct_fraction)
        super_shares = (super_tag.share_score(single_share) for super_tag in super_tags)
        return direct_share & super_shares

    def __init__(self, *args: PreferenceScoreCompatible):
        self.points_list = []
        for preference in args:
            self.__append(preference)

    def __append(self, preference: PreferenceScoreCompatible) -> None:
        if isinstance(preference, PreferenceScore):
            self.points_list.append(preference)
        elif isinstance(preference, PreferenceScoreAppender):
            self.points_list.extend(preference.points_list)
        else:
            for sub_pref in preference:
                self.__append(sub_pref)

    def __and__(self, other: PreferenceScoreCompatible) -> PreferenceScoreAppender:
        return PreferenceScoreAppender(self, other)

    def calculate(self) -> PreferenceScore:
        combined: Dict[Tag, List[float]] = {}
        for preference in self.points_list:
            for tag, score in preference.points.items():
                if tag not in combined:
                    combined[tag] = []
                combined[tag].append(score)
        return PreferenceScore(
            {tag: math.fsum(scores) for tag, scores in combined.items()}
        )


PreferenceScoreSuper: TypeAlias = Union[PreferenceScore, PreferenceScoreAppender]
PreferenceScoreCompatible: TypeAlias = Union[
    PreferenceScoreSuper, Iterable[PreferenceScoreSuper]
]
