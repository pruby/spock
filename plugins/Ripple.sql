BEGIN;

CREATE TABLE trusts (
  trustor TEXT NOT NULL,
  trustee TEXT NOT NULL,
  amount DECIMAL NOT NULL,
  currency TEXT NOT NULL,
  PRIMARY KEY (trustor, trustee, currency)
);

CREATE TABLE debts (
  debt_from TEXT NOT NULL,
  debt_to TEXT NOT NULL,
  amount DECIMAL NOT NULL,
  currency TEXT NOT NULL,
  PRIMARY KEY (debt_from, debt_to, currency)
);

CREATE TABLE trust_changes (
  trustor TEXT NOT NULL,
  trustee TEXT NOT NULL,
  changed_by DECIMAL NOT NULL,
  currency TEXT NOT NULL,
  changed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT 'now'
);

CREATE TABLE transactions (
  transaction_id SERIAL PRIMARY KEY,
  sent_from TEXT NOT NULL,
  sent_to TEXT NOT NULL,
  amount DECIMAL NOT NULL,
  currency TEXT NOT NULL,
  sent_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT 'now'
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