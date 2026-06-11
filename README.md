![](https://github.com/emercoin/docker/blob/main/docs/docker.png)

# Emercoin + AI agent tools

Docker compose image for Emercoin core **and `emer-ai-tools`: an on-chain
identity & memory layer for AI agents** built on top of it.

> **🤖 Building with an AI agent?** Read **[AGENTS.md](AGENTS.md)** — it explains
> how an agent gets a verifiable on-chain identity and durable memory through the
> `emercoin-agent` MCP server (no cryptocurrency required). A ready-to-use Claude
> Code skill ships at `.claude/skills/emercoin-identity/`.
>
> The rest of this README covers running the Emercoin node itself.

### Why is all this necessary?

Docker allows you to create an isolated container with an Emercoin wallet inside and a separate storage (volume: blockhain_data) for the blockchain. This makes it cross-platform (you can run it on any OS where you can install Docker), the ability to update versions of the Emercoin wallet in one click. Use the wallet functionality in your projects through the RPC JSON interface.

Core - the classic version, just an Emercoin wallet in a container. It takes time to sync with the network.

### To start from scratch:
 
Install [Git](https://github.com/git-guides/install-git)
Install [Docker](https://docs.docker.com/engine/install/) and [docker-compose](https://docs.docker.com/compose/install/#install-compose)

Clone the repository and go to the project folder:
```
git clone https://github.com/emercoin/docker emer_docker_wallet && cd emer_docker_wallet
```

Rename `node/emercoin.conf.example` to `node/emercoin.conf`

**Start building a container with Emercoin:**

The node alone (no agent tools) is the default stack — no profile needed:
```
docker compose -f deploy/docker-compose.yaml up -d --build
```
To also run the AI-agent tools (adapter + edge + redis), add `--profile dev`
(or `--profile prod`); see [AGENTS.md](AGENTS.md).


The container is launched, it takes time to download the blockchain (~ 3-5 hours), but some data can be obtained right now.
By default, port 6662 is used to connect to the container.

- address: **127.0.0.1**
- user: **emcrpc**
- password: **emcpass**
- method: **POST** request body example `{"method": "getinfo"}`

**Change the password in the container:**
```
docker compose -f deploy/docker-compose.yaml exec emc bash changepass.sh
docker compose -f deploy/docker-compose.yaml restart emc
```

### How can I check that the container is working properly?
Need to send **POST** (using Postman, for example)
to the address `http://emcrpc:emcpass@127.0.0.1:6662`, request body `{"method":"getinfo"}`

**Python:**
```python
import requests

url = "emcrpc:emcpass@127.0.0.1:6662"
payload = {"method": "getinfo"}
headers = { 'Content-Type': 'application/json' }
response = requests.request("POST", url, headers=headers, json=payload)
print(response.json())
```

**On the command line using Curl:**
(sudo apt-get update && sudo apt-get install curl) - если Curl не установлен
```bash
curl --location --request POST 'emcrpc:emcpass@127.0.0.1:6662' \
--header 'Content-Type: application/json' \
--data-raw '{"method": "getinfo" }'
```
if everything is ok, the response will be in JSON format:
```JSON
{
    "result": {
        "fullversion": "v0.7.10emc",
        "version": 71000,
        "protocolversion": 70015,
        "walletversion": 130000,
        "balance": 0.000000,
        ...
```

### Build Management

**Stop container:**
```
docker compose -f deploy/docker-compose.yaml stop emc
```

**Remove containers:**
```
docker compose -f deploy/docker-compose.yaml down
```
In this case, the blockchain database, wallet.dat and emercoin.conf are not deleted. It remains in volume docker_emercoin_data.

**Delete blockchain database**
```
docker volume rm emer_data
```
Attention! this command also deletes **wallet.dat**
