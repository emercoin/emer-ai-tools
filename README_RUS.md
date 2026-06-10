![](https://github.com/emercoin/docker/blob/main/docker.png)
# Emercoin Docker
Docker compose image for Emercoin core

### Зачем это всё надо?

Docker позволяет создать изолированный контейнер с кошельком Emercoin внутри и отдельным хранилищем (volume: blockhain_data) для блокчейна. Это дает кроссплатформенность (можно запускать на любой ОС, где можно установить Docker), возможность обновлять версии кошелька Emercoin в "один клик". Использовать в своих проектах функционал кошелька через интерфейс RPC JSON.

Core — классическая версия, просто кошелек Эмеркоина в контейнере. Требуется время для синхронизации с сеть. 

### Для старта с нуля: 
 
Установить [Git](https://github.com/git-guides/install-git) 
Установить [Docker](https://docs.docker.com/engine/install/) и [docker-compose](https://docs.docker.com/compose/install/#install-compose) 

Склонировать репозитарий и перейти в папку с проектом:
```
git clone https://github.com/emercoin/docker emer_docker_wallet && cd emer_docker_wallet
``` 

Переименовать: `emercoin.conf.example` в `emercoin.conf`

**Запустить сборку контейнера с Emercoin:**

для обычной версии Core
```
docker-compose up -d
```
для версии Core Fast Start:
```
docker-compose -f docker-compose-fs.yaml up -d
```

Контейнер запущен, требуется время, чтобы скачать блокчейн (~3-5 часов), но некоторые данные можно получить уже сейчас.
По умолчанию для соединения с контейнером используется порт 6662

- адрес: **127.0.0.1**
- пользователь: **emcrpc**
- пароль: **emcpass**
- метод: **POST** тело запроса пример `{"method": "getinfo" }`

**Сменить пароль в контейнере:**
```
docker-compose exec emc bash changepass.sh
docker-compose restart emc
```

### Как проверить, что контейнер работает нормально?
Нужно отправить **POST** (с помощью Postman, например)
по адресу `http://emcrpc:emcpass@127.0.0.1:6662`, тело запроса `{"method": "getinfo"}`

**В Python:**
```python
import requests

url = "emcrpc:emcpass@127.0.0.1:6662"
payload = {"method": "getinfo"}
headers = { 'Content-Type': 'application/json' }
response = requests.request("POST", url, headers=headers, json=payload)
print(response.json())
```

**В командной строке c помощью Curl:**
(sudo apt-get update && sudo apt-get install curl) - если Curl не установлен
```bash
curl --location --request POST 'emcrpc:emcpass@127.0.0.1:6662' \
--header 'Content-Type: application/json' \
--data-raw '{"method": "getinfo", "params":[]}'
```
если все ок, ответом будет выдача в формате JSON:
```JSON
{
    "result": {
        "fullversion": "v0.7.10emc",
        "version": 71000,
        "protocolversion": 70015,
        "walletversion": 130000,
        "balance": 0.000000,
```

Разблокировать wallet в mint only режим:

```bash
curl --location --request POST 'emcrpc:emcpass@127.0.0.1:6662' \
--header 'Content-Type: application/json' \
--data-raw '{"method": "walletpassphrase", "params":["wallet_password", 100500, true]}'
```

### Управление сборкой

**Остановить контейнер:**
```
docker-compose stop emc
```

**Удалить контейнеры:**
```
docker-compose down
```
При этом база блокчейна, wallet.dat и emercoin.conf не удаляется. Она остается в volume docker_emercoin_data.

**Удалить базу блокчейна**
```
docker volume rm emer_data
```
Внимание! эта команда удаляет так-же wallet.dat


### Для локальной разработки Gateway

Установка через классический pip

Создать venv - `python -m venv venv`

`pip install -r requirements.txt`

Установка через быстрый uv

`pip install uv==0.6.14`

```bash
uv venv venv --python 3.10
source venv/bin/activate
uv pip install -r   requirements.txt
```
