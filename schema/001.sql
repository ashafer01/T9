-- Schema setup for Postgres

BEGIN;
INSERT INTO t9_schema (applied) VALUES ('001');

CREATE TABLE funcs (
    func_name text,
    parent_func text,
    func_data text,
    setter_nick varchar(32),
    set_time timestamp DEFAULT now()
);

CREATE TABLE chans (channel varchar(32));

CREATE TABLE secrets (
    owner_nick varchar(32),
    env_var varchar(32),
    secret varchar(512),
    PRIMARY KEY (owner_nick, env_var)
);

CREATE TABLE write_locks (
    file_path text PRIMARY KEY,
    owner_nick varchar(32)
);

COMMIT;
