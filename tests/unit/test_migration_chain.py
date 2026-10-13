from alembic.script import ScriptDirectory

from noc.cli.main import alembic_config


def test_migrations_form_one_unbroken_chain() -> None:
    scripts = ScriptDirectory.from_config(alembic_config())
    assert scripts.get_heads() == [scripts.get_current_head()]
    revisions = list(scripts.walk_revisions())
    assert revisions[-1].down_revision is None
    assert len(revisions) == len({revision.revision for revision in revisions})
