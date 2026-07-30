# BrCobrança (Ruby) — engine offline DESCONTINUADA

> **Status: descontinuado na versão 2.0.0** (2026-07-23).

Até a versão 1.5.0, a superfície offline (`/api/*`) desta plataforma era servida
pela gem Ruby [brcobranca](https://github.com/Maxwbh/brcobranca) (fork @maxwbh,
com Banco C6, PIX e templates Prawn), executada como processo separado e depois
como sidecar embutido.

Na **versão 2.0.0** a plataforma passou a ser **100% Python**: a geração de
boleto, CNAB 240/400, carnê e PIX é feita **nativamente** pela engine
[pyCobrança](https://github.com/Maxwbh/pyCobranca), dentro do próprio processo
FastAPI. Não há mais Ruby, Gemfile, Puma ou GhostScript no runtime.

- Engine atual: [`docs/README.md`](../README.md) · Swagger offline `/api/docs`
- Histórico da migração: [roadmap-migracao-servico-unico.md](./roadmap-migracao-servico-unico.md)
- Gem original (referência): https://github.com/Maxwbh/brcobranca
