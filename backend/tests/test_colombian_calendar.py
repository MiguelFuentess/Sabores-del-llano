from __future__ import annotations

from datetime import date

import pytest

from app.services.colombian_calendar import (
    calculate_easter_sunday,
    get_colombian_holidays,
    get_holiday_name,
    inspect_operation_date,
    is_colombian_holiday,
    is_valid_operation_date,
    is_weekend,
    move_to_next_monday,
)


def test_calculate_easter_sunday_known_years():
    assert calculate_easter_sunday(2024) == date(2024, 3, 31)
    assert calculate_easter_sunday(2025) == date(2025, 4, 20)
    assert calculate_easter_sunday(2026) == date(2026, 4, 5)


def test_move_to_next_monday_emiliani_rule():
    # Si ya es lunes, permanece en el mismo lunes
    assert move_to_next_monday(date(2024, 11, 11)) == date(2024, 11, 11)
    # Viernes 1 de noviembre de 2024 -> Lunes 4 de noviembre de 2024
    assert move_to_next_monday(date(2024, 11, 1)) == date(2024, 11, 4)
    # Domingo 1 de noviembre de 2026 -> Lunes 2 de noviembre de 2026
    assert move_to_next_monday(date(2026, 11, 1)) == date(2026, 11, 2)


def test_fixed_national_holidays_are_not_moved():
    # 20 de julio de 2026 cae en lunes, 7 de agosto de 2026 cae en viernes
    assert is_colombian_holiday(date(2026, 1, 1)) is True
    assert get_holiday_name(date(2026, 1, 1)) == "Año Nuevo"

    assert is_colombian_holiday(date(2026, 5, 1)) is True
    assert get_holiday_name(date(2026, 5, 1)) == "Día del Trabajo"

    assert is_colombian_holiday(date(2026, 7, 20)) is True
    assert get_holiday_name(date(2026, 7, 20)) == "Día de la Independencia"

    assert is_colombian_holiday(date(2026, 8, 7)) is True
    assert get_holiday_name(date(2026, 8, 7)) == "Batalla de Boyacá"
    assert is_colombian_holiday(date(2026, 8, 10)) is False  # No se traslada al lunes

    assert is_colombian_holiday(date(2026, 12, 8)) is True
    assert is_colombian_holiday(date(2026, 12, 25)) is True


def test_emiliani_transferred_holidays():
    # Reyes Magos 2026: martes 6 de enero -> se traslada al lunes 12 de enero de 2026
    assert is_colombian_holiday(date(2026, 1, 6)) is False
    assert is_colombian_holiday(date(2026, 1, 12)) is True
    assert get_holiday_name(date(2026, 1, 12)) == "Día de los Reyes Magos"

    # Todos los Santos 2024: viernes 1 de noviembre -> se traslada al lunes 4 de noviembre de 2024
    assert is_colombian_holiday(date(2024, 11, 1)) is False
    assert is_colombian_holiday(date(2024, 11, 4)) is True
    assert get_holiday_name(date(2024, 11, 4)) == "Todos los Santos"

    # Independencia de Cartagena 2024: lunes 11 de noviembre -> permanece en lunes 11
    assert is_colombian_holiday(date(2024, 11, 11)) is True
    assert get_holiday_name(date(2024, 11, 11)) == "Independencia de Cartagena"

    # Independencia de Cartagena 2026: miércoles 11 de noviembre -> lunes 16 de noviembre de 2026
    assert is_colombian_holiday(date(2026, 11, 11)) is False
    assert is_colombian_holiday(date(2026, 11, 16)) is True
    assert get_holiday_name(date(2026, 11, 16)) == "Independencia de Cartagena"


def test_easter_relative_holidays_2026():
    # Pascua 2026: 5 de abril
    # Jueves Santo: 2 de abril, Viernes Santo: 3 de abril
    assert get_holiday_name(date(2026, 4, 2)) == "Jueves Santo"
    assert get_holiday_name(date(2026, 4, 3)) == "Viernes Santo"
    # Ascensión: +39 días (14 mayo) -> lunes 18 de mayo de 2026
    assert get_holiday_name(date(2026, 5, 18)) == "Ascensión del Señor"
    # Corpus Christi: +60 días (4 junio) -> lunes 8 de junio de 2026
    assert get_holiday_name(date(2026, 6, 8)) == "Corpus Christi"
    # Sagrado Corazón: +68 días (12 junio) -> lunes 15 de junio de 2026
    assert get_holiday_name(date(2026, 6, 15)) == "Sagrado Corazón de Jesús"


def test_saturdays_sundays_and_normal_weekdays():
    # Sábado 2 de noviembre de 2024
    sabado = date(2024, 11, 2)
    info_sab = inspect_operation_date(sabado)
    assert is_weekend(sabado) is True
    assert info_sab.es_sabado is True
    assert info_sab.es_domingo is False
    assert info_sab.es_festivo_nacional is False
    assert info_sab.es_dia_operacion is True
    assert is_valid_operation_date(sabado) is True

    # Domingo 3 de noviembre de 2024
    domingo = date(2024, 11, 3)
    info_dom = inspect_operation_date(domingo)
    assert is_weekend(domingo) is True
    assert info_dom.es_sabado is False
    assert info_dom.es_domingo is True
    assert info_dom.es_dia_operacion is True

    # Lunes festivo 4 de noviembre de 2024 (Todos los Santos)
    lunes_festivo = date(2024, 11, 4)
    info_fest = inspect_operation_date(lunes_festivo)
    assert info_fest.es_sabado is False
    assert info_fest.es_domingo is False
    assert info_fest.es_festivo_nacional is True
    assert info_fest.nombre_festivo == "Todos los Santos"
    assert info_fest.es_dia_operacion is True

    # Martes normal 5 de noviembre de 2024
    martes_normal = date(2024, 11, 5)
    info_norm = inspect_operation_date(martes_normal)
    assert info_norm.es_sabado is False
    assert info_norm.es_domingo is False
    assert info_norm.es_festivo_nacional is False
    assert info_norm.nombre_festivo is None
    assert info_norm.es_dia_operacion is False
    assert is_valid_operation_date(martes_normal) is False


def test_year_official_holidays_and_overlapping_holidays():
    holidays_2025 = get_colombian_holidays(2025)
    holidays_2026 = get_colombian_holidays(2026)
    # En 2026 las 18 festividades caen en 18 fechas distintas
    assert len(holidays_2026) == 18
    # En 2025 Sagrado Corazón de Jesús y San Pedro y San Pablo coinciden el lunes 30 de junio (17 fechas únicas)
    assert len(holidays_2025) == 17
    assert (
        holidays_2025[date(2025, 6, 30)]
        == "San Pedro y San Pablo / Sagrado Corazón de Jesús"
    )
