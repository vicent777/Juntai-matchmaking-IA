"""Execute python -m app.supervised.synthetic --help a partir da raiz."""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from app.supervised.schemas import InvestorProfile, StartupProfile
from app.supervised.synthetic.export import export_run
from app.supervised.synthetic.generator import Config, VERSION, generate
from app.supervised.synthetic.source import load_source, verify_source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--exposures", type=int, default=20000)
    parser.add_argument("--cutoff", required=True, help="Relógio simulado fixo ISO 8601, com timezone")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--env-file", type=Path, help="Arquivo de conexão somente de leitura; nunca exportado")
    inputs.add_argument("--profiles", type=Path, help="profiles.json de execução anterior; reprodução offline")
    parser.add_argument("--output", type=Path, required=True, help="Diretório novo dentro de data/synthetic/")
    args = parser.parse_args()
    config = Config(args.seed, args.exposures, datetime.fromisoformat(args.cutoff.replace("Z", "+00:00")))
    output = args.output.resolve()
    root = Path(__file__).resolve().parents[3] / "data" / "synthetic"
    if not output.is_relative_to(root) or output == root:
        parser.error("--output deve ser um diretório novo dentro de data/synthetic/ (ignorado pelo Git)")
    if output.exists():
        parser.error("--output já existe; escolha outro diretório para preservar os artefatos")
    if args.profiles:
        payload = json.loads(args.profiles.read_text(encoding="utf-8"))
        investors = [InvestorProfile.model_validate(p) for p in payload["investidores"]]
        startups = [StartupProfile.model_validate(p) for p in payload["startups"]]
        quality = payload["qualidade"]
        state = None
    else:
        investors, startups, quality, state = load_source(args.env_file)
    data = generate(investors, startups, config)
    digest = hashlib.sha256(data.model_dump_json().encode()).hexdigest()
    repeated = generate(investors, startups, config)
    if hashlib.sha256(repeated.model_dump_json().encode()).hexdigest() != digest:
        raise ValueError("Falha de reprodutibilidade")
    del repeated
    verified = verify_source(args.env_file, state) if state else None
    provenance = {"versao_gerador": VERSION, "origem_dados": "sintetica", "input_sha256": digest,
                  "reprodutibilidade_verificada": True, "banco_inalterado": verified,
                  "estado_fonte": state, "snapshots": "Perfis atuais reutilizados em uma linha do tempo fictícia, sem reconstrução histórica real."}
    summary = export_run(output, data, (investors, startups), quality, config, provenance)
    # A verificação após a exportação cobre toda a execução com PostgreSQL.
    if state:
        verify_source(args.env_file, state)
    print(json.dumps({key: value for key, value in summary.items() if key not in ("proveniencia", "features_ausentes")}, ensure_ascii=False, indent=2))
    print("Artefatos validados em: " + str(output))


if __name__ == "__main__":
    main()
