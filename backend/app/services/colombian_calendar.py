from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache


@dataclass(frozen=True)
class OperationDateInfo:
    fecha: date
    es_sabado: bool
    es_domingo: bool
    es_festivo_nacional: bool
    nombre_festivo: str | None
    es_dia_operacion: bool


# Festivos nacionales de fecha fija (no se trasladan al lunes siguiente)
_FIXED_HOLIDAYS: tuple[tuple[int, int, str], ...] = (
    (1, 1, "Año Nuevo"),
    (5, 1, "Día del Trabajo"),
    (7, 20, "Día de la Independencia"),
    (8, 7, "Batalla de Boyacá"),
    (12, 8, "Inmaculada Concepción"),
    (12, 25, "Navidad"),
)

# Festivos nacionales sujetos a la Ley 51 de 1983 (Ley Emiliani):
# si no caen en lunes, se trasladan al lunes inmediatamente siguiente.
_EMILIANI_HOLIDAYS: tuple[tuple[int, int, str], ...] = (
    (1, 6, "Día de los Reyes Magos"),
    (3, 19, "Día de San José"),
    (6, 29, "San Pedro y San Pablo"),
    (8, 15, "La Asunción de la Virgen"),
    (10, 12, "Día de la Raza"),
    (11, 1, "Todos los Santos"),
    (11, 11, "Independencia de Cartagena"),
)


def calculate_easter_sunday(year: int) -> date:
    """Calcula el Domingo de Pascua para un año gregoriano (algoritmo de Meeus/Jones/Butcher)."""
    if year < 1583:
        raise ValueError("El cálculo gregoriano de Pascua requiere un año >= 1583.")
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def move_to_next_monday(target_date: date) -> date:
    """Traslada una fecha al lunes siguiente si no cae en lunes (Ley 51 de 1983)."""
    weekday = target_date.weekday()  # 0 = lunes ... 6 = domingo
    if weekday == 0:
        return target_date
    return target_date + timedelta(days=7 - weekday)


@lru_cache(maxsize=64)
def get_colombian_holidays(year: int) -> dict[date, str]:
    """Devuelve el mapa {fecha: nombre_festivo} de los 18 festivos nacionales oficiales de Colombia."""
    holidays: dict[date, str] = {}

    def _register(holiday_date: date, name: str) -> None:
        if holiday_date in holidays and name not in holidays[holiday_date]:
            holidays[holiday_date] = f"{holidays[holiday_date]} / {name}"
        else:
            holidays[holiday_date] = name

    # 1. Festivos de fecha fija
    for month, day, name in _FIXED_HOLIDAYS:
        _register(date(year, month, day), name)

    # 2. Festivos trasladables por Ley Emiliani
    for month, day, name in _EMILIANI_HOLIDAYS:
        observed = move_to_next_monday(date(year, month, day))
        _register(observed, name)

    # 3. Festivos móviles respecto al Domingo de Pascua
    easter = calculate_easter_sunday(year)
    _register(easter - timedelta(days=3), "Jueves Santo")
    _register(easter - timedelta(days=2), "Viernes Santo")
    _register(move_to_next_monday(easter + timedelta(days=39)), "Ascensión del Señor")
    _register(move_to_next_monday(easter + timedelta(days=60)), "Corpus Christi")
    _register(move_to_next_monday(easter + timedelta(days=68)), "Sagrado Corazón de Jesús")

    return dict(sorted(holidays.items()))


def get_holiday_name(target_date: date) -> str | None:
    """Devuelve el nombre del festivo nacional oficial en Colombia o None si no es festivo."""
    return get_colombian_holidays(target_date.year).get(target_date)


def is_colombian_holiday(target_date: date) -> bool:
    """Indica si la fecha corresponde a un festivo nacional oficial de Colombia."""
    return target_date in get_colombian_holidays(target_date.year)


def is_weekend(target_date: date) -> bool:
    """Indica si la fecha es sábado (5) o domingo (6)."""
    return target_date.weekday() in (5, 6)


def is_valid_operation_date(target_date: date) -> bool:
    """Determina si una fecha es válida para operación (sábado, domingo o festivo nacional colombiano)."""
    return is_weekend(target_date) or is_colombian_holiday(target_date)


def inspect_operation_date(target_date: date) -> OperationDateInfo:
    """Retorna el desglose completo de clasificación operativa de una fecha."""
    weekday = target_date.weekday()
    es_sabado = weekday == 5
    es_domingo = weekday == 6
    nombre_festivo = get_holiday_name(target_date)
    es_festivo = nombre_festivo is not None
    return OperationDateInfo(
        fecha=target_date,
        es_sabado=es_sabado,
        es_domingo=es_domingo,
        es_festivo_nacional=es_festivo,
        nombre_festivo=nombre_festivo,
        es_dia_operacion=es_sabado or es_domingo or es_festivo,
    )
