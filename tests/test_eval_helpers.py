from eval.run import answer_language, facts_present


def test_answer_language_tells_the_three_demo_languages_apart():
    assert answer_language("The documents do not contain this information.") == "en"
    assert answer_language("Die Dokumente enthalten keine Angabe zum Geschäftsführer.") == "de"
    assert answer_language("LW 9'un yıllık bakımı net 189,00 € ve brüt 224,91 €.") == "tr"
    assert answer_language("10 yıl [1]") == "tr"
    assert answer_language("P1 [1]") is None


def test_facts_accept_typographic_minus_signs():
    assert facts_present("von –25 °C bis +35 °C", ["-25|−25"])
    assert facts_present("down to −25 °C", ["-25"])
    assert facts_present("bis ‑25 °C", ["-25"])  # non-breaking hyphen
    assert not facts_present("up to +35 °C", ["-25|−25"])
