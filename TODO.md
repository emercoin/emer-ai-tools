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
- [ ] Опубликовать adapter-образ в реестр (`emercoin/agent-adapter:<tag>`) — чтобы
      репо exchanger'а затягивало его как `image:` (adapter+wallet как переиспользуемый узел).
- [ ] Расширение identity-namespace за пределы GitHub: `ai:dns:<domain>`,
      `ai:did:<method>:<id>` — нейтральные корни доверия.

### In Progress
    

### Done ✓
- [x] Создать версию FS (fast start) образ Emercoin с синхронизированным за 7 последних лет блокчейном.
- [x] Создать docker для Emercoin  
