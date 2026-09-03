-- ==========================================================================
-- Sample ORACLE schema (HR-style) used to demo the dbmigrate plugin.
-- Exercises a spread of datatypes, constraints, views, PL/SQL routines,
-- a trigger and a sequence so every generator/report path is hit.
-- Oracle "/" terminators are used for PL/SQL blocks.
-- ==========================================================================

CREATE SEQUENCE emp_seq START WITH 1000 INCREMENT BY 1;

CREATE TABLE departments (
    dept_id        NUMBER(6)        NOT NULL,
    dept_name      VARCHAR2(60)     NOT NULL,
    location       VARCHAR2(120),
    budget         NUMBER(14,2)     DEFAULT 0,
    created_at     DATE             DEFAULT SYSDATE,
    CONSTRAINT pk_departments PRIMARY KEY (dept_id),
    CONSTRAINT uq_dept_name UNIQUE (dept_name)
);

CREATE TABLE employees (
    emp_id         NUMBER(10)       NOT NULL,
    first_name     VARCHAR2(50)     NOT NULL,
    last_name      VARCHAR2(50)     NOT NULL,
    email          VARCHAR2(120),
    phone          VARCHAR2(30),
    hire_date      DATE             NOT NULL,
    job_title      VARCHAR2(80),
    salary         NUMBER(12,2),
    commission     BINARY_DOUBLE,
    is_active      CHAR(1)          DEFAULT 'Y',
    dept_id        NUMBER(6),
    resume_doc     CLOB,
    photo          BLOB,
    external_ref   RAW(16),
    last_review    TIMESTAMP WITH TIME ZONE,
    notes          NVARCHAR2(400),
    row_ver        NUMBER,
    CONSTRAINT pk_employees PRIMARY KEY (emp_id),
    CONSTRAINT fk_emp_dept FOREIGN KEY (dept_id) REFERENCES departments(dept_id),
    CONSTRAINT ck_active CHECK (is_active IN ('Y','N'))
);

CREATE TABLE audit_log (
    log_id         NUMBER(12)       NOT NULL,
    table_name     VARCHAR2(60),
    action         VARCHAR2(10),
    changed_at     TIMESTAMP,
    detail         LONG,
    row_location   ROWID,
    CONSTRAINT pk_audit PRIMARY KEY (log_id)
);

CREATE VIEW v_active_employees AS
    SELECT e.emp_id, e.first_name, e.last_name, e.salary, d.dept_name
    FROM employees e
    JOIN departments d ON e.dept_id = d.dept_id
    WHERE e.is_active = 'Y';

CREATE OR REPLACE FUNCTION fn_annual_salary (p_emp_id IN NUMBER)
RETURN NUMBER
IS
    v_salary NUMBER(12,2);
BEGIN
    SELECT salary INTO v_salary FROM employees WHERE emp_id = p_emp_id;
    RETURN NVL(v_salary, 0) * 12;
END;
/

CREATE OR REPLACE PROCEDURE sp_give_raise (
    p_emp_id   IN NUMBER,
    p_percent  IN NUMBER
)
IS
BEGIN
    UPDATE employees
       SET salary = salary * (1 + p_percent / 100)
     WHERE emp_id = p_emp_id;
    COMMIT;
END;
/

CREATE OR REPLACE TRIGGER trg_emp_audit
AFTER INSERT OR UPDATE ON employees
FOR EACH ROW
BEGIN
    INSERT INTO audit_log (log_id, table_name, action, changed_at)
    VALUES (emp_seq.NEXTVAL, 'EMPLOYEES', 'CHG', SYSTIMESTAMP);
END;
/
