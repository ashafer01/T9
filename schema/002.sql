BEGIN;
INSERT INTO t9_schema (applied) VALUES ('002');

ALTER TABLE funcs ADD PRIMARY KEY (func_name);

COMMIT;
