import pytest
from src.normalization.name_normalizer import (
    clean_and_normalize_name,
    get_name_tokens,
    remove_single_letter_initials
)
from src.normalization.vehicle_normalizer import vehicle_normalizer
from src.normalization.date_normalizer import date_normalizer

def test_name_normalizer_cleaning():
    assert clean_and_normalize_name("MR. PARIKSHIT   PANCHAL") == "PARIKSHIT PANCHAL"
    assert clean_and_normalize_name("Parikshit-Panchal") == "PARIKSHIT PANCHAL"
    assert clean_and_normalize_name("SMT. PRIYA SHARMA") == "PRIYA SHARMA"
    assert clean_and_normalize_name("Shri Amit Kumar Patel") == "AMIT PATEL"

def test_name_token_sorting():
    tokens1 = get_name_tokens("Parikshit Panchal")
    tokens2 = get_name_tokens("Panchal Parikshit")
    assert tokens1 == tokens2 == ["PANCHAL", "PARIKSHIT"]

def test_initials_removal():
    assert remove_single_letter_initials("PARIKSHIT A PANCHAL") == "PARIKSHIT PANCHAL"
    assert remove_single_letter_initials("R. SHARMA") == "SHARMA"

def test_vehicle_normalizer_mappings():
    # 2 wheeler mappings
    assert vehicle_normalizer.normalize("MCWG") == "2 wheeler"
    assert vehicle_normalizer.normalize("m-cycle") == "2 wheeler"
    assert vehicle_normalizer.normalize("Motor Cycle") == "2 wheeler"
    assert vehicle_normalizer.normalize("Scooter") == "2 wheeler"
    assert vehicle_normalizer.normalize("2 wheeler") == "2 wheeler"

    # Car mappings
    assert vehicle_normalizer.normalize("LMV") == "car"
    assert vehicle_normalizer.normalize("Light Motor Vehicle") == "car"
    assert vehicle_normalizer.normalize("motor car") == "car"
    assert vehicle_normalizer.normalize("car") == "car"

    # Truck mappings (including LGV)
    assert vehicle_normalizer.normalize("HGV") == "truck"
    assert vehicle_normalizer.normalize("LGV") == "truck"
    assert vehicle_normalizer.normalize("Heavy Goods Vehicle") == "truck"
    assert vehicle_normalizer.normalize("truck") == "truck"

    # 3 wheeler mappings
    assert vehicle_normalizer.normalize("auto") == "3 wheeler"
    assert vehicle_normalizer.normalize("Three Wheeler") == "3 wheeler"
    assert vehicle_normalizer.normalize("3 wheeler") == "3 wheeler"

    # Unrecognized classes
    assert vehicle_normalizer.normalize("AEROPLANE") is None
    assert vehicle_normalizer.normalize("") is None

def test_date_normalizer():
    assert date_normalizer.normalize("12/05/1995") == "1995-05-12"
    assert date_normalizer.normalize("12-05-1995") == "1995-05-12"
    assert date_normalizer.normalize("1995/05/12") == "1995-05-12"
    assert date_normalizer.normalize("1995") == "1995"
