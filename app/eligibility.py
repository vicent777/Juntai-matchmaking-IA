"""Elegibilidade operacional declarada pelo backend; não substitui autorização."""
from app.schemas import InvestidorEntrada, StartupEntrada, ResultadoElegibilidade


def evaluate_eligibility(investor: InvestidorEntrada, startup: StartupEntrada) -> ResultadoElegibilidade:
    verified, blockers, missing = [], [], []
    # O formato dos UUIDs já foi validado pelo contrato Pydantic.
    verified.append("IDs de Investidor e Startup com formato UUID válido.")
    for label, profile in (("investidor", investor), ("startup", startup)):
        user = profile.usuario
        if user is None or user.id is None:
            missing.append(f"{label}: Usuario.id não informado para distinguir do ID do perfil.")
        elif profile.id == user.id:
            blockers.append(f"{label}: ID do perfil igual ao respectivo Usuario.id.")
        else:
            verified.append(f"{label}: ID do perfil distinto do respectivo Usuario.id.")
        if user is None or user.ativo is None:
            missing.append(f"{label}: atividade do usuário não informada.")
        elif not user.ativo:
            blockers.append(f"{label}: usuário explicitamente inativo.")
        else:
            verified.append(f"{label}: usuário explicitamente ativo.")
    if startup.statusModeracao is None:
        missing.append("startup: moderação não informada.")
    elif startup.statusModeracao != "aprovado":
        blockers.append(f"startup: moderação {startup.statusModeracao}, diferente de aprovado.")
    else:
        verified.append("startup: moderação explicitamente aprovada.")
    state = "inelegivel" if blockers else "indeterminado" if missing else "elegivel"
    return ResultadoElegibilidade(estado=state, verificadas=verified,
                                 impedimentos=blockers, pendencias=missing)
