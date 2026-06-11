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
- [ ] Ротация операционного адреса; публичная политика хранения средств
      (доверие важнее юрлица — слой 2 «надёжность без юрлица»).
- [~] GitHub OAuth вместо raw-token login; JWT secret ≥32 байт. Device-flow +
      web-flow (за флагом) реализованы в edge; raw-token за `EDGE_DEV_LOGIN_ENABLED`.
      Device-flow проверен e2e с реальным client_id; MCP `login()`+`login_poll()`
      через device-flow готовы. Осталось: прод web-callback на домене (ai.emercoin.com).
- [~] Публикация adapter-образа как `emercoin/rest-api` (Docker Hub) — CI
      `.github/workflows/publish-rest-api.yml` на тег `v*`; standalone-сборка из
      `./adapter` проверена (healthz/docs). Осталось: завести repo-секреты
      DOCKERHUB_USERNAME + DOCKERHUB_TOKEN и запушить тег `v0.0.1` (или ручной
      workflow_dispatch → latest), чтобы образ реально лёг в реестр.
- [ ] Расширение identity-namespace за пределы GitHub: `ai:dns:<domain>`,
      `ai:did:<method>:<id>` — нейтральные корни доверия.

### In Progress
- [ ] **Node-образ через CI** (`emercoin/core`): воркфлоу `.github/workflows/publish-node.yml`
      готов (триггер `node-v*`, amd64, версия из node/Dockerfile, dispatch→`<ver>-test`).
      Dockerfile модернизирован: multi-stage debian:bookworm-slim, **237MB→87MB**, +emercoin-cli,
      дефолтный CMD = запуск ноды (был bash); собран и проверен живьём (daemon стартует,
      getinfo, синк с пиром). ⚠ публикует ОФИЦИАЛЬНЫЙ образ и меняет поведение (base/CMD) —
      перед релизным тегом прогнать `workflow_dispatch` (`:0.8.5-test`) и сверить с upstream.
      Опц.: GPG-верификация тарбола по emercoin.pub в builder-стадии.
    

### Done ✓
- [x] Создать версию FS (fast start) образ Emercoin с синхронизированным за 7 последних лет блокчейном.
- [x] Создать docker для Emercoin  
