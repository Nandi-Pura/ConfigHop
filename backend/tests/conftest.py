from pathlib import Path

import pytest

from confighop_core import parse_palo_alto_xml


FIXTURES = Path(__file__).parent / "fixtures" / "paloalto"


@pytest.fixture(scope="module")
def minimal():
    return parse_palo_alto_xml(FIXTURES / "pa_minimal.xml")


@pytest.fixture(scope="module")
def complex_inventory():
    return parse_palo_alto_xml(FIXTURES / "pa_complex_synthetic.xml")
