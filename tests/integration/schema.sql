-- The GnuCash tables the form reads and writes, as GnuCash 5 creates them in
-- PostgreSQL, with a small account tree. GUIDs are readable fixtures.

DROP TABLE IF EXISTS splits, transactions, prices, accounts, commodities;

CREATE TABLE commodities (
    guid varchar(32) PRIMARY KEY,
    namespace varchar(2048) NOT NULL,
    mnemonic varchar(2048) NOT NULL,
    fullname varchar(2048),
    cusip varchar(2048),
    fraction integer NOT NULL,
    quote_flag integer NOT NULL,
    quote_source varchar(2048),
    quote_tz varchar(2048)
);

CREATE TABLE accounts (
    guid varchar(32) PRIMARY KEY,
    name varchar(2048) NOT NULL,
    account_type varchar(2048) NOT NULL,
    commodity_guid varchar(32),
    commodity_scu integer NOT NULL,
    non_std_scu integer NOT NULL,
    parent_guid varchar(32),
    code varchar(2048),
    description varchar(2048),
    hidden integer,
    placeholder integer
);

CREATE TABLE prices (
    guid varchar(32) PRIMARY KEY,
    commodity_guid varchar(32) NOT NULL,
    currency_guid varchar(32) NOT NULL,
    date timestamp NOT NULL,
    source varchar(2048),
    type varchar(2048),
    value_num bigint NOT NULL,
    value_denom bigint NOT NULL
);

CREATE TABLE transactions (
    guid varchar(32) PRIMARY KEY,
    currency_guid varchar(32) NOT NULL,
    num varchar(2048) NOT NULL,
    post_date timestamp,
    enter_date timestamp,
    description varchar(2048)
);

CREATE TABLE splits (
    guid varchar(32) PRIMARY KEY,
    tx_guid varchar(32) NOT NULL,
    account_guid varchar(32) NOT NULL,
    memo varchar(2048) NOT NULL,
    action varchar(2048) NOT NULL,
    reconcile_state varchar(1) NOT NULL,
    reconcile_date timestamp,
    value_num bigint NOT NULL,
    value_denom bigint NOT NULL,
    quantity_num bigint NOT NULL,
    quantity_denom bigint NOT NULL,
    lot_guid varchar(32)
);

INSERT INTO commodities (guid, namespace, mnemonic, fraction, quote_flag) VALUES
    ('c0000000000000000000000000000jpy', 'CURRENCY', 'JPY', 1, 0),
    ('c0000000000000000000000000000twd', 'CURRENCY', 'TWD', 100, 0),
    ('c0000000000000000000000000000usd', 'CURRENCY', 'USD', 100, 0);

INSERT INTO accounts
    (guid, name, account_type, commodity_guid, commodity_scu, non_std_scu,
     parent_guid, hidden, placeholder)
VALUES
    ('a00000000000000000000000000root0', 'Root Account', 'ROOT', NULL, 0, 0, NULL, 0, 0),
    ('a00000000000000000000000template', 'Template Root', 'ROOT', NULL, 0, 0, NULL, 0, 0),
    ('a0000000000000000000000000tmpl01', 'Assets', 'ASSET', 'c0000000000000000000000000000jpy', 1, 0, 'a00000000000000000000000template', 0, 0),
    ('a000000000000000000000000assets0', 'Assets', 'ASSET', 'c0000000000000000000000000000jpy', 1, 0, 'a00000000000000000000000000root0', 0, 1),
    ('a00000000000000000000000jpycurr0', 'Yen', 'ASSET', 'c0000000000000000000000000000jpy', 1, 0, 'a000000000000000000000000assets0', 0, 1),
    ('a00000000000000000000000jpycash0', 'Cash', 'CASH', 'c0000000000000000000000000000jpy', 1, 0, 'a00000000000000000000000jpycurr0', 0, 0),
    ('a00000000000000000000000usdcurr0', 'Dollar', 'ASSET', 'c0000000000000000000000000000usd', 100, 0, 'a000000000000000000000000assets0', 0, 1),
    ('a00000000000000000000000usdcash0', 'Cash', 'CASH', 'c0000000000000000000000000000usd', 100, 0, 'a00000000000000000000000usdcurr0', 0, 0),
    ('a00000000000000000000000twdcurr0', 'NT Dollar', 'ASSET', 'c0000000000000000000000000000twd', 100, 0, 'a000000000000000000000000assets0', 0, 1),
    ('a00000000000000000000000twdcash0', 'Cash', 'CASH', 'c0000000000000000000000000000twd', 100, 0, 'a00000000000000000000000twdcurr0', 0, 0),
    ('a0000000000000000000000expenses0', 'Expenses', 'EXPENSE', 'c0000000000000000000000000000jpy', 1, 0, 'a00000000000000000000000000root0', 0, 1),
    ('a000000000000000000000000foods00', 'Food', 'EXPENSE', 'c0000000000000000000000000000jpy', 1, 0, 'a0000000000000000000000expenses0', 0, 0),
    ('a00000000000000000000000dining00', 'Dining', 'EXPENSE', 'c0000000000000000000000000000jpy', 1, 0, 'a000000000000000000000000foods00', 0, 0),
    ('a000000000000000000000000000old0', 'Old', 'EXPENSE', 'c0000000000000000000000000000jpy', 1, 0, 'a0000000000000000000000expenses0', 1, 0);

INSERT INTO prices
    (guid, commodity_guid, currency_guid, date, source, type, value_num, value_denom)
VALUES
    ('p000000000000000000000000twdjpy0', 'c0000000000000000000000000000twd', 'c0000000000000000000000000000jpy', '2026-08-06 10:59:00', 'user:price', 'last', 487, 100),
    ('p000000000000000000000000jpyusd0', 'c0000000000000000000000000000jpy', 'c0000000000000000000000000000usd', '2026-07-31 10:59:00', 'user:price', 'last', 1, 150);
