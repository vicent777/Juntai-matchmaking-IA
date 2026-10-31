"""Gerador offline: testes não conectam nem inserem perfis em PostgreSQL."""

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.supervised.dataset import build_dataset
from app.supervised.schemas import InvestorProfile, StartupProfile
from app.supervised.synthetic.export import export_run, validate_exports
from app.supervised.synthetic.generator import Config, behavioral_probability, generate

CUTOFF = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


def uid(value):
    return str(UUID(int=value, version=4))


@pytest.fixture
def profiles():
    investors = [InvestorProfile(id=uid(i+1), usuario={"id": uid(i+1000), "ativo": True},
                                tipoInvestidor="anjo_mentor", segmentosInteresse=["agtech"],
                                estagiosInteresse=["mvp"], modelosInteresse=["b2b"], regioesInteresse=["nordeste"],
                                perfilRisco="moderado", ticketMaximo="50000.00", areasAjuda=["mentoria"])
                 for i in range(12)]
    startups = [StartupProfile(id=uid(i+100), usuario={"id": uid(i+2000), "ativo": True}, statusModeracao="aprovado",
                              segmento="agtech" if i % 2 else "fintech", estagio="mvp", modeloNegocio="b2b",
                              regioesAtuacao=["nordeste"], necessidadesAdicionais=["mentoria"],
                              capitalProcurado="100000.00", numeroClientes=i*10, taxaCrescimentoPct="10.00")
                for i in range(100)]
    return investors, startups


def test_same_seed_is_byte_reproducible_and_source_order_independent(profiles):
    config = Config(42, 1000, CUTOFF)
    first = generate(*profiles, config)
    assert first.model_dump_json() == generate(list(reversed(profiles[0])), list(reversed(profiles[1])), config).model_dump_json()
    assert first.model_dump_json() != generate(*profiles, Config(43, 1000, CUTOFF)).model_dump_json()


def test_existing_ids_only_exact_count_unique_events_and_temporal_consistency(profiles):
    data = generate(*profiles, Config(42, 1000, CUTOFF))
    assert len(data.exposicoes) == 1000
    assert len({e.exposicao_id for e in data.exposicoes}) == 1000
    assert len({e.id for e in data.interacoes}) == len(data.interacoes)
    assert {e.investidor_id for e in data.exposicoes} == {p.id for p in profiles[0]}
    assert {e.startup_id for e in data.exposicoes} <= {p.id for p in profiles[1]}
    first = {}
    for exposure in data.exposicoes:
        assert exposure.ocorrido_em <= CUTOFF
        first.setdefault((exposure.investidor_id, exposure.startup_id), exposure.ocorrido_em)
    for event in data.interacoes:
        assert first[(event.investidor_id, event.startup_id)] < event.ocorrido_em <= CUTOFF
    by_id = {e.exposicao_id: e for e in data.exposicoes}
    for snapshot in data.snapshots:
        assert snapshot.estado_em == by_id[snapshot.exposicao_id].ocorrido_em
    assert data.origem_dados == "sintetica"
    assert data.historico_completo and data.completo_ate == CUTOFF


def test_labels_are_from_existing_pipeline_and_not_forced_balanced(profiles):
    data = generate(*profiles, Config(42, 1000, CUTOFF))
    result = build_dataset(data)
    targets = [r.rotulo.target for r in result.registros]
    assert set(targets) == {0, 1, None}
    assert targets.count(0) > targets.count(1)
    assert len(result.registros) == 850
    assert not {"snapshot_ausente", "snapshot_invalido", "evento_futuro", "interacao_sem_exposicao"} & {q.codigo for q in result.qualidade}
    interests = {(e.investidor_id, e.startup_id): e for e in data.interacoes if e.tipo_evento == "interesse_demonstrado"}
    for row in result.registros:
        t0 = datetime.fromisoformat(row.metadados["t0"])
        pair = (UUID(row.metadados["investidor_id"]), UUID(row.metadados["startup_id"]))
        event = interests.get(pair)
        if row.rotulo.target == 1:
            assert event and t0 < event.ocorrido_em <= min(CUTOFF, t0 + timedelta(days=30))
        elif row.rotulo.target == 0:
            assert t0 + timedelta(days=30) <= CUTOFF
            assert not event or event.ocorrido_em > t0 + timedelta(days=30)
        else:
            assert t0 + timedelta(days=30) > CUTOFF


def test_future_behavior_never_changes_features(profiles):
    data = generate(*profiles, Config(42, 150, CUTOFF))
    result = build_dataset(data)
    changed = data.model_copy(deep=True)
    changed.interacoes = []
    other = build_dataset(changed)
    assert [r.features for r in result.registros] == [r.features for r in other.registros]
    assert [r.rotulo for r in result.registros] != [r.rotulo for r in other.registros]


