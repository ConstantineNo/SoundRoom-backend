"""CHANGE-002 classification; historical scope/ownership is never guessed.

Revision ID: c2a20260918
Revises: fe4213a38322
"""
from datetime import datetime
from alembic import op
import sqlalchemy as sa

revision = "c2a20260918"
down_revision = "fe4213a38322"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scores", sa.Column("original_key", sa.String(200)))
    op.add_column("scores", sa.Column("notes", sa.Text()))
    op.add_column("scores", sa.Column("visibility", sa.String(20), nullable=False, server_default="private"))
    op.add_column("scores", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    arrangements = op.create_table("score_arrangements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("score_id", sa.Integer(), sa.ForeignKey("scores.id"), nullable=False),
        sa.Column("label", sa.String(100), nullable=False), sa.Column("coverage", sa.String(20), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False), sa.Column("notes", sa.Text()))
    op.create_index("ix_score_arrangements_score_id", "score_arrangements", ["score_id"])
    sections = op.create_table("score_sections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("arrangement_id", sa.Integer(), sa.ForeignKey("score_arrangements.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False), sa.Column("location_label", sa.String(200), nullable=False),
        sa.Column("local_key", sa.String(200)), sa.Column("performance_key", sa.String(200)),
        sa.Column("key_basis", sa.String(20), nullable=False), sa.Column("instrument_profile", sa.String(100), nullable=False),
        sa.Column("fingering_code", sa.String(20)), sa.Column("fingering_raw", sa.String(200)),
        sa.Column("flute_key", sa.String(10)), sa.Column("classification_status", sa.String(20), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False), sa.Column("notes", sa.Text()))
    op.create_index("ix_score_sections_arrangement_id", "score_sections", ["arrangement_id"])
    op.create_table("score_idempotency",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("method", sa.String(10), nullable=False), sa.Column("path", sa.String(250), nullable=False),
        sa.Column("key", sa.String(200), nullable=False), sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False), sa.Column("etag", sa.String(100), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "method", "path", "key", name="uq_score_idempotency"))
    assets = op.create_table("score_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("score_id", sa.Integer(), sa.ForeignKey("scores.id"), nullable=False),
        sa.Column("arrangement_id", sa.Integer(), sa.ForeignKey("score_arrangements.id", ondelete="SET NULL")),
        sa.Column("purpose", sa.String(30), nullable=False), sa.Column("storage_key", sa.String(100), nullable=False),
        sa.Column("legacy_path", sa.String(255)),
        sa.Column("media_type", sa.String(100), nullable=False), sa.Column("size", sa.Integer(), nullable=True),
        sa.Column("processing_status", sa.String(20), nullable=False), sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("public_allowed", sa.Boolean(), nullable=False), sa.Column("copy_allowed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_score_assets_score_id", "score_assets", ["score_id"])
    connection = op.get_bind()
    scores = sa.table("scores", sa.column("id", sa.Integer()), sa.column("song_key", sa.String()),
        sa.column("original_key", sa.String()), sa.column("flute_key", sa.String()), sa.column("fingering", sa.String()),
        sa.column("image_path", sa.String()), sa.column("audio_path", sa.String()))
    connection.execute(scores.update().values(original_key=scores.c.song_key))
    # Freeze migration normalization rather than importing evolving application code.
    codes = {"closed_" + d for d in ("1", "2", "3", "4", "5", "6", "b7", "7")}
    for old in connection.execute(sa.select(scores)).mappings().all():
        for field, purpose in (("image_path", "score_image"), ("audio_path", "reference_audio")):
            if old[field]:
                connection.execute(assets.insert().values(score_id=old["id"], purpose=purpose,
                    storage_key=f"legacy-{old['id']}-{field}", legacy_path=old[field],
                    media_type="application/octet-stream", size=None, processing_status="stored",
                    issues=[{"reason": "LEGACY_CONTENT_UNVERIFIED"}], public_allowed=False, copy_allowed=False,
                    created_at=datetime.utcnow()))
        result = connection.execute(arrangements.insert().values(score_id=old["id"], label="历史方案（待核实）",
            coverage="unknown", is_default=True, notes="迁移来源未经人工复核"))
        raw = old["fingering"] or "未知"
        normalized = raw.replace("全按", "筒音").replace("做", "作").replace("♭", "b").replace("降", "b").replace(" ", "")
        code = normalized if normalized in codes else "closed_" + normalized.removeprefix("筒音作")
        connection.execute(sections.insert().values(arrangement_id=result.inserted_primary_key[0], position=0,
            location_label="范围待核实", key_basis="original", instrument_profile="standard_six_hole_dizi",
            fingering_code=code if code in codes else None, fingering_raw=raw, flute_key=None,
            classification_status="needs_review", evidence={"source": "legacy_migration", "previous_flute_key": old["flute_key"],
                "original_key": old["song_key"], "scope_verified": False}))


def downgrade() -> None:
    # Reverting a multi-arrangement model into scalars would silently destroy data.
    raise RuntimeError("CHANGE-002 is a data migration. Restore a verified pre-migration backup to roll back.")
