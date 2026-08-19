# Renderizadores de documentação (vendorizados)

Copiados do npm sem modificação:

| Arquivo | Pacote | O quê |
|---|---|---|
| `swagger-ui.css` | `swagger-ui-dist@5.17.14` | folha de estilo do swagger-ui |
| `swagger-ui-bundle.js` | `swagger-ui-dist@5.17.14` | o renderizador do `/docs` e do `/api/docs` |
| `redoc.standalone.js` | `redoc@2.1.5` | o renderizador do `/redoc` |

**Por que versionado e não por CDN:** esta documentação existe para continuar
no ar quando o serviço de demonstração não está. Buscar o renderizador num
terceiro devolveria a página à mesma classe de problema — só que com outro
dono.

**O serviço usa estes mesmos arquivos.** O Dockerfile os copia para
`/swagger-ui` e a aplicação os serve; `/docs`, `/api/docs` e `/redoc` apontam
para lá.
Até 08/2026 o serviço buscava na unpkg.com, com a justificativa de que "a rede
já é premissa" — e a premissa estava errada: alcançar a API não implica
alcançar a unpkg. Este produto é **self-hosted**, em rede que libera saída
**host a host** (é o que o `examples/oracle/acl_setup.sql` configura). Onde a
saída não inclui a unpkg, a página abria com o cabeçalho da plataforma e o
Swagger não renderizava — em branco, sem erro nenhum.

A CDN continua como plano B, com **versão pinada**, para quem roda do checkout
sem `docs/` (é de lá que estes arquivos vêm, e o `.dockerignore` corta o
diretório por padrão).

Licenças: Apache-2.0 (swagger-api/swagger-ui) e MIT (Redocly/redoc).
Atualizar = baixar a versão nova e trocar o arquivo.