def test_behavior_has_independent_latent_tastes_and_noise(profiles):
    investor, startup = profiles[0][0], profiles[1][1]
    taste = {"sector": "agtech", "stage": "mvp", "model": "b2b", "bias": 0, "growth": 0.8}
    baseline = behavioral_probability(investor, startup, taste, 0)
    assert 0 < baseline < 1
    assert baseline != behavioral_probability(investor, startup, {**taste, "sector": "edtech"}, 0)
    assert baseline != behavioral_probability(investor, startup, taste, 0.6)


def test_export_roundtrip_integrity_and_training_excludes_ids_and_nulls(profiles, tmp_path):
    config = Config(42, 120, CUTOFF)
    data = generate(*profiles, config)
    output = tmp_path / "run"
    summary = export_run(output, data, profiles, {}, config, {"origem_dados": "sintetica"})
    validated = validate_exports(output)
    assert validated["training_rows"] == summary["pares_unicos"] - summary["labels_indefinidos"]
    for line in (output / "training.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        assert set(row) == {"features", "target"}
        assert row["target"] in (0, 1)
        assert all(key.split('.')[-1] not in {"id", "investidor_id", "startup_id", "target", "ocorrido_em", "probabilidade", "evento_interesse_id"} for group in row["features"].values() for key in group)
    with pytest.raises(FileExistsError):
        export_run(output, data, profiles, {}, config, {})
    with (output / "training.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("{}\n")
    with pytest.raises(ValueError, match="Integridade"):
        validate_exports(output)


@pytest.mark.parametrize("count", [0, -1, True, 1.5])
def test_invalid_count(count):
    with pytest.raises(ValueError):
        Config(42, count, CUTOFF)


def test_timezone_empty_pools_and_duplicate_profiles(profiles):
    with pytest.raises(ValueError, match="timezone"):
        Config(42, 1, datetime(2026, 10, 30))
    with pytest.raises(ValueError, match="perfis"):
        generate([], profiles[1], Config(42, 1, CUTOFF))
    with pytest.raises(ValueError, match="duplicados"):
        generate(profiles[0] * 2, profiles[1], Config(42, 1, CUTOFF))


def test_small_pair_pool_repeats_without_duplicate_dataset_rows(profiles):
    data = generate(profiles[0][:1], profiles[1][:1], Config(42, 10, CUTOFF))
    assert len(data.exposicoes) == 10
    assert len(build_dataset(data).registros) == 1


def test_generator_does_not_call_level_1_scoring(profiles, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("O gerador não deve usar o score 1A para decidir interesse")
    monkeypatch.setattr('app.rules.rank', forbidden)
    assert len(generate(*profiles, Config(42, 20, CUTOFF)).exposicoes) == 20


def test_incomplete_history_remains_unlabeled(profiles):
    data = generate(*profiles, Config(42, 100, CUTOFF))
    data.historico_completo = False
    data.completo_ate = None
    rows = build_dataset(data).registros
    assert rows and all(r.rotulo.target is None and r.rotulo.status_rotulo == 'historico_incompleto' for r in rows)


def test_source_rejects_ineligible_invalid_and_insufficient_profiles(profiles):
    pytest.importorskip('psycopg2')
    from app.supervised.features import INV_NUM, INV_CAT, INV_MULTI
    from app.supervised.synthetic.source import read_profiles
    fields = list(dict.fromkeys(('id', *INV_NUM, *INV_CAT, *INV_MULTI)))
    base = profiles[0][0].model_dump()
    records = [base, {**base, 'regioesInteresse': ['nacional']}, {**base, 'segmentosInteresse': []}, base]
    raw = [tuple(record[k] for k in fields) + ('aprovado', n != 3, 'investidor', uid(4000)) for n, record in enumerate(records)]
    class Cursor:
        def execute(self, query):
            self.query = query
        def fetchall(self):
            return raw
    accepted, quality = read_profiles(Cursor(), 'investidores', InvestorProfile, INV_NUM, INV_CAT, INV_MULTI)
    assert len(accepted) == 1
    assert quality['descartados'] == 3
    assert quality['motivos'] == {'contrato_invalido': 1, 'campo_invalido:regioesInteresse': 1, 'informacao_insuficiente': 1, 'inelegivel': 1}


def test_source_connection_enforces_read_only_transaction(tmp_path, monkeypatch):
    driver = pytest.importorskip('psycopg2')
    from app.supervised.synthetic.source import connection
    values = {'DB_HOST': 'localhost', 'DB_PORT': '5433', 'DB_NAME': 'juntai_db', 'DB_USER': 'synthetic', 'DB_PASSWORD': 'test-only'}
    env = tmp_path / '.env'
    env.write_text('\n'.join(k+'='+v for k,v in values.items()), encoding='utf-8')
    for key in values:
        monkeypatch.delenv(key, raising=False)
    calls = {}
    class Connection:
        def set_session(self, **kwargs):
            calls['session'] = kwargs
    def connect(**kwargs):
        calls['connect'] = kwargs
        return Connection()
    monkeypatch.setattr(driver, 'connect', connect)
    connection(env)
    assert calls['connect']['options'] == '-c default_transaction_read_only=on'
    assert calls['session'] == {'readonly': True, 'isolation_level': 'REPEATABLE READ'}
