def pytest_addoption(parser):
    parser.addoption("--run-real-embeddings", action="store_true", default=False,
                     help="Executa integração real em CPU; pode baixar pesos do Hugging Face.")
