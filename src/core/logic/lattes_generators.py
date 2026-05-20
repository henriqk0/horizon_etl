
from typing import List, Dict


class LattesConfigGenerator:
    """
    Generates the configuration file for scriptLattes.
    """

    def generate(
        self,
        config_path: str,
        output_dir: str,
        list_path: str = "lattes.list",
        cache_dir: str | None = None,
    ) -> None:
        """
        Generates the configuration file.

        Args:
            config_path: Absolute path where the .config file will be saved.
            output_dir: Directory where scriptLattes should save its output (JSONs).
            list_path: Path to the input list file.
            cache_dir: Directory where scriptLattes stores raw HTML curricula.
        """
        cache_line = ""
        if cache_dir:
            cache_line = f"global-diretorio_de_armazenamento_de_cvs = {cache_dir}\n"

        config_content = f"""  # Arquivo de configuracao gerado automaticamente
global-nome_do_grupo = Lattes Group
global-diretorio_de_saida = {output_dir}
{cache_line}global-email_do_admin = admin@example.com
global-idioma = PT
global-itens_desde_o_ano = 1950
global-itens_ate_o_ano = 2100
global-itens_por_pagina = 1000
global-producao_bibliografica-itens = artigo,livro,capitulo,texto,trabalho-completo,resumo-expandido,resumo-congresso,apresentacao-trabalho,outro
global-producao_tecnica-itens = software,patente,desenho-industrial,produto-tecnologico,processo-tecnica,trabalho-tecnico,outro
global-producao_artistica-itens = producao
global-identificacao_dos_grupos_de_pesquisa = SIM
global-arquivo_de_entrada = {list_path}
global-arquivo_de_entrada_de_grupos =
global-diretorio_de_saida_json = {output_dir}
"""
        with open(config_path, "w") as f:
            f.write(config_content.strip())


class LattesListGenerator:
    """
    Generates the list file for scriptLattes containing researchers' Lattes IDs.
    """

    def generate_from_db(self, list_path: str, researchers: List[Dict]) -> None:
        """
        Generates the list file from a list of researcher dictionaries.

        Args:
            list_path: Absolute path where the .list file will be saved.
            researchers: List of dicts, each must have 'name' and 'lattes_id'.
        """
        lines = []
        for r in researchers:
            lattes_id = r.get("lattes_id")
            name = r.get("name")
            if lattes_id and name:
                lines.append(f"{lattes_id},{name}")

        with open(list_path, "w") as f:
            f.write("\n".join(lines))
