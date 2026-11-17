"""CA e certificado exclusivos do laboratorio local; chave da CA so em memoria."""
from __future__ import annotations

import ipaddress
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

SERVER = Path("/tls-servidor")
CLIENT = Path("/tls-cliente")
EXPORT = Path("/exportar-ca")


def write(path, body, mode=0o644):
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        mode,
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(body)


def main():
    for folder in (SERVER, CLIENT, EXPORT):
        folder.mkdir(parents=True, exist_ok=True)
        if folder != EXPORT:
            folder.chmod(0o755)

    ca_path = SERVER / "ca.pem"
    cert_path = SERVER / "server.pem"
    key_path = SERVER / "server-key.pem"
    files = (
        ca_path,
        cert_path,
        key_path,
        CLIENT / "ca.pem",
    )

    if any(p.exists() for p in files):
        if not all(p.is_file() for p in files):
            raise RuntimeError(
                "TLS local parcialmente criado. Revisar volumes; "
                "nenhum arquivo sera sobrescrito."
            )

        ca = x509.load_pem_x509_certificate(
            ca_path.read_bytes()
        )
        cert = x509.load_pem_x509_certificate(
            cert_path.read_bytes()
        )
        key = serialization.load_pem_private_key(
            key_path.read_bytes(),
            password=None,
        )

        ca.public_key().verify(
            cert.signature,
            cert.tbs_certificate_bytes,
            padding.PKCS1v15(),
            cert.signature_hash_algorithm,
        )

        if (
            cert.public_key().public_numbers()
            != key.public_key().public_numbers()
        ):
            raise RuntimeError(
                "Certificado e chave local nao correspondem."
            )

        if min(
            ca.not_valid_after_utc,
            cert.not_valid_after_utc,
        ) <= datetime.now(timezone.utc):
            raise RuntimeError(
                "Certificado local expirado; "
                "revisar renovacao antes de iniciar."
            )

        if (
            (CLIENT / "ca.pem").read_bytes()
            != ca_path.read_bytes()
        ):
            raise RuntimeError(
                "CA do cliente diferente da CA do servidor."
            )

    else:
        now = datetime.now(timezone.utc)

        ca_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        ca_name = x509.Name([
            x509.NameAttribute(
                NameOID.COMMON_NAME,
                "Litro de Ouro - CA LOCAL DE TESTES",
            )
        ])

        ca = (
            x509.CertificateBuilder()
            .subject_name(ca_name)
            .issuer_name(ca_name)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=365))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=0),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    False,
                    False,
                    False,
                    False,
                    False,
                    True,
                    True,
                    False,
                    False,
                ),
                critical=True,
            )
            .sign(ca_key, hashes.SHA256())
        )

        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, "db")
            ]))
            .issuer_name(ca.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=365))
            .add_extension(
                x509.BasicConstraints(
                    ca=False,
                    path_length=None,
                ),
                critical=True,
            )
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("db"),
                    x509.DNSName("localhost"),
                    x509.IPAddress(
                        ipaddress.ip_address("127.0.0.1")
                    ),
                ]),
                critical=False,
            )
            .add_extension(
                x509.ExtendedKeyUsage([
                    ExtendedKeyUsageOID.SERVER_AUTH
                ]),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )

        ca_bytes = ca.public_bytes(
            serialization.Encoding.PEM
        )

        write(ca_path, ca_bytes)
        write(CLIENT / "ca.pem", ca_bytes)
        write(
            cert_path,
            cert.public_bytes(serialization.Encoding.PEM),
        )
        write(
            key_path,
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            ),
            0o640,
        )

    # UID/GID da imagem oficial mysql:8.4.
    # Backend recebe apenas o volume da CA publica.
    os.chown(key_path, 999, 999)
    key_path.chmod(0o640)

    exported = EXPORT / "ca.pem"
    if exported.exists():
        if exported.read_bytes() != ca_path.read_bytes():
            raise RuntimeError(
                "A CA exportada difere do volume atual; "
                "revisar a conexao DBeaver."
            )
    else:
        write(exported, ca_path.read_bytes())

    print(
        "TLS local pronto. CA publica: "
        "docker/local/certs/ca.pem. Segredos preservados."
    )


if __name__ == "__main__":
    main()