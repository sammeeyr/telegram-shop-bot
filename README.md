# Cube Tech Commerce

Cube Tech Enterprises' shared, multi-tenant commerce and dispatch platform. The commerce engine is the foundation; Telegram, storefronts, WhatsApp, rider tools, and developer integrations will be channel adapters over shared services.

**Current milestone:** Sprints 1-3 foundation, tenancy, catalog, inventory, checkout, and orders. FastAPI, PostgreSQL, SQLAlchemy async, Alembic, forced RLS, atomic stock reservations, immutable order snapshots, separate payment/fulfillment states, and a verified-payment gate for encrypted digital assets. Payment providers are not integrated yet.

## Commerce API development

Copy `.env.example` to `.env`, replace the development secrets, then start PostgreSQL and apply migrations:

```powershell
pip install -e ".[dev]"
docker compose up -d postgres
alembic upgrade head
uvicorn commerce_api.asgi:app --reload
```

For digital inventory, generate a unique Fernet key and set `DIGITAL_ASSET_ENCRYPTION_KEY` in the local environment. Keep it separate from `JWT_SECRET_KEY`; without it, digital asset operations fail closed.

OpenAPI is available at `http://localhost:8000/docs`. Run the full suite with `python -m pytest`. The direct PostgreSQL RLS test requires `TEST_DATABASE_URL`; CI provisions PostgreSQL and runs it against the restricted runtime role.

The system is not production-ready yet. No production deployment or production data changes are authorized. See [Sprint Tracker](project/SPRINT_TRACKER.md) and [Deployment Guide](docs/DEPLOYMENT_GUIDE.md).

## Legacy Telegram Digital Shop

The existing bot is retained as a separate legacy application while the shared platform is built. It sells digital products: license keys, accounts, gift codes, e-books, and download links. It is not yet a multi-tenant commerce channel adapter and uses a separate SQLite database and Crypto Pay implementation.

**Legacy stack:** Python 3.11+, [aiogram 3](https://docs.aiogram.dev), SQLAlchemy 2 async, SQLite, [Crypto Pay API](https://help.crypt.bot/crypto-pay-api) (@CryptoBot).

## Features

**Customers**
- 👤 Profile, created automatically on `/start`: balance, total deposited/spent, order count
- 💰 Crypto top-ups: USDT, TON, BTC, ETH, LTC, TRX, BNB, USDC through @CryptoBot. Balance is credited automatically.
- 🛍 Catalog with categories, product cards, live stock levels, and a quantity picker
- ⚡ Instant delivery: items arrive in the chat, and big orders come as a `.txt` file
- 📦 Order history, with the option to re-send purchased items at any time
- 🧾 Top-up history. Open invoices can be reopened, re-checked or cancelled.

**Admins** (`/admin` or the ⚙️ button)
- 📂 Catalog: create, rename, hide or delete categories and products, and edit name, description and price
- Two delivery types:
  - 🔑 **Unique items**: each buyer gets their own keys/accounts from stock
  - ♾ **Same content for everyone**: a file, link or text, with unlimited stock
- 📥 Stock upload by pasting lines or sending a `.txt` file. Multi-line items are separated with `---`. Duplicates are skipped, including items that already sold.
- 📤 Export and 🧹 clear unsold stock
- 📦 Inventory overview with low-stock and out-of-stock markers
- ⚠️ Automatic low-stock alerts, plus alerts for new orders and paid top-ups
- 📈 Stats: users, orders, revenue (today, 7 days, total), deposits, top products
- 👥 Users: find by ID or @username, add/deduct balance (the user is notified), ban/unban
- 📣 Broadcast any message (text, photo, file…) to all users, rate-limited

**Reliability**
- Money is stored as integer cents and every balance change is written to a ledger (`balance_transactions`)
- Purchases are atomic: the balance charge, stock claim and order are one transaction, using conditional updates.
  Concurrent buyers can't oversell stock, and a balance can't go negative (both covered by tests).
- Top-up crediting is idempotent: a payment is credited exactly once, even if the poller and the
  "I've paid" button race each other
- Orders keep a snapshot of what was delivered, so history survives product edits or deletion

## Setup

### 1. Create the bot and payment app
1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Get your numeric Telegram ID from [@userinfobot](https://t.me/userinfobot). This makes you an admin.
3. Crypto Pay token:
   - **Testing:** open [@CryptoTestnetBot](https://t.me/CryptoTestnetBot) → Crypto Pay → Create App → copy the token. Test coins are free.
   - **Production:** do the same in [@CryptoBot](https://t.me/CryptoBot) and set `CRYPTOPAY_TESTNET=false`.

### 2. Configure
```bash
cp .env.example .env
```
Fill in `BOT_TOKEN`, `ADMIN_IDS` and `CRYPTOPAY_TOKEN`. Every option is documented in `.env.example`.

### 3. Run
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
python -m shopbot
```
Or with Docker:
```bash
docker compose up -d --build
```
The database (`data/shop.db`) is created automatically on first run.

### 4. Stock the shop
In the bot: **⚙️ Admin Panel → 📂 Catalog → ➕ New category → ➕ Add product**, then **➕ Add stock**.

Stock upload format:
```
KEY-AAAA-1111
KEY-BBBB-2222
```
or, for multi-line items:
```
login: alice@mail.com
password: hunter2
---
login: bob@mail.com
password: qwerty
```

## How payments work
1. The customer picks an amount, and the bot creates a Crypto Pay invoice in your fiat currency (e.g. $10).
2. The customer pays in @CryptoBot with any accepted coin.
3. A background poller checks open invoices every `PAYMENT_POLL_INTERVAL` seconds and credits the balance.
   The "I've paid" button triggers an immediate check. No public server or webhook is needed.

Funds land in your Crypto Pay app balance inside @CryptoBot.

To add another gateway, implement the small `PaymentProvider` protocol in `shopbot/payments/base.py`.
`shopbot/payments/cryptopay.py` is the reference implementation.

## Project layout
```
commerce_api/
  api/routes/          versioned FastAPI endpoints
  core/                settings, password hashing, access and refresh tokens
  db/                  PostgreSQL models, sessions, and tenant RLS context
  migrations/          Alembic environment and versioned schema
  services/             tenant onboarding and authentication services
shopbot/
  config.py            settings from .env
  money.py             cents parsing/formatting
  db/                  models + engine
  services/            business logic (no Telegram code): users, catalog, inventory, orders, deposits, stats
  payments/            provider interface, Crypto Pay client, PaymentService (invoices, polling, crediting)
  bot/
    app.py             startup/shutdown, dispatcher wiring
    middlewares.py     DB session + user registration/ban check
    handlers/          start, shop, orders, deposit, admin/*, fallback
    texts.py           every message the bot sends
    keyboards.py       user keyboards; admin_keyboards.py
    delivery.py        sends purchased items
    tasks.py           payment poller
tests/                 service, payment and end-to-end bot tests
docs/                  architecture, domain, security, API, and operations docs
project/               sprint tracker, decisions, known issues, release checklist
```

## Tests
```bash
pip install -e ".[dev]"
python -m pytest
```
The end-to-end test runs fake Telegram updates through the real dispatcher: admin setup, purchase, top-up, bans and
reports. It also checks that every outgoing message is valid Telegram HTML.

## Notes
- FSM state (half-finished forms) lives in memory and resets on restart. Balances, orders and stock are in the database.
- Tables are created automatically. If you change models later, add a migration tool such as Alembic.
- For high traffic, use PostgreSQL: `pip install asyncpg` and set `DATABASE_URL`.
