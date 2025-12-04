# app/services/pricing.py
from __future__ import annotations

from typing import Iterable, Sequence, Tuple, List

from app.models.event_option import EventOption


def calculate_event_price(
    all_options: Sequence[EventOption],
    selected_option_ids: Iterable[int],
) -> Tuple[int, List[EventOption]]:
    """
    Berechne Gesamtpreis und die tatsächlich berechneten Optionen.

    :param all_options: Alle aktiven Optionen für das Event
    :param selected_option_ids: Option-IDs, die der Client gewählt hat (Travel/Ticket/etc.)
    :return: (total_price_cents, charged_options)
    """
    id_set = {int(o_id) for o_id in selected_option_ids}

    required_options = [o for o in all_options if o.is_required]
    selected_optional = [
        o
        for o in all_options
        if not o.is_required and o.is_selectable and o.id in id_set
    ]

    charged_options = required_options + selected_optional
    total = sum(o.price_cents for o in charged_options)

    return total, charged_options
