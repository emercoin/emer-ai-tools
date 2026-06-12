### Todo

- [ ] Сделать web-интефейс к emercoin core docker  

#### Gateway — hardening перед публичным MVP
- [x] **Разделить gateway на два слоя** — `adapter` (RPC↔REST, без IAM) и `edge`
      (auth/ratelimit, HTTP-клиент адаптера). Compose в `deploy/` с профилями
      dev|prod; адаптер за `X-Internal-Key` в проде (готово к разносу на хосты).
- [ ] **Hot-wallet split** (паттерн бирж): маленький spending-кошелёк, регулярно
      пополняемый из холодной treasury; не держать весь баланс на ключе, который
      подписывает каждую запись.
- [ ] Лимит расхода EMC/час + alerting на аномальный темп записей.
  - [ ] Ротация операционного адреса; публичная политика хранения средствС
        (доверие важнее юрлица — слой 2 «надёжность без юрлица»).
- [x] GitHub OAuth вместо raw-token login; JWT secret ≥32 байт. Device-flow +
      web-flow реализованы и **развёрнуты на проде** (`ai.emercoin.com`): браузерный
      вход на `/login`, callback с сессионным токеном; статический корпус (index/login/
      css) раздаёт Caddy, динамику — edge. Device-flow e2e подтверждён через CF
      (запись в mainnet). raw-token остаётся за `EDGE_DEV_LOGIN_ENABLED` (в проде off).
- [x] Публикация adapter-образа как `emercoin/rest-api` (Docker Hub) — CI
      `.github/workflows/publish-rest-api.yml` на тег `rest-api-v*` (disjoint c
      node-пайплайном). Опубликовано: `emercoin/rest-api:0.0.1` + `latest`
      (amd64+arm64) по тегу `rest-api-v0.0.1`.
- [ ] Расширение identity-namespace за пределы GitHub: `ai:dns:<domain>`,
      `ai:did:<method>:<id>` — нейтральные корни доверия.

### Done ✓

- [x] **Node-образ через CI** (`emercoin/core`): воркфлоу `.github/workflows/publish-node.yml`
      (триггер `node-v*`, amd64, версия из node/Dockerfile, dispatch→`<ver>-test`).
      Dockerfile модернизирован: multi-stage debian:bookworm-slim, +emercoin-cli,
      дефолтный CMD = запуск ноды (был bash). Релиз `node-v0.8.5` опубликован →
      официальный `emercoin/core:0.8.5` + `latest` теперь slim **31MB** (был ~102MB ubuntu).
      ВЫЯСНЕНО: GPG-верификация тарбола невозможна — релизы emercoin на GitHub без
      подписей (.asc/SHA256SUMS нет), а emercoin.pub — EC-ключ P-256 `role: emercoin`
      (PKI/NVS), не релизный. Опц. альтернатива: пин SHA256 тарбола (TOFU) —
      `c4b0f4551956a14e33ebe7f9d88479db3a0b92fd20649b8b4a46f7c69ea68db0` для 0.8.5.
- [x] Создать docker для Emercoin  
