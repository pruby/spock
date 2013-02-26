BEGIN;

create table trusts(trustor TEXT, trustee TEXT, amount DECIMAL, currency TEXT, PRIMARY KEY (trustor, trustee, currency));
create table debts(debt_from TEXT, debt_to TEXT, amount DECIMAL, currency TEXT, PRIMARY KEY (debt_from, debt_to, currency));

COMMIT;