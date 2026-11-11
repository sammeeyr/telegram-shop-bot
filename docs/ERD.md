# Entity Relationship Diagram

Current Sprint 1-3 schema from `commerce_api/db/models.py`:

```mermaid
erDiagram
    USERS ||--o{ TENANT_MEMBERSHIPS : joins
    TENANTS ||--o{ TENANT_MEMBERSHIPS : has
    USERS ||--o{ REFRESH_SESSIONS : authenticates
    TENANTS ||--o{ CATEGORIES : owns
    TENANTS ||--o{ PRODUCTS : owns
    CATEGORIES o|--o{ PRODUCTS : classifies
    PRODUCTS ||--o{ PRODUCT_VARIANTS : offers
    TENANTS ||--o{ WAREHOUSES : owns
    PRODUCT_VARIANTS ||--o{ INVENTORY_BALANCES : stocked_as
    WAREHOUSES ||--o{ INVENTORY_BALANCES : stores
    PRODUCT_VARIANTS ||--o{ STOCK_RESERVATIONS : reserved
    WAREHOUSES ||--o{ STOCK_RESERVATIONS : from
    PRODUCT_VARIANTS ||--o{ STOCK_MOVEMENTS : moved
    WAREHOUSES ||--o{ STOCK_MOVEMENTS : at
    STOCK_RESERVATIONS o|--o{ STOCK_MOVEMENTS : records
    TENANTS ||--o{ CUSTOMERS : owns
    CUSTOMERS ||--o{ CUSTOMER_ADDRESSES : has
    CUSTOMERS ||--o{ CARTS : owns
    CARTS ||--o{ CART_ITEMS : contains
    PRODUCT_VARIANTS ||--o{ CART_ITEMS : selected
    CUSTOMERS ||--o{ ORDERS : places
    ORDERS ||--o{ ORDER_ITEMS : contains
    PRODUCT_VARIANTS ||--o{ ORDER_ITEMS : snapshotted_as
    ORDERS ||--o{ PAYMENT_ATTEMPTS : paid_by
    PRODUCT_VARIANTS ||--o{ DIGITAL_ASSETS : supplies
    ORDER_ITEMS o|--o{ DIGITAL_ASSETS : receives

    USERS {
        uuid id PK
        string email UK
        string full_name
        string password_hash
        boolean is_platform_admin
    }
    TENANTS {
        uuid id PK
        string name
        string slug UK
    }
    TENANT_MEMBERSHIPS {
        uuid id PK
        uuid tenant_id FK
        uuid user_id FK
        string role
    }
    REFRESH_SESSIONS {
        string token_hash PK
        uuid user_id FK
        datetime expires_at
        datetime revoked_at
    }
    CATEGORIES {
        uuid id PK
        uuid tenant_id FK
        string name
        string slug
    }
    PRODUCTS {
        uuid id PK
        uuid tenant_id FK
        uuid category_id FK
        bigint unit_price_minor
        string currency
    }
    PRODUCT_VARIANTS {
        uuid id PK
        uuid tenant_id FK
        uuid product_id FK
        string sku
    }
    WAREHOUSES {
        uuid id PK
        uuid tenant_id FK
        string code
    }
    INVENTORY_BALANCES {
        uuid id PK
        uuid tenant_id FK
        uuid variant_id FK
        uuid warehouse_id FK
        decimal on_hand
        decimal reserved
        decimal safety_stock
    }
    STOCK_RESERVATIONS {
        uuid id PK
        uuid tenant_id FK
        uuid variant_id FK
        uuid warehouse_id FK
        decimal quantity
        string idempotency_key
        string status
        datetime expires_at
    }
    STOCK_MOVEMENTS {
        uuid id PK
        uuid tenant_id FK
        uuid variant_id FK
        uuid warehouse_id FK
        uuid reservation_id FK
        string kind
        decimal quantity
        string idempotency_key
    }
    CUSTOMERS {
        uuid id PK
        uuid tenant_id FK
        string full_name
        string email
    }
    CUSTOMER_ADDRESSES {
        uuid id PK
        uuid tenant_id FK
        uuid customer_id FK
        json address
    }
    CARTS {
        uuid id PK
        uuid tenant_id FK
        uuid customer_id FK
        string status
        string checkout_key
    }
    CART_ITEMS {
        uuid id PK
        uuid tenant_id FK
        uuid cart_id FK
        uuid variant_id FK
        decimal quantity
    }
    ORDERS {
        uuid id PK
        uuid tenant_id FK
        uuid customer_id FK
        bigint total_minor
        string payment_status
        string fulfillment_status
    }
    ORDER_ITEMS {
        uuid id PK
        uuid tenant_id FK
        uuid order_id FK
        uuid variant_id FK
        string product_name_snapshot
        bigint unit_price_minor
        string product_type
    }
    PAYMENT_ATTEMPTS {
        uuid id PK
        uuid tenant_id FK
        uuid order_id FK
        string provider
        string provider_reference
        string status
    }
    DIGITAL_ASSETS {
        uuid id PK
        uuid tenant_id FK
        uuid variant_id FK
        uuid order_item_id FK
        bytes ciphertext
        string status
    }
```

The diagram omits secondary unique constraints, audit timestamps, and RLS policy predicates. Every commerce relationship includes tenant identity in its database constraints. The legacy Telegram bot schema is intentionally separate.