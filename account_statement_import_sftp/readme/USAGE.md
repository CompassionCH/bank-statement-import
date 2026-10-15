The EDI scheduled actions find the new files on the server, get them and
import them as bank statements. A file that cannot be imported (unknown
format, or only transactions already imported) gets the error on its
exchange record.

Files of other input types of this backend type (like pain.002) are not
bank statements: with the *EDI handler: bank file not imported* processor,
their exchange record ends in error once.

The statement lines are posted when they are created, so the old
`import_statement_edi_auto_post` system parameter is not used any more.
