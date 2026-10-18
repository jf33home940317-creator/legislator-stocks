# 立委持股查詢：後端

[![CI](https://github.com/jf33home940317-creator/legislator-stocks/actions/workflows/ci.yml/badge.svg)](https://github.com/jf33home940317-creator/legislator-stocks/actions/workflows/ci.yml)

爬取證交所／櫃買中心每日股價（上市、上櫃、興櫃），搭配立法委員財產申報的持股資料，
用「持股 × 最新收盤價」估算市值，並提供 JSON API。

- 設計文件：[docs/specs/2026-09-30-backend-design.md](docs/specs/2026-09-30-backend-design.md)
- 線上 API 文件（給前端組員）：http://192.168.0.137:8000/docs
- 資料來源：監察院公報（持股）、台灣證交所／櫃買中心（股價，每日更新）

## 給前端組員

所有網址都以 `/api/v1` 開頭。

| 網址 | 用途 |
|---|---|
| `GET /politicians?party=&sort=-market_value&limit=20&page=1` | 立委列表／市值排行 |
| `GET /politicians/{id}` | 個人頁（持股明細） |
| `GET /stocks?sort=-holders` | 被最多立委持有的股票 |
| `GET /stocks/{code}` | 個股頁（持有的立委） |
| `GET /meta` | 資料更新日期 |

- `market_value` 是 `null` → 沒有申報資料；`missing_price: true` → 有持股查不到股價，總市值偏低
- 錯誤格式統一：`{"error": {"code": "not_found", "message": "..."}}`
- 請在頁面同時顯示 `declared_date`（申報日）和 `price_date`（股價日），避免誤導
- 股價：上市／上櫃是收盤價；興櫃（`market: "ESB"`）是當天最新成交價

## 技術

Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · SQLite · httpx · pytest · Docker

## 本機開發（Windows）

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\alembic upgrade head
.venv\Scripts\python -m app.crawler prices
.venv\Scripts\python -m app.crawler import_politicians seed/politicians.example.csv
.venv\Scripts\python -m app.crawler import_holdings seed/holdings.example.csv
.venv\Scripts\uvicorn app.api.main:app --reload
```

測試：`.venv\Scripts\python -m pytest`

## 專案結構

```
app/
  config.py        設定（環境變數）
  db.py            資料庫連線
  models.py        7 張資料表
  crawler/         爬蟲：股價（twse/tpex/esb）、CSV 匯入
  services/        市值計算
  api/             FastAPI 路由
  backup.py        SQLite 備份
migrations/        Alembic 資料庫版本
seed/              範例 CSV
tests/             73 個測試
```

## 新增持股資料

1. 在 `seed/politicians.csv` 加立委（`id` 自己編號，不重複）
2. 在 `seed/holdings.csv` 加持股（`owner` 只能填 `本人`／`配偶`／`未成年子女`）
3. 先 `import_politicians`，再 `import_holdings`
4. 同一位立委同一申報日重匯，會整份取代舊持股

## 修改資料表

1. 改 `app/models.py`
2. `.venv\Scripts\alembic revision --autogenerate -m "說明"`，檢查產生的檔案
3. `.venv\Scripts\alembic upgrade head`
4. 伺服器重新部署時會自動升級（容器啟動會跑 `alembic upgrade head`）

## 部署（自架伺服器 192.168.0.137）

更新程式：

```powershell
git push server main
ssh yicheng@192.168.0.137 "cd ~/apps/legislator-stocks && git pull && docker compose up -d --build"
```

伺服器上手動抓股價 / 備份：

```bash
docker compose exec -T api python -m app.crawler prices
docker compose exec -T api python -m app.backup
```

- 排程設定在 `deploy/crontab`（週一～五台灣 17:00、18:30 抓股價，週二～六 08:00 補抓前一交易日，每天 03:00 備份），記錄檔在伺服器 `data/cron.log`；每筆股價紀錄會寫出「資料日期」，可看出是否抓到舊資料
- 環境變數在伺服器的 `.env`（`ADMIN_API_KEY`、`CORS_ORIGINS`），不進 git
- 資料庫檔案在 `data/app.db`（Docker volume，重建容器不會遺失）

## 資料來源與授權

持股資料來自監察院公職人員財產申報公報；股價來自台灣證交所、櫃買中心公開 OpenAPI。
本專案為課堂作業，PDF 解析邏輯部分參考開源專案 legislator-wealth.tw（MIT 授權）。
