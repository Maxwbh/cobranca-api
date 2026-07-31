<!--
Obrigado por contribuir com a Cobranca-API!
Preencha o que se aplica e apague o resto — PR pequeno e focado é revisado mais rápido.
Convenções completas: CONTRIBUTING.md
-->

## 📝 O que muda

<!-- Uma descrição do problema resolvido ou da funcionalidade adicionada. -->

Fecha #

## 🏷️ Tipo

- [ ] `[FIX]` Correção de bug (não quebra contrato)
- [ ] `[FEAT]` Nova funcionalidade (não quebra contrato)
- [ ] `[BREAKING]` Mudança que quebra o contrato da API
- [ ] `[DOCS]` Só documentação
- [ ] `[REFACTOR]` Refatoração interna, sem mudança de comportamento
- [ ] `[TEST]` Só testes
- [ ] `[CHORE]` Build, CI, dependências

## 🏦 Alcance

- [ ] Caminho **registrado** (provider REST do banco — C6, Sicoob, …)
- [ ] Caminho **offline** (engine pyCobrança — boleto, CNAB, carnê, OFX)
- [ ] Ambos / transversal (auth, cofre, jobs, webhooks, observabilidade)

Bancos afetados: <!-- ex: C6 (336), Sicoob (756), todos, nenhum -->

## ✅ Checklist

- [ ] `cd gateway && PYTHONPATH=. pytest` passa
- [ ] Endpoint novo/alterado tem cobertura na coleção Postman (`python postman/check_coverage.py` = 100%)
- [ ] Specs OpenAPI continuam válidas (o CI valida a 3.0 offline e a 3.1 do gateway)
- [ ] `CHANGELOG.md` atualizado em **[Não lançado]**
- [ ] Documentação atualizada (`docs/`, `README.md`) quando o comportamento visível mudou
- [ ] **Nenhum segredo, certificado, `.pfx`, token ou dado real de cliente** no diff

## 🧪 Como testar

<!-- Comandos, payload de exemplo, resposta esperada. -->

```bash
```

## 💥 Quebra de contrato

<!-- Se marcou [BREAKING]: o que quebra, por quê, e como migrar. Senão, "N/A". -->

N/A
