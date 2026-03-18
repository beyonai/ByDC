class FileStoreError(Exception):
    """File store base error."""


class InvalidUploadItem(FileStoreError):
    pass


class BackendMisconfigured(FileStoreError):
    pass


class FileNotFoundInStore(FileStoreError):
    def __init__(self, md5: str):
        super().__init__(f"File not found for md5={md5}")
        self.md5 = md5

