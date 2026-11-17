"""Egress CA for inspected HTTPS (INV-11).

An agent's HTTPS client sends CONNECT to the sandbox proxy. The forwarder answers the tunnel
itself with a short-lived certificate for the requested host, signed by this deployment's
egress CA. The sandbox trusts only that CA, so the agent's TLS ends at the forwarder, which
then sees every request, stamps the agent's signed identity and hands it to Envoy. Envoy opens
the real TLS connection to the upstream and validates the upstream's certificate against the
system CA store. The CA private key stays in the vault and never enters a sandbox.
"""
import datetime
import ipaddress
import re
import ssl
import tempfile
import threading
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

KEY_REF = "keychain://egress-ca-key"
CERT_REF = "keychain://egress-ca-cert"
HOST = re.compile(r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$")


class EgressCA:
    def __init__(self, cert_pem: str, key_pem: str):
        self.cert_pem = cert_pem.strip() + "\n"
        self.cert = x509.load_pem_x509_certificate(self.cert_pem.encode())
        self.key = serialization.load_pem_private_key(key_pem.encode(), password=None)
        if not self.cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise ValueError("egress CA certificate is not a CA")
        self._dir = Path(tempfile.mkdtemp(prefix="rvos-leaf-"))
        self._dir.chmod(0o700)
        self._contexts: dict[str, ssl.SSLContext] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_vault(cls, resolver) -> "EgressCA | None":
        cert, key = resolver.get(CERT_REF), resolver.get(KEY_REF)
        return cls(cert, key) if cert and key else None

    def write_bundle(self, path: Path) -> Path:
        path.write_text(self.cert_pem)
        return path

    def server_context(self, host: str) -> ssl.SSLContext:
        """TLS server context presenting a leaf certificate for `host` (cached per CA)."""
        host = host.lower()
        if not HOST.match(host):
            try:
                ipaddress.ip_address(host)
            except ValueError:
                raise ValueError(f"not a valid host name: {host!r}") from None
        with self._lock:
            if host in self._contexts:
                return self._contexts[host]
            key = ec.generate_private_key(ec.SECP256R1())
            now = datetime.datetime.now(datetime.timezone.utc)
            try:
                san = x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(host))])
            except ValueError:
                san = x509.SubjectAlternativeName([x509.DNSName(host)])
            cert = (x509.CertificateBuilder()
                    .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host[:64])]))
                    .issuer_name(self.cert.subject)
                    .public_key(key.public_key())
                    .serial_number(x509.random_serial_number())
                    .not_valid_before(now - datetime.timedelta(minutes=5))
                    .not_valid_after(now + datetime.timedelta(hours=24))
                    .add_extension(san, critical=False)
                    .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                    .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                    .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
                    .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(self.key.public_key()), critical=False)
                    .sign(self.key, hashes.SHA256()))   # key identifiers: required by strict X.509 checks
            stem = self._dir / host.replace(":", "_")
            chain = stem.with_suffix(".crt")
            keyfile = stem.with_suffix(".key")
            chain.write_bytes(cert.public_bytes(serialization.Encoding.PEM) + self.cert_pem.encode())
            keyfile.touch(mode=0o600)
            keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                  serialization.NoEncryption()))
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.load_cert_chain(chain, keyfile)
            ctx.set_alpn_protocols(["http/1.1"])
            self._contexts[host] = ctx
            return ctx


def generate_ca(common_name: str = "RevenueOS egress CA") -> tuple[str, str]:
    """(cert_pem, key_pem) for a new egress CA; used by bootstrap and tests."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                                         key_encipherment=False, data_encipherment=False, key_agreement=False,
                                         encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256()))
    return (cert.public_bytes(serialization.Encoding.PEM).decode(),
            key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()).decode())


if __name__ == "__main__":  # pragma: no cover - used by infra/bootstrap.sh
    import sys
    c, k = generate_ca()
    Path(sys.argv[1]).write_text(c)
    kp = Path(sys.argv[2])
    kp.touch(mode=0o600)
    kp.write_text(k)
