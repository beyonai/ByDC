class FileStoreError(Exception):
    """File store base error."""


class InvalidUploadItemError(FileStoreError):
    pass


class BackendMisconfiguredError(FileStoreError):
    pass


class FileNotFoundInStoreError(FileStoreError):
    def __init__(self, md5: str):
        super().__init__(f"File not found for md5={md5}")
        self.md5 = md5
