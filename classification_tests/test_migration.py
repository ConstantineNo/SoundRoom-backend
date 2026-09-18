"""Exercise actual migrations against populated legacy databases."""
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from sqlalchemy import create_engine, text
from app.core import config
from app.core.database import Base


def test_legacy_migration_and_schema_drift(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setattr(config, "SQLALCHEMY_DATABASE_URL", url)
    settings = Config("alembic.ini")
    command.upgrade(settings, "fe4213a38322")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id,username) VALUES (1,'legacy')"))
        connection.execute(text("INSERT INTO scores (id,title,song_key,flute_key,fingering,image_path,audio_path,created_by) VALUES (42,'legacy','D','A','全按作2','uploads/img.png','uploads/a.wav',1)"))
        connection.execute(text("INSERT INTO scores (id,title,song_key,flute_key,fingering) VALUES (43,'unowned','未知','未知','特别指法')"))
    command.upgrade(settings, "head")
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT * FROM scores ORDER BY id")).mappings().all()
        assert [r['id'] for r in rows] == [42, 43]
        assert rows[0]['original_key'] == 'D' and rows[0]['image_path'] == 'uploads/img.png'
        assert rows[1]['created_by'] is None and rows[1]['visibility'] == 'private'
        sections = connection.execute(text("SELECT * FROM score_sections ORDER BY id")).mappings().all()
        assert all(s['classification_status'] == 'needs_review' and s['flute_key'] is None for s in sections)
        assets = connection.execute(text("SELECT * FROM score_assets ORDER BY id")).mappings().all()
        assert len(assets) == 2 and all(not a['public_allowed'] for a in assets)
        assert [a['legacy_path'] for a in assets] == ['uploads/img.png', 'uploads/a.wav']
        assert sections[0]['fingering_code'] == 'closed_2' and sections[1]['fingering_code'] is None
        assert connection.execute(text("SELECT coverage FROM score_arrangements")).scalars().all() == ['unknown', 'unknown']
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []
    command.upgrade(settings, "head")  # repeat upgrade is a no-op
    engine.dispose()


def test_edition_upgrade_preserves_entire_existing_aggregate(tmp_path, monkeypatch):
    import json
    url = f"sqlite:///{tmp_path / 'edition-upgrade.db'}"
    monkeypatch.setattr(config, 'SQLALCHEMY_DATABASE_URL', url)
    settings = Config('alembic.ini')
    command.upgrade(settings, 'c2a20260918')
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users(id,username) VALUES (11,'owner')"))
        connection.execute(text("INSERT INTO scores(id,title,original_key,notes,tags,created_by,visibility,revision,abc_source) VALUES (77,'同名','D','不要推断歌手','[\"标签\"]',11,'public',9,'K:D')"))
        connection.execute(text("INSERT INTO score_arrangements(id,score_id,label,coverage,is_default) VALUES (88,77,'方案','complete',1)"))
        connection.execute(text("INSERT INTO score_sections(id,arrangement_id,position,location_label,key_basis,instrument_profile,fingering_code,flute_key,classification_status,evidence) VALUES (99,88,0,'全曲','original','standard_six_hole_dizi','closed_2','A','confirmed','{}')"))
        connection.execute(text("INSERT INTO score_assets(id,score_id,arrangement_id,purpose,storage_key,media_type,size,processing_status,issues,public_allowed,copy_allowed,created_at) VALUES (111,77,88,'score_image','unchanged-file','image/png',123,'stored','[]',0,0,'2026-09-18')"))
        before_score = dict(connection.execute(text('SELECT * FROM scores')).mappings().one())
        before_related = {table:[dict(row) for row in connection.execute(text('SELECT * FROM '+table)).mappings()]
            for table in ('users','score_arrangements','score_sections','score_assets')}
    command.upgrade(settings, 'head')
    with engine.connect() as connection:
        after = dict(connection.execute(text('SELECT * FROM scores')).mappings().one())
        assert {key:after[key] for key in before_score} == before_score
        new_columns = set(after)-set(before_score)
        assert new_columns == {'edition_'+name for name in ('label','original_artist','performer','album','release_date')}
        assert all(after[key] is None for key in new_columns)
        for table,rows in before_related.items():
            assert [dict(row) for row in connection.execute(text('SELECT * FROM '+table)).mappings()] == rows
        assert connection.execute(text('PRAGMA foreign_key_check')).all() == []
        assert compare_metadata(MigrationContext.configure(connection),Base.metadata) == []
    command.upgrade(settings,'head')
    engine.dispose()
