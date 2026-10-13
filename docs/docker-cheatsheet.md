# Docker 複習筆記

本專案用 Docker 部署到自架伺服器。這份是常用概念與指令整理。

## 三個核心名詞

| 名詞 | 是什麼 | 比喻 |
|---|---|---|
| 映像檔 image | 打包好的「程式 + 環境」，唯讀模板 | 安裝光碟 / 食譜 |
| 容器 container | 用 image 跑起來的實體，可啟停刪 | 用光碟裝好開機的電腦 |
| 資料卷 volume | 掛在容器外的資料夾，容器砍掉資料還在 | 外接硬碟 |

- 一個 image 可以開出很多 container。
- `--build` = 做出 image；`up` = 用 image 開 container。
- 資料庫 `app.db` 放在 `./data` volume，重建容器不會遺失。

## 兩個設定檔

`Dockerfile`：怎麼做出 image（食譜）

```dockerfile
FROM python:3.12-slim        # 基底：已裝好 Python 的 Linux
COPY requirements.txt .      # 先複製套件清單
RUN pip install ...          # 裝套件（這層會被快取）
COPY app ./app               # 再複製程式碼
CMD ["sh","-c","alembic upgrade head && uvicorn app.api.main:app --host 0.0.0.0 --port 8000"]
```

`docker-compose.yml`：怎麼跑這個 container（埠、volume、環境變數）

```yaml
services:
  api:
    build: .
    ports: ["8000:8000"]       # 主機 8000 → 容器 8000
    volumes: ["./data:/data"]  # 資料庫放這
    env_file: .env
```

## 常用指令

建置 & 啟動：

```bash
docker compose up -d --build   # 建 image + 背景啟動容器
```

看狀態 & log：

```bash
docker compose ps              # 容器狀態
docker compose logs --tail 20 api
docker compose logs -f api     # -f = 即時跟著看
```

在容器裡執行指令：

```bash
docker compose exec -T api python -m app.crawler prices
docker compose exec -T api python -m app.crawler legislators
docker compose exec -T api python -m app.backup
```

- `exec` = 在跑著的容器裡執行；`-T` = 不開互動終端（腳本/cron 用）。

其他維運：

```bash
docker compose down            # 停止並移除容器（volume 資料保留）
docker compose restart
docker compose cp seed api:/app/seed   # 複製檔案進容器
docker images                  # 列出 image
docker ps                      # 列出執行中的容器
```

## 更新部署循環

```bash
# 本機
git push server main

# 伺服器
cd ~/apps/legislator-stocks
git pull
docker compose up -d --build
# 需要時：docker compose exec -T api <指令>
```

第一次部署才要做（之後不用重做）：建 bare repo、clone、設定 `.env`、安裝 cron。
