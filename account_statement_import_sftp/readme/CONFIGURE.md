1.  Create an EDI backend with the backend type *Bank SFTP Import* and an
    FS storage (sftp). Set its input pending directory.
2.  For each kind of file, create an input exchange type for this backend
    type, with a filename pattern (for example `^camt\.053.*\.xml`).
3.  Set *Receiver* to the storage handler and *Processor* to
    *EDI handler: import bank statement files*.
