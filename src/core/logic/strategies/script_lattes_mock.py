import os
import json
import logging

logger = logging.getLogger(__name__)


class ScriptLattesMock:
    """
    Mocks the behavior of the scriptLattes library for development and testing.
    """

    def run(self, config_file: str, list_file: str) -> None:
        """
        Simulates the scriptLattes execution.
        Reads the config to find the output dir, reads the list file to get researchers,
        and generates dummy JSON files for each researcher.
        """
        logger.info(f"Mocking scriptLattes execution with config={config_file} and list={list_file}")

        # 1. Read Config to get output directory
        output_dir = "data"  # Default
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                for line in f:
                    if line.strip().startswith("global-diretorio_de_saida_json"):
                        parts = line.split('=')
                        if len(parts) > 1:
                            output_dir = parts[1].strip()

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # 2. Read List file to get researchers
        if os.path.exists(list_file):
            with open(list_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    parts = line.split(',')
                    if len(parts) >= 2:
                        lattes_id = parts[0].strip()
                        name = parts[1].strip()

                        # 3. Generate Mock JSON
                        self._generate_json(output_dir, lattes_id, name)
        else:
             logger.warning(f"List file not found at {list_file}")

    def _generate_json(self, output_dir: str, lattes_id: str, name: str) -> None:
        """Generates a dummy JSON file for a researcher."""
        data = {
            "idLattes": lattes_id,
            "nome": name,
            "resumo": f"Resumo mock do pesquisador {name}.",
            "producoes": [
                {"titulo": "Artigo Mock 1", "ano": "2024"},
                {"titulo": "Artigo Mock 2", "ano": "2023"}
            ],
            "formacao_academica": [
                {
                    "nome_pt": "Doutorado em Ciência da Computação",
                    "ano_inicio": "2018",
                    "ano_fim": "2022",
                    "nome_instituicao": "Universidade Federal do Espírito Santo",
                    "id_curso": "1",
                    "nome_curso_ingles": "PhD in Computer Science"
                },
                {
                    "nome_pt": "Mestrado em Informática",
                    "ano_inicio": "2016",
                    "ano_fim": "2018",
                    "nome_instituicao": "Universidade Federal do Espírito Santo",
                    "id_curso": "2",
                    "nome_curso_ingles": "MSc in Informatics"
                }
            ],
            "projetos_pesquisa": [
                {
                    "nome": f"Projeto de Pesquisa Mock {lattes_id}",
                    "ano_inicio": "2024",
                    "ano_conclusao": "Atual",
                    "descricao": ["Descrição: Projeto pesquisa mock. Situação: Em andamento. Natureza: Pesquisa."],
                    "integrantes": [{"nome": name, "papel": "Coordenador"}]
                }
            ],
            "projetos_extensao": [
                {
                    "nome": f"Projeto de Extensão Mock {lattes_id}",
                    "ano_inicio": "2023",
                    "ano_conclusao": "2023",
                    "descricao": ["Descrição: Projeto extensão mock. Situação: Concluído. Natureza: Extensão."],
                    "integrantes": [{"nome": name, "papel": "Coordenador"}]
                }
            ],
             "projetos_desenvolvimento": [
                {
                    "nome": f"Projeto de Desenvolvimento Mock {lattes_id}",
                    "ano_inicio": "2025",
                    "ano_conclusao": "Atual",
                    "descricao": ["Descrição: Projeto dev mock. Situação: Em andamento. Natureza: Desenvolvimento."],
                    "integrantes": [{"nome": name, "papel": "Coordenador"}]
                }
            ]
        }

        file_path = os.path.join(output_dir, f"{lattes_id}.json")
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.info(f"Generated mock JSON for {name} ({lattes_id}) at {file_path}")
