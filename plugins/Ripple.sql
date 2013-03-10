BEGIN;

CREATE TABLE accounts (
  account_name TEXT PRIMARY KEY,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX account_name_case_insensitive ON accounts(LOWER(account_name));

CREATE TABLE account_managers (
  account_name TEXT NOT NULL REFERENCES accounts,
  minecraft_name TEXT NOT NULL
);

CREATE TABLE api_keys (
  key_id TEXT NOT NULL PRIMARY KEY,
  secret TEXT NOT NULL,
  account_name TEXT NOT NULL REFERENCES accounts,
  access_type TEXT NOT NULL CHECK (access_type IN ('read', 'write')),
  UNIQUE (minecraft_name, description)
);

CREATE TABLE refusals (
  trustor TEXT NOT NULL REFERENCES accounts,
  trustee TEXT NOT NULL REFERENCES accounts,
  amount DECIMAN NOT NULL CHECK (amount >= 0),
  currency TEXT NOT NULL REFERENCES currencies,
  refused_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE currencies (
  currency_name TEXT PRIMARY KEY,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
INSERT INTO CURRENCIES (currency_name) VALUES ('d'), ('i');

CREATE TABLE trusts (
  trustor TEXT NOT NULL REFERENCES accounts,
  trustee TEXT NOT NULL REFERENCES accounts,
  amount DECIMAL NOT NULL CHECK (amount >= 0),
  currency TEXT NOT NULL REFERENCES currencies,
  PRIMARY KEY (trustor, trustee, currency)
);

CREATE TABLE debts (
  debt_from TEXT NOT NULL REFERENCES accounts,
  debt_to TEXT NOT NULL REFERENCES accounts,
  amount DECIMAL NOT NULL CHECK (amount >= 0),
  currency TEXT NOT NULL REFERENCES currencies,
  PRIMARY KEY (debt_from, debt_to, currency)
);

CREATE TABLE trust_changes (
  trustor TEXT NOT NULL REFERENCES accounts,
  trustee TEXT NOT NULL REFERENCES accounts,
  changed_by DECIMAL NOT NULL,
  currency TEXT NOT NULL REFERENCES currencies,
  changed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE transactions (
  transaction_id SERIAL PRIMARY KEY,
  sent_from TEXT NOT NULL REFERENCES accounts,
  sent_to TEXT NOT NULL REFERENCES accounts,
  amount DECIMAL NOT NULL CHECK (amount > 0),
  currency TEXT NOT NULL REFERENCES currencies,
  invoker TEXT NOT NULL,
  sent_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TABLE transaction_paths (
    transaction_id INTEGER NOT NULL REFERENCES transactions,
    path_id INTEGER NOT NULL,
    path TEXT[] NOT NULL,
    amount DECIMAL NOT NULL,
    PRIMARY KEY (transaction_id, path_id)
);

CREATE TABLE shifts (
    transaction_id INTEGER NOT NULL,
    path_id INTEGER NOT NULL,
    from_account TEXT NOT NULL,
    to_account TEXT NOT NULL,
    FOREIGN KEY (transaction_id, path_id) REFERENCES transaction_paths
);

COMMIT;