from naratrace.matching.name_normalizer import NameNormalizer


def test_hyphenated_name_keeps_original_and_weighted_variants():
    variants = NameNormalizer().variants("Schultze-Naumburg")
    by_value = {variant.value: variant for variant in variants}

    assert by_value["Schultze-Naumburg"].weight == 1.0
    assert by_value["Schultze Naumburg"].weight < 1.0
    assert by_value["SchultzeNaumburg"].weight < by_value["Schultze Naumburg"].weight
    assert by_value["Schultze"].weight < by_value["SchultzeNaumburg"].weight


def test_umlauts_and_sharp_s_are_normalized_without_losing_variants():
    normalizer = NameNormalizer()
    values = {variant.value for variant in normalizer.variants("Müller")}

    assert normalizer.normalize("Müller") == "muller"
    assert "Müller" in values
    assert "Mueller" in values
    assert "Muller" in values
    assert normalizer.normalize("Groß") == "gross"


def test_nobility_particle_has_weighted_abbreviation_and_removal():
    variants = {variant.value: variant for variant in NameNormalizer().variants("von Müller")}

    assert "von Müller" in variants
    assert "v. Müller" in variants
    assert "Müller" in variants
    assert variants["von Müller"].weight > variants["Müller"].weight
