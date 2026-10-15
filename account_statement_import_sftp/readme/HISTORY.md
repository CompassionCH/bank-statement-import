## 18.0.1.0.0 (2026-10-15)

- \[MIG\] Migration to 18.0: the component is now an EDI process handler
  model. The migration sets it on the camt input exchange types.
- \[ADD\] Other input types of the backend type (like pain.002) get a
  handler that ends the exchange record in error once: they are not bank
  statements.
- \[REM\] `import_statement_edi_auto_post`: in 18 the statement lines are
  always posted.

## 14.0.1.0.0 (2023-06-21)

- \[ADD\] account_statement_import_sftp
