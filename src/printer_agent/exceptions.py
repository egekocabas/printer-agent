"""Application-level exceptions translated at the HTTP boundary."""


class PrinterAgentError(Exception):
    """Base class for expected application failures."""


class PrinterConfigurationError(PrinterAgentError):
    """The selected printer backend is not configured correctly."""


class PrinterUnavailableError(PrinterAgentError):
    """The configured printer cannot currently be reached."""


class PrinterCommunicationError(PrinterAgentError):
    """Communication with the printer failed after it was opened."""


class InvalidImageError(PrinterAgentError):
    """Uploaded bytes are not a complete, decodable image."""


class UnsupportedImageFormatError(InvalidImageError):
    """An image decoded successfully but has an unsupported format."""


class ImageTooLargeError(InvalidImageError):
    """An image exceeds an encoded or decoded size limit."""


class InvalidPrintDocumentError(PrinterAgentError):
    """A multipart print document is malformed or references missing files."""
