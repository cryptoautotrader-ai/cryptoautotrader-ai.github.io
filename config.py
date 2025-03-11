"""
Configuration file. Must be version-controlled.

"""

from dataclasses import dataclass


@dataclass
class GeneralParameters:
    DEFAULT_MAX_RAM: int = 256


@dataclass
class Color:
    """Colors to alter console output"""

    PURPLE: str = "\033[95m"
    CYAN: str = "\033[96m"
    DARK_CYAN: str = "\033[36m"
    BLUE: str = "\033[94m"
    GREEN: str = "\033[92m"
    YELLOW: str = "\033[93m"
    RED: str = "\033[91m"
    BOLD: str = "\033[1m"
    ITALIC: str = "\x1B[3m"
    UNDERLINE: str = "\033[4m"
    END: str = "\033[0m"


@dataclass
class TestData:
    __test__ = False
    # TEST DATA (For LLM API. Pandas won't necessarily be so predictable)
    # Data for uptrend
    DEFAULT_DATA_TO_TEST_API_UP = [
        ["2020-03-10 12:04:00", 1, 1, 1, 1, 10],
        ["2020-03-10 12:04:01", 2, 2, 2, 2, 10],
        ["2020-03-10 12:04:02", 3, 3, 3, 3, 10],
        ["2020-03-10 12:04:03", 4, 4, 4, 4, 10],
        ["2020-03-10 12:04:04", 5, 5, 5, 5, 10],
    ]
    # Data for downtrend
    DEFAULT_DATA_TO_TEST_API_DOWN = [
        ["2020-03-10 12:04:00", 10, 10, 10, 10, 10],
        ["2020-03-10 12:04:01", 2, 2, 2, 2, 10],
        ["2020-03-10 12:04:02", 0.3, 0.3, 0.3, 0.3, 10],
        ["2020-03-10 12:04:03", 0.03, 0.03, 0.03, 0.03, 10],
        ["2020-03-10 12:04:04", 0.003, 0.003, 0.003, 0.003, 10],
    ]