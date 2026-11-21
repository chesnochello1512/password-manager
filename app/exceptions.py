"""Domain exceptions with user-safe messages."""


class PasswordManagerError(Exception):
    """Base class for all expected application errors."""


class ValidationError(PasswordManagerError):
    """User input failed validation."""


class VaultError(PasswordManagerError):
    """Base class for vault related failures."""


class VaultNotFoundError(VaultError):
    """No vault exists at the expected location."""


class VaultExistsError(VaultError):
    """A vault already exists and cannot be created twice."""


class VaultLockedError(VaultError):
    """The vault is locked and the operation requires the encryption key."""


class InvalidMasterPasswordError(VaultError):
    """The supplied master password does not unlock the vault."""


class VaultCorruptedError(VaultError):
    """The vault is structurally damaged or has an unsupported format."""


class VaultReopenError(VaultError):
    """The vault file was replaced but could not be opened again.

    The operation has already been committed: the new master password is the
    one that now protects the file on disk.  The UI must not claim that the
    data is unchanged.
    """

    committed = True


class DecryptionError(VaultError):
    """Authenticated decryption failed."""


class BackupError(PasswordManagerError):
    """Backup creation, validation or restoration failed."""


class GeneratorError(PasswordManagerError):
    """Invalid password generator configuration."""


class StorageError(PasswordManagerError):
    """A database operation failed."""
