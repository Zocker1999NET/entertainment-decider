from __future__ import annotations

from datetime import datetime, timedelta
from functools import cache
from itertools import chain
import logging
import math
from typing import Callable, Iterable, List, Optional, Sequence, Set, TypeAlias

from pony import orm

from .tag_scoring import PreferenceScore
from ..models import (
    MediaCollection,
    MediaElement,
    Tag,
    db,
    get_all_elements_tags_recursive,
)


ScoreCalc: TypeAlias = Callable[["MediaElement"], float]


def generate_preference_list(
    object_gen: Callable[[], List[MediaElement]],
    score_adapt: float,
    base: Optional[PreferenceScore] = None,
    limit: Optional[int] = None,
) -> List[MediaElement]:
    element_list: Set[MediaElement] = set(object_gen())
    preference = base if base is not None else PreferenceScore()
    now = datetime.now()  # reference time

    def add_tags_for_collections() -> None:
        collections: Iterable[MediaCollection] = MediaCollection.select()
        for coll in collections:
            tag = Tag.gen_temporary_tag(
                hint=f"Collection: {coll.title}",
            )
            coll.tag_list.add(tag)

    def add_tags_for_extractor_names() -> None:
        @cache
        def get_extractor_tag(extractor_name: str) -> Tag:
            return Tag.gen_temporary_tag(
                hint=f"Extractor: {extractor_name}",
            )

        for element in element_list:
            element.tag_list.add(get_extractor_tag(element.extractor_name))

    add_tags_for_collections()
    add_tags_for_extractor_names()
    orm.flush()  # flush after custom tags

    # score calc

    elem_tag_map = get_all_elements_tags_recursive()

    def all_tags(element: MediaElement) -> Sequence[Tag]:
        return elem_tag_map.get(element.id, [])

    # TODO prepare static score in parallel (or cache it in DB for longer)
    @cache
    def gen_statis_score(element: MediaElement) -> float:
        pinned_collections = orm.count(
            link for link in element.collection_links if link.collection.pinned
        )
        # reference_date = orm.max((elem_link.element.release_date for coll_link in element.collection_links for elem_link in coll_link.collection.media_links if coll_link.collection.watch_in_order and not elem_link.element.skip_over), default=element.release_date)
        # reference_date = max((l.collection.last_release_date_to_watch for l in element.collection_links if l.collection.watch_in_order), default=element.release_date)
        reference_date = element.release_date
        age_nerf = (
            (
                max(-0.5, math.log((now - reference_date) / timedelta(days=14)) - 1)
                if reference_date < now  # possible on yet to release media
                else -0.5
            )
            # nerf the nerf when pinned or started to prevent hiding
            * 0.1
            if (pinned_collections > 0) or element.started
            else 1
        )
        # avg_rel = element.average_release_per_week or element.left_length
        # avg_rel = element.left_length
        all_nerfs = (
            # by id to make sorting consistent
            (10**-8) * math.log(element.id + 1000),
            # for age of media (newer is better)
            age_nerf,
            # for average length in relevant collections / length of video itself
            # max(0, (math.log(avg_rel + 1) - 5) / 2) if avg_rel else 0
        )
        all_buffs = (
            # for already began to watch
            2 if element.started else 0,
            # for count of tags (more is better)
            0.5 * math.log(len(all_tags(element)) + 1),
            # for being in pinned collections
            3 * math.log(pinned_collections + 1),
        )
        return math.fsum(chain(all_nerfs, (-val for val in all_buffs)))

    def gen_score(element: MediaElement) -> float:
        static_score = gen_statis_score(element)
        pref_score = preference.calculate_iter_score(all_tags(element))
        return static_score + pref_score

    # pre filter list
    # - elements which have a too low current score may never possible appear
    # TODO add test that this does not change end result
    def pre_filter_list_by_score(elem_list: Set[MediaElement]) -> Set[MediaElement]:
        elem_count = len(elem_list)
        if limit is None or elem_count <= limit:
            return elem_list
        # cache pref score for this
        gen_pre_score = cache(gen_score)
        # biggest possible score increase by adaption
        max_score_inc = preference.max_score_increase(
            score=score_adapt,
            adapt_count=limit,
        )
        logging.debug(f"Max adaption possible: {max_score_inc}")
        # differenciate adapted buffing and adapted nerfing
        without_max_adapt: ScoreCalc = lambda elem: gen_pre_score(elem)
        with_max_adapt: ScoreCalc = lambda elem: without_max_adapt(elem) + max_score_inc
        is_nerfing = score_adapt >= 0
        if is_nerfing:
            best_case = without_max_adapt
            worst_case = with_max_adapt
        else:  # is buffing
            best_case = with_max_adapt
            worst_case = without_max_adapt
        # (limit)ths best's score in the worst adaption for it
        limitths_best_worst = sorted(worst_case(elem) for elem in elem_list)[limit]
        logging.debug(f"(limit)ths best's worst case score: {limitths_best_worst}")
        # extract worst's element's score in best case as well
        worsts_best = best_case(max(elem_list, key=gen_pre_score))
        logging.debug(f"Worsts best case score is {worsts_best}")
        # check if reducing element count is possible
        if limitths_best_worst < worsts_best:
            # throw away all elements which's best adaption is not better than the (limit)ths one
            ret = {elem for elem in elem_list if best_case(elem) < limitths_best_worst}
            logging.debug(
                f"Prefilter reduced set from {elem_count} to {len(ret)} elements"
            )
            return ret
        logging.debug(f"Prefilter couldn't reduce the element count ({elem_count})")
        return elem_list

    element_list = pre_filter_list_by_score(element_list)

    # gen elements
    res_ids = list[int]()
    while 0 < len(element_list):
        first_element = min(element_list, key=gen_score)
        res_ids.append(first_element.id)
        if limit is not None and limit <= len(res_ids):
            break
        element_list.remove(first_element)
        preference = preference.adapt_score(first_element, score_adapt)

    # revert any changes on DB
    orm.rollback()
    db.execute(f"ALTER TABLE {Tag._table_} AUTO_INCREMENT = 1;")

    # return MediaElements
    return [MediaElement[i] for i in res_ids]
