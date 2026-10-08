-- Runs once, when the Postgres container starts with an empty data directory.
--
-- One Postgres server, but a separate database and a separate user for each
-- service. catalog cannot read the orders tables even by mistake: it does not
-- have the password. One server keeps the lab small; in production each
-- service could just as well have its own server.
--
-- Lab passwords. Never commit real ones.

CREATE USER catalog WITH PASSWORD 'catalogpw';
CREATE DATABASE catalog OWNER catalog;

CREATE USER orders WITH PASSWORD 'orderspw';
CREATE DATABASE orders OWNER orders;

CREATE USER payments WITH PASSWORD 'paymentspw';
CREATE DATABASE payments OWNER payments;

CREATE USER invoicing WITH PASSWORD 'invoicingpw';
CREATE DATABASE invoicing OWNER invoicing;

-- Nobody but the owner may connect to each database.
REVOKE CONNECT ON DATABASE catalog, orders, payments, invoicing FROM PUBLIC;
