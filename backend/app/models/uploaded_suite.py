"""A user-uploaded evaluation suite. Public tests and the spec are stored in plaintext; the hidden
tests are stored ENCRYPTED (app.sealing). Only aggregate counts and hashes ever leave the backend.

The three committed hashes are stored so that an execution's commitment can be recorded at run start
WITHOUT decrypting the hidden tests: decryption happens only at evaluation time.
"""
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime, utcnow
from app.hashing import SHA256_SQL


class UploadedSuite(Base):
    __tablename__ = "uploaded_suites"
    __table_args__ = (
        CheckConstraint(SHA256_SQL.format(col="suite_hash"), name="ck_uploaded_suites_suite_hash"),
        CheckConstraint(SHA256_SQL.format(col="public_suite_hash"), name="ck_uploaded_suites_public_hash"),
        CheckConstraint(SHA256_SQL.format(col="hidden_suite_hash"), name="ck_uploaded_suites_hidden_hash"),
        CheckConstraint("hidden_test_count >= 1 AND public_test_count >= 1", name="ck_uploaded_suites_counts"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 'u<hex>', fits the suite-id regex
    spec: Mapped[dict] = mapped_column(JSON)  # entrypoint, language, description, contract, quality
    public_tests: Mapped[list[dict]] = mapped_column(JSON)  # plaintext: public tests may be shown
    hidden_tests_sealed: Mapped[bytes] = mapped_column(LargeBinary)  # Fernet token of the hidden tests JSON
    public_test_count: Mapped[int] = mapped_column(Integer)
    hidden_test_count: Mapped[int] = mapped_column(Integer)
    suite_hash: Mapped[str] = mapped_column(String(64))
    public_suite_hash: Mapped[str] = mapped_column(String(64))
    hidden_suite_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
