from src.prefect_runtime import bootstrap_local_prefect

bootstrap_local_prefect()

from src.flows.pipelines.unified import full_ingestion_pipeline  # noqa E402


def run_pipeline():
    campus = "Serra"
    print(f"\n>>> Running unified pipeline for campus: {campus}")
    full_ingestion_pipeline(
        campus_name=campus, output_dir="data/exports", generate_etl_report=True
    )
    print("\n>>> Pipeline execution completed with ETL report.")


if __name__ == "__main__":
    run_pipeline()
