# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
import base64
import re
from typing import List, Optional
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.backends import default_backend


def _pem_to_x5c(pem_chain: str) -> List[str]:
    """Convert a PEM certificate chain to x5c format (array of base64-encoded DER certificates).

    :param str pem_chain: PEM-encoded certificate chain (may have newlines stripped)
    :return: List of base64-encoded DER certificates for the x5c JWT header
    :rtype: List[str]
    """
    # The pem_chain may have newlines stripped, so we need to handle both cases
    # Pattern matches -----BEGIN CERTIFICATE----- followed by base64 content followed by -----END CERTIFICATE-----
    cert_pattern = re.compile(
        r"-----BEGIN CERTIFICATE-----(.+?)-----END CERTIFICATE-----",
        re.DOTALL
    )
    x5c = []
    for match in cert_pattern.finditer(pem_chain):
        # Extract the base64 content and remove any whitespace/newlines
        cert_b64 = match.group(1).replace("\n", "").replace("\r", "").replace(" ", "")
        x5c.append(cert_b64)
    return x5c


class AadClientCertificate:
    """Wraps 'cryptography' to provide the crypto operations AadClient requires for certificate authentication.

    :param bytes pem_bytes: bytes of a a PEM-encoded certificate including the (RSA) private key
    :param bytes password: (optional) the certificate's password
    :param str public_certificate: (optional) the public certificate chain for x5c claim (SNI authentication)
    """

    def __init__(self, pem_bytes: bytes, password: Optional[bytes] = None, public_certificate: Optional[str] = None) -> None:
        private_key = serialization.load_pem_private_key(pem_bytes, password=password, backend=default_backend())
        if not isinstance(private_key, RSAPrivateKey):
            raise ValueError("The certificate must have an RSA private key because RS256 is used for signing")
        self._private_key = private_key

        cert = x509.load_pem_x509_certificate(pem_bytes, default_backend())
        fingerprint = cert.fingerprint(hashes.SHA1())  # nosec
        sha256_fingerprint = cert.fingerprint(hashes.SHA256())
        self._thumbprint = base64.urlsafe_b64encode(fingerprint).decode("utf-8")
        self._sha256_thumbprint = base64.urlsafe_b64encode(sha256_fingerprint).decode("utf-8")

        self._x5c = _pem_to_x5c(public_certificate) if public_certificate else None

    @property
    def thumbprint(self) -> str:
        """The certificate's SHA1 thumbprint as a base64url-encoded string.

        :rtype: str
        """
        return self._thumbprint

    @property
    def sha256_thumbprint(self) -> str:
        """The certificate's SHA256 thumbprint as a base64url-encoded string.

        :rtype: str
        """
        return self._sha256_thumbprint

    def sign_rs256(self, plaintext: bytes) -> bytes:
        """Sign bytes using RS256.

        :param bytes plaintext: Bytes to sign.
        :return: The signature.
        :rtype: bytes
        """
        return self._private_key.sign(
            plaintext, padding.PKCS1v15(), hashes.SHA256()  # CodeQL [SM04457] need this for backwards compatibility
        )

    def sign_ps256(self, plaintext: bytes) -> bytes:
        """Sign bytes using PS256.

        :param bytes plaintext: Bytes to sign.
        :return: The signature.
        :rtype: bytes
        """
        hash_alg = hashes.SHA256()

        # Note: For PS265, the salt length should match the hash output size, so we use the hash algorithm's
        # digest_size property to get the correct value.
        return self._private_key.sign(
            plaintext,
            padding.PSS(mgf=padding.MGF1(hash_alg), salt_length=hash_alg.digest_size),
            hash_alg,
        )
