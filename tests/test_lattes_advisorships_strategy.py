from src.core.logic.strategies.lattes_advisorships import (
    LattesAdvisorshipMappingStrategy,
)


def test_lattes_strategy_sets_parent_title_and_best_effort_flag():
    strategy = LattesAdvisorshipMappingStrategy("Maria Silva")
    mapped = strategy.map_row(
        {
            "title": "Uso de Redes Neurais para Classificação de Sinais",
            "status": "Concluded",
            "start_year": 2020,
            "end_year": 2022,
            "student_name": "João Souza",
            "nature": "mestrado",
            "type": "Master's Thesis",
        }
    )

    assert mapped["model_class"].__name__ == "Advisorship"
    assert mapped["initiative_type_name"] == "Advisorship"
    assert mapped["parent_title"] == "Uso de Redes Neurais para Classificação de Sinais"
    assert mapped["create_parent_if_missing"] is False
    assert mapped["description"] == "Master's Thesis"
    assert mapped["coordinator_name"] == "Maria Silva"
    assert "master s thesis" in mapped["identity_key"]
    assert "uso de redes neurais para classificacao de sinais" in mapped["identity_key"]


def test_lattes_strategy_description_falls_back_to_type_name():
    strategy = LattesAdvisorshipMappingStrategy("Maria Silva")
    mapped = strategy.map_row(
        {
            "title": "Título",
            "status": "Active",
            "start_year": 2021,
            "end_year": None,
            "student_name": "Ana",
            "nature": "iniciação científica",
            "type_name": "Scientific Initiation",
        }
    )

    assert mapped["description"] == "Scientific Initiation"
    assert mapped["create_parent_if_missing"] is False
    assert mapped["parent_title"] == "Título"
