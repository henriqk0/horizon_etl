from src.core.logic.lattes_generators import LattesConfigGenerator, LattesListGenerator


def test_lattes_config_generator(tmp_path):
    output_dir = tmp_path / "output"
    cache_dir = tmp_path / "cache"
    config_path = tmp_path / "test.config"

    gen = LattesConfigGenerator()
    gen.generate(str(config_path), str(output_dir), cache_dir=str(cache_dir))

    assert config_path.exists()
    content = config_path.read_text()
    assert f"global-diretorio_de_saida_json = {output_dir}" in content
    assert f"global-diretorio_de_armazenamento_de_cvs = {cache_dir}" in content


def test_lattes_list_generator(tmp_path):
    list_path = tmp_path / "test.list"
    researchers = [
        {"name": "Alice", "lattes_id": "123"},
        {"name": "Bob", "lattes_id": "456"},
    ]

    gen = LattesListGenerator()
    gen.generate_from_db(str(list_path), researchers)

    assert list_path.exists()
    content = list_path.read_text()
    assert "123,Alice" in content
    assert "456,Bob" in content
