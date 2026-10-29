"""Target independente das features e dos scores de compatibilidade."""

from app.supervised.schemas import Label


def build_target(t0, fim_janela, data_corte, interactions, historico_completo):
    interests = sorted(
        (e for e in interactions if e.tipo_evento == "interesse_demonstrado" and e.ocorrido_em <= data_corte),
        key=lambda e: (e.ocorrido_em, e.id),
    )
    if interests and interests[0].ocorrido_em <= t0:
        return Label(target=None, status_rotulo="interesse_previo", evento_interesse_id=interests[0].id)
    # Sem histórico anterior completo, nem a primeira conversão pode ser garantida.
    if not historico_completo:
        return Label(target=None, status_rotulo="historico_incompleto")
    if interests and interests[0].ocorrido_em <= fim_janela:
        return Label(target=1, status_rotulo="positivo", evento_interesse_id=interests[0].id)
    if data_corte >= fim_janela:
        return Label(target=0, status_rotulo="negativo")
    return Label(target=None, status_rotulo="censurado")
