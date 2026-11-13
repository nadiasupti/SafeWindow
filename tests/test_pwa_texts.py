"""The mobile app's texts (pwa/src/locales) must follow the safety wording of the app plan (section 4)."""
import json
import re
from pathlib import Path

import pytest

LOCALES = Path(__file__).resolve().parent.parent / "pwa" / "src" / "locales"

# Words that promise more than the data can: a road "cut", a "safe" route or day, a relief date.
FORBIDDEN = {
    "bn": ["নিরাপদ পথ", "শেষ নিরাপদ", "রাস্তা কাটা", "ত্রাণ পৌঁছানোর", "ত্রাণের deadline"],
    "en": ["safe route", "last safe", "road cut", "roads cut", "relief deadline", "aid deadline"],
}


def texts(lang: str) -> dict:
    return json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))


def flat(value) -> list[str]:
    return value if isinstance(value, list) else [value]


@pytest.mark.parametrize("lang", ["bn", "en"])
def test_no_wording_that_promises_safety(lang):
    for key, value in texts(lang).items():
        for text in flat(value):
            for word in FORBIDDEN[lang]:
                assert word.lower() not in text.lower(), f"{lang}.json {key}: {word!r}"


def test_both_languages_have_the_same_keys_and_placeholders():
    bn, en = texts("bn"), texts("en")
    assert set(bn) == set(en)
    for key in en:
        assert type(bn[key]) is type(en[key]), key
        for b, e in zip(flat(bn[key]), flat(en[key])):
            assert set(re.findall(r"\{(\w+)\}", b)) == set(re.findall(r"\{(\w+)\}", e)), key


def test_key_safety_messages_are_present():
    bn = texts("bn")
    assert "মাঠে যাচাই করা হয়নি" in bn["route_caveat"]
    assert "অফিসিয়াল সতর্কবার্তা না" in bn["official_notice"]
    assert "নিশ্চিত তারিখও না" in bn["supply_note"]
    assert bn["shelter_unverified"] == "আশ্রয়কেন্দ্র (যাচাই করা হয়নি)"
